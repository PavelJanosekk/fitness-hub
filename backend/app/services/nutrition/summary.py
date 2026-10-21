"""The day view of intake: meals with live-computed items, and per-nutrient totals with coverage (Amendment C1).

Coverage = share of the day's kcal that comes from items whose food has a value for that nutrient. A low
coverage means "unknown", not "deficient": quick-add items and foods without micros (KT, many OFF products)
lower it. A food without a micro (or fibre, sugar, ...) borrows it from its USDA references (E26, `micro_refs.py`).
"""

import datetime as dt
import uuid

from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, col, exists, select

from app.models.gym import Workout
from app.models.nutrition import Food, MealLog, MealLogItem, MealType, NutritionProfile
from app.models.running import Activity
from app.schemas.nutrition import MealItemRead, MealRead
from app.services.nutrition import ITEM_MACROS, item_values
from app.services.nutrition.micro_refs import Ref, effective_values, refs_for
from app.services.nutrition.nutrients import ALL
from app.services.nutrition.targets import DayTarget, Mode, day_target
from app.timeutils import day_bounds

MEAL_ORDER = {meal_type.value: index for index, meal_type in enumerate(MealType)}


class NutrientSource(BaseModel):
    """One food's share of a day total (the same food eaten twice is summed)."""

    name: str
    amount: float
    estimated: bool  # borrowed from the food's USDA references (E26), not the food's own value


class NutrientTotal(BaseModel):
    key: str
    label: str
    unit: str
    amount: float | None  # sum over items with a known value; None when no item has one
    coverage: float | None  # 0-1 share of the day's kcal behind `amount`; None on a day without kcal
    target: float | None  # the profile target, else the EU reference
    percent: float | None
    sources: list[NutrientSource] = []  # largest first
    unknown: list[str] = []  # items of the day without a value for this nutrient


class DaySummary(BaseModel):
    date: dt.date
    training_day: bool
    meals: list[MealRead]
    nutrients: list[NutrientTotal]
    target: DayTarget  # the day's kcal target and where it comes from (E41)
    fueling_kcal: float  # eaten during runs: in the totals, but not compared with the target


def _item_nutrients(
    item: MealLogItem, food: Food | None, refs: list[Ref] | None
) -> tuple[dict[str, float | None], set[str]]:
    """Every tracked nutrient for one item, and the keys borrowed from references. A quick-add item knows only
    its manual macros."""
    values: dict[str, float | None] = dict.fromkeys((n.key for n in ALL), None) | item_values(item, food)
    if food is None or item.amount_g is None:
        return values, set()
    scale = item.amount_g / 100
    known = effective_values(food, refs)
    borrowed = set(known) - set(effective_values(food, None))
    for nutrient in ALL:
        if nutrient.key not in ITEM_MACROS:
            per_100g = known.get(nutrient.key)
            values[nutrient.key] = None if per_100g is None else per_100g * scale
    return values, borrowed


def _sources(
    key: str, items: list[tuple[str, dict[str, float | None], set[str]]]
) -> tuple[list[NutrientSource], list[str]]:
    sums: dict[str, list] = {}
    unknown: list[str] = []
    for name, values, borrowed in items:
        value = values[key]
        if value is None:
            if name not in unknown:
                unknown.append(name)
            continue
        entry = sums.setdefault(name, [0.0, False])
        entry[0] += value
        entry[1] = entry[1] or key in borrowed
    sources = [
        NutrientSource(name=name, amount=round(amount, 3), estimated=estimated)
        for name, (amount, estimated) in sums.items()
        if round(amount, 3) > 0
    ]
    return sorted(sources, key=lambda source: -source.amount), unknown


def _rows(session: Session, day: dt.date) -> list[tuple[MealLog, MealLogItem, Food | None]]:
    statement = (
        select(MealLog, MealLogItem, Food)
        .join(MealLogItem, col(MealLogItem.meal_log_id) == MealLog.id)
        .outerjoin(Food, col(Food.id) == MealLogItem.food_id)
        .where(MealLog.logged_date == day)
        .order_by(col(MealLog.created_at))
    )
    return list(session.exec(statement).all())  # type: ignore[arg-type]


def read_item(item: MealLogItem, food: Food | None) -> MealItemRead:
    values = item_values(item, food)
    return MealItemRead(
        id=item.id,
        label=item.label,
        food_id=item.food_id,
        food_name=food.name if food else None,
        food_source=food.source if food else None,
        amount_g=item.amount_g,
        kcal=values["kcal"] or 0.0,
        protein_g=values["protein_g"],
        carbs_g=values["carbs_g"],
        fat_g=values["fat_g"],
    )


def day_meals(session: Session, day: dt.date) -> list[MealRead]:
    meals: dict[uuid.UUID, MealRead] = {}
    for meal, item, food in _rows(session, day):
        read = meals.setdefault(
            meal.id,
            MealRead(id=meal.id, logged_date=meal.logged_date, meal_type=meal.meal_type, notes=meal.notes, items=[]),
        )
        read.items.append(read_item(item, food))
    return sorted(meals.values(), key=lambda m: MEAL_ORDER[m.meal_type])


def is_training_day(session: Session, day: dt.date) -> bool:
    start, end = day_bounds(day)
    workout = exists().where(col(Workout.started_at) >= start, col(Workout.started_at) < end)
    activity = exists().where(col(Activity.start_time) >= start, col(Activity.start_time) < end)
    return bool(session.exec(select(or_(workout, activity))).one())


def _targets(profile: NutritionProfile | None, target: DayTarget) -> dict[str, float | None]:
    """Targets per nutrient; a key with None means "no target" (off mode), a missing key falls back to the EU
    reference."""
    candidates: dict[str, float | None] = {
        "kcal": target.kcal,
        "protein_g": target.protein_g,
        "carbs_g": target.carbs_g,
        "fat_g": target.fat_g,
        "fiber_g": profile.fiber_target_g if profile else None,
    }
    no_target = {"kcal", "protein_g", "carbs_g", "fat_g"} if target.mode == Mode.off else set()
    return {k: v for k, v in candidates.items() if v is not None or k in no_target}


def day_summary(session: Session, day: dt.date) -> DaySummary:
    rows = _rows(session, day)
    refs = refs_for(session, (food.id for _, _, food in rows if food is not None))  # type: ignore[misc]
    items = [
        (food.name if food else item.label, *_item_nutrients(item, food, refs.get(food.id) if food else None))  # type: ignore[arg-type]
        for _, item, food in rows
    ]
    per_item = [values for _, values, _ in items]
    fueling = [meal.meal_type == MealType.fueling for meal, _, _ in rows]
    day_kcal = sum(values["kcal"] or 0 for values in per_item)
    training_day = is_training_day(session, day)
    profile = session.get(NutritionProfile, 1)
    day_goal = day_target(session, day, profile)
    targets = _targets(profile, day_goal)
    totals = []
    for nutrient in ALL:
        known = [(v[nutrient.key], v["kcal"] or 0) for v in per_item if v[nutrient.key] is not None]
        amount = round(sum(value for value, _ in known), 3) if known else None
        coverage = round(sum(kcal for _, kcal in known) / day_kcal, 3) if day_kcal > 0 else None
        target = targets.get(nutrient.key, nutrient.reference)
        # Fueling during runs is covered by the run itself, so it doesn't eat into the target
        counted = [v[nutrient.key] for v, during_run in zip(per_item, fueling, strict=True) if not during_run]
        counted_amount = sum(v for v in counted if v is not None) if any(v is not None for v in counted) else None
        percent = round(counted_amount / target * 100, 1) if counted_amount is not None and target else None
        sources, unknown = _sources(nutrient.key, items)
        totals.append(
            NutrientTotal(
                key=nutrient.key,
                label=nutrient.label_cs,
                unit=nutrient.unit,
                amount=amount,
                coverage=coverage,
                target=target,
                percent=percent,
                sources=sources,
                unknown=unknown,
            )
        )
    fueling_kcal = sum((v["kcal"] or 0) for v, during_run in zip(per_item, fueling, strict=True) if during_run)
    return DaySummary(
        date=day,
        training_day=training_day,
        meals=day_meals(session, day),
        nutrients=totals,
        target=day_goal,
        fueling_kcal=round(fueling_kcal, 1),
    )
