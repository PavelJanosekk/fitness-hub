"""USDA FoodData Central bulk seed (decision E3): SR Legacy + Foundation into `foods` and `food_portions`.

USDA's CSV editions are downloaded once (pinned URL + sha256), streamed row by row (the SR JSON edition is 210 MB
unzipped) and upserted by `external_id = usda:<fdc_id>`. Only mapped nutrients are stored (nutrients.py); foods
missing a required macro are skipped. Runs from `python -m app.seed` when no USDA food exists yet, or by hand:
`python -m app.services.nutrition.usda [--force]` (e.g. after bumping a dataset below).
"""

import csv
import hashlib
import io
import logging
import re
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, func, select

from app.models.nutrition import Food, FoodPortion, FoodSource
from app.services.nutrition.nutrients import MACROS, MICRO_KEYS, REQUIRED_MACROS, USDA_IDS, from_usda
from app.timeutils import now_utc

log = logging.getLogger(__name__)

BASE_URL = "https://fdc.nal.usda.gov/fdc-datasets"
BATCH = 500


@dataclass(frozen=True)
class Dataset:
    file: str
    sha256: str
    data_type: str  # food.csv rows of other types (Foundation's samples) are ignored


DATASETS = (
    Dataset(
        "FoodData_Central_sr_legacy_food_csv_2018-04.zip",
        "b80817294b8850530aaedf2e515c02593b1824f763a0ff356e5c2081643e6fd0",
        "sr_legacy_food",
    ),
    Dataset(
        "FoodData_Central_foundation_food_csv_2026-04-30.zip",
        "70457ee9d9342f43bda2010318c85f04210c689fdeb9cd2da4c513b0e8dbc655",
        "foundation_food",
    ),
)


@dataclass
class UsdaFood:
    fdc_id: str
    description: str
    category: str | None
    amounts: dict[int, float] = field(default_factory=dict)
    portions: dict[str, float] = field(default_factory=dict)  # label → grams


@dataclass
class SeedResult:
    foods: int = 0
    portions: int = 0
    skipped: int = 0  # no value for a required macro


class UsdaError(RuntimeError):
    pass


def _rows(archive: zipfile.ZipFile, table: str) -> Iterator[dict[str, str]]:
    name = next((n for n in archive.namelist() if n.endswith(f"/{table}.csv") or n == f"{table}.csv"), None)
    if name is None:
        raise UsdaError(f"{table}.csv missing from the archive")
    with archive.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))


def _portion_label(row: dict[str, str], units: dict[str, str]) -> str:
    amount = float(row["amount"]) if row.get("amount") else 1.0
    unit = units.get(row.get("measure_unit_id", ""), "")
    parts = [f"{amount:g}"]
    if unit and unit != "undetermined":
        parts.append(unit)
    if detail := (row.get("portion_description") or row.get("modifier") or "").strip():
        parts.append(detail)
    return re.sub(r"\s+", " ", " ".join(parts))[:120]


def parse(path: Path, data_type: str) -> list[UsdaFood]:
    """Foods of `data_type` from one USDA CSV zip, with mapped nutrient amounts and portions."""
    with zipfile.ZipFile(path) as archive:
        categories = {r["id"]: r["description"] for r in _rows(archive, "food_category")}
        foods = {
            r["fdc_id"]: UsdaFood(r["fdc_id"], r["description"].strip(), categories.get(r["food_category_id"]))
            for r in _rows(archive, "food")
            if r["data_type"] == data_type
        }
        for r in _rows(archive, "food_nutrient"):
            food = foods.get(r["fdc_id"])
            if food is None or not r["amount"]:
                continue
            nutrient_id = int(r["nutrient_id"])
            if nutrient_id in USDA_IDS:
                food.amounts[nutrient_id] = float(r["amount"])
        units = {r["id"]: r["name"] for r in _rows(archive, "measure_unit")}
        for r in _rows(archive, "food_portion"):
            food = foods.get(r["fdc_id"])
            if food is not None and r["gram_weight"] and float(r["gram_weight"]) > 0:
                food.portions.setdefault(_portion_label(r, units), float(r["gram_weight"]))
    return list(foods.values())


def _is_raw(description: str) -> bool | None:
    words = set(re.findall(r"[a-z]+", description.lower()))
    if "raw" in words:
        return True
    if words & {"cooked", "boiled", "roasted", "baked", "fried", "grilled", "braised", "steamed", "broiled", "stewed"}:
        return False
    return None


def _food_row(food: UsdaFood) -> dict | None:
    values = from_usda(food.amounts)
    if any(key not in values for key in REQUIRED_MACROS):
        return None
    now = now_utc()
    row = {
        "name_en": food.description,
        "category": food.category,
        "source": FoodSource.usda.value,
        "external_id": f"usda:{food.fdc_id}",
        "is_raw": _is_raw(food.description),
        "micronutrients": {k: v for k, v in values.items() if k in MICRO_KEYS},
        "created_at": now,
        "updated_at": now,
    }
    # Every macro column in every row (multi-row INSERT needs the same keys); unknown ones stay null
    return row | {n.key: values.get(n.key) for n in MACROS}


def import_foods(session: Session, foods: list[UsdaFood]) -> SeedResult:
    """Upsert by external_id. Nutrients and names from USDA are refreshed; name_cs (set by use) is kept."""
    result = SeedResult()
    rows, kept = [], []
    for food in foods:
        if (row := _food_row(food)) is None:
            result.skipped += 1
        else:
            rows.append(row)
            kept.append(food)
    refreshed = [c for c in rows[0] if c not in ("external_id", "created_at")] if rows else []
    ids: dict[str, int] = {}
    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        statement = insert(Food).values(batch)
        statement = statement.on_conflict_do_update(
            index_elements=["external_id"], set_={c: statement.excluded[c] for c in refreshed}
        ).returning(Food.external_id, Food.id)
        ids.update(dict(session.connection().execute(statement).all()))
    result.foods = len(rows)
    portions = [
        {"food_id": ids[f"usda:{food.fdc_id}"], "label": label, "grams": grams}
        for food in kept
        for label, grams in food.portions.items()
    ]
    for start in range(0, len(portions), BATCH):
        statement = insert(FoodPortion).values(portions[start : start + BATCH])
        statement = statement.on_conflict_do_update(
            index_elements=["food_id", "label"], set_={"grams": statement.excluded.grams}
        )
        session.connection().execute(statement)
    result.portions = len(portions)
    return result


def download(http: httpx.Client, dataset: Dataset, directory: Path) -> Path:
    path = directory / dataset.file
    digest = hashlib.sha256()
    with http.stream("GET", f"{BASE_URL}/{dataset.file}", follow_redirects=True) as response:
        response.raise_for_status()
        with path.open("wb") as out:
            for chunk in response.iter_bytes():
                digest.update(chunk)
                out.write(chunk)
    if digest.hexdigest() != dataset.sha256:
        raise UsdaError(f"{dataset.file}: sha256 mismatch ({digest.hexdigest()})")
    return path


def is_seeded(session: Session) -> bool:
    return bool(session.exec(select(func.count()).select_from(Food).where(Food.source == FoodSource.usda)).one())


def seed_usda(session: Session, http: httpx.Client, datasets: tuple[Dataset, ...] = DATASETS) -> SeedResult:
    """Download, parse and import every dataset in one transaction (all or nothing)."""
    total = SeedResult()
    with tempfile.TemporaryDirectory() as tmp:
        for dataset in datasets:
            part = import_foods(session, parse(download(http, dataset, Path(tmp)), dataset.data_type))
            total.foods += part.foods
            total.portions += part.portions
            total.skipped += part.skipped
    session.commit()
    return total


if __name__ == "__main__":
    import sys

    from app.database import engine

    with Session(engine) as db, httpx.Client(timeout=60, headers={"User-Agent": "fitness-hub"}) as client:
        if is_seeded(db) and "--force" not in sys.argv:
            print("usda: already seeded (use --force to refresh)")
        else:
            r = seed_usda(db, client)
            print(f"usda: {r.foods} foods, {r.portions} portions, {r.skipped} skipped (missing a required macro)")
