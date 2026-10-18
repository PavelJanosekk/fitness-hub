"""Micronutrient references (E26): a food borrows the values it doesn't know from USDA foods.

A reference is (USDA food, grams of it per gram of the food). A value the food has itself (KT calcium/sodium,
OFF label values) always wins; otherwise it is the sum over the references that know it. That covers the micros
and the optional macros (sugar, saturated fat, fibre, salt; KT often lacks fibre); kcal/P/C/F always stay the
food's. The numbers therefore always come from USDA: mapping only decides which USDA foods, in what amounts,
describe the food.

Mappings come from a mapping file (`python -m app.services.nutrition.micro_refs < file`), from the Gemini
mapper for new foods (`mapper.py`) or from the user in the food sheet (status `manual`, never overwritten
automatically).
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from app.models.nutrition import Food, FoodMicroRef, FoodSource, MicrosStatus
from app.services.nutrition.nutrients import MACROS, REQUIRED_MACROS
from app.timeutils import now_utc

OPTIONAL_MACROS = tuple(n.key for n in MACROS if n.key not in REQUIRED_MACROS)


@dataclass(frozen=True)
class Ref:
    food: Food  # the USDA reference
    grams_per_g: float


def refs_for(session: Session, food_ids: Iterable[int]) -> dict[int, list[Ref]]:
    ids = {i for i in food_ids if i is not None}
    if not ids:
        return {}
    rows = session.exec(
        select(FoodMicroRef, Food)
        .join(Food, col(Food.id) == FoodMicroRef.ref_food_id)
        .where(col(FoodMicroRef.food_id).in_(ids))
        .order_by(col(FoodMicroRef.grams_per_g).desc())
    ).all()
    out: dict[int, list[Ref]] = defaultdict(list)
    for ref, food in rows:
        out[ref.food_id].append(Ref(food, ref.grams_per_g))
    return dict(out)


def _known(food: Food) -> dict[str, float]:
    """The food's own optional macros and micros, per 100 g (only known values)."""
    macros = {key: getattr(food, key) for key in OPTIONAL_MACROS}
    return {k: v for k, v in macros.items() if v is not None} | dict(food.micronutrients or {})


def effective_values(food: Food | None, refs: list[Ref] | None) -> dict[str, float]:
    """Per-100 g optional macros and micros: the food's own values, then the references' weighted sum for the
    keys it lacks."""
    if food is None:
        return {}
    own = _known(food)
    borrowed: dict[str, float] = defaultdict(float)
    for ref in refs or []:
        for key, value in _known(ref.food).items():
            if key not in own:
                borrowed[key] += value * ref.grams_per_g
    return own | {k: round(v, 4) for k, v in borrowed.items()}


def set_refs(session: Session, food: Food, refs: list[tuple[int, float]], status: MicrosStatus) -> None:
    """Replace the food's references (an empty list with `unmatched` records that nothing fits)."""
    session.exec(delete(FoodMicroRef).where(col(FoodMicroRef.food_id) == food.id))  # type: ignore[call-overload]
    merged: dict[int, float] = defaultdict(float)
    for ref_food_id, grams_per_g in refs:
        if ref_food_id != food.id and grams_per_g > 0:
            merged[ref_food_id] += grams_per_g
    for ref_food_id, grams_per_g in merged.items():
        session.add(FoodMicroRef(food_id=food.id, ref_food_id=ref_food_id, grams_per_g=round(min(grams_per_g, 5), 4)))  # type: ignore[arg-type]
    food.micros_status = status
    food.updated_at = now_utc()
    session.add(food)


def needs_mapping(food: Food) -> bool:
    return food.source != FoodSource.usda and food.micros_status is None


# Mapping file: one food per line, "<external_id> | <name, informational> | <fdc_id>:<grams_per_g> ..." ("-" = none)
LINE = re.compile(r"^(?P<ext>[^|#]+?)\s*\|\s*(?P<name>[^|]*?)\s*\|\s*(?P<refs>.+?)\s*$")


@dataclass
class ApplyResult:
    mapped: int = 0
    unmatched: int = 0
    skipped_manual: int = 0
    missing_foods: list[str] | None = None
    missing_usda: list[str] | None = None


def apply_mapping(session: Session, text: str) -> ApplyResult:
    """Apply a mapping file. Foods the user mapped by hand (`manual`) are left alone; unknown ids are reported."""
    result = ApplyResult(missing_foods=[], missing_usda=[])
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE.match(line)
        if match is None:
            raise ValueError(f"bad line: {raw!r}")
        food = session.exec(select(Food).where(Food.external_id == match["ext"])).first()
        if food is None:
            result.missing_foods.append(match["ext"])  # type: ignore[union-attr]
            continue
        if food.micros_status == MicrosStatus.manual:
            result.skipped_manual += 1
            continue
        refs: list[tuple[int, float]] = []
        if match["refs"] != "-":
            for token in match["refs"].split():
                fdc, _, grams = token.partition(":")
                ref = session.exec(select(Food).where(Food.external_id == f"usda:{fdc}")).first()
                if ref is None or ref.id is None:
                    result.missing_usda.append(fdc)  # type: ignore[union-attr]
                    continue
                refs.append((ref.id, float(grams)))
        set_refs(session, food, refs, MicrosStatus.mapped if refs else MicrosStatus.unmatched)
        if refs:
            result.mapped += 1
        else:
            result.unmatched += 1
    session.commit()
    return result


if __name__ == "__main__":
    # docker compose exec -T app python -m app.services.nutrition.micro_refs < mapping.txt
    import sys

    from app.database import engine

    with Session(engine) as db:
        r = apply_mapping(db, sys.stdin.read())
    print(f"micro refs: {r.mapped} mapped, {r.unmatched} unmatched, {r.skipped_manual} left alone (manual)")
    if r.missing_foods:
        print(f"  foods not found: {', '.join(r.missing_foods)}")
    if r.missing_usda:
        print(f"  USDA ids not found: {', '.join(sorted(set(r.missing_usda)))}")
