"""Open Food Facts client (nutrition spec §3B + Amendment C4): packaged products by barcode or text search.

Barcode lookup is the reliable path. Text search uses search.openfoodfacts.org (the legacy cgi/search.pl was
unreliable when tested) and is noisy ("skyr bily" → "Sambal bilis"), so the caller lets Gemini pick a candidate.
OFF asks for a descriptive User-Agent and ≤ 10 searches/min; lookups are user-driven, one per logged item.
Only complete products (kcal + protein + carbs + fat known) can become foods; missing values stay null.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.models.nutrition import Food, FoodPortion, FoodSource
from app.timeutils import now_utc

PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{ean}.json"
SEARCH_URL = "https://search.openfoodfacts.org/search"
HEADERS = {"User-Agent": "fitness-hub/1.0 (self-hosted personal app)"}
FIELDS = "code,product_name,product_name_cs,generic_name,brands,quantity,serving_quantity,nutriments"
KJ_PER_KCAL = 4.184

# OFF nutriment key (per 100 g) → our column
COLUMNS = {
    "proteins_100g": "protein_g",
    "carbohydrates_100g": "carbs_g",
    "fat_100g": "fat_g",
    "sugars_100g": "sugar_g",
    "saturated-fat_100g": "saturated_fat_g",
    "fiber_100g": "fiber_g",
    "salt_100g": "salt_g",
}
# OFF reports minerals in g per 100 g; ours are mg
MICROS_G_TO_MG = {"sodium_100g": "sodium_mg", "calcium_100g": "calcium_mg", "iron_100g": "iron_mg"}


@dataclass
class OffProduct:
    ean: str
    name: str
    brand: str | None
    values: dict[str, float]  # our macro columns that OFF knows
    micronutrients: dict[str, float] = field(default_factory=dict)
    serving_g: float | None = None

    @property
    def complete(self) -> bool:
        return all(k in self.values for k in ("kcal", "protein_g", "carbs_g", "fat_g"))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_product(data: dict[str, Any]) -> OffProduct | None:
    """An OFF product (lookup or search hit) → OffProduct; None without a code or a name."""
    name = (data.get("product_name_cs") or data.get("product_name") or data.get("generic_name") or "").strip()
    ean = str(data.get("code") or "").strip()
    if not name or not ean:
        return None
    brands = data.get("brands")
    brand = (brands[0] if isinstance(brands, list) else str(brands).split(",")[0]) if brands else None
    nutriments = data.get("nutriments") or {}
    values: dict[str, float] = {}
    kcal = _number(nutriments.get("energy-kcal_100g"))
    if kcal is None and (kj := _number(nutriments.get("energy-kj_100g") or nutriments.get("energy_100g"))) is not None:
        kcal = round(kj / KJ_PER_KCAL, 1)  # energy_100g is kJ, never kcal
    if kcal is not None:
        values["kcal"] = kcal
    for key, column in COLUMNS.items():
        if (number := _number(nutriments.get(key))) is not None:
            values[column] = number
    micros = {
        column: round(number * 1000, 3)
        for key, column in MICROS_G_TO_MG.items()
        if (number := _number(nutriments.get(key))) is not None
    }
    serving = _number(data.get("serving_quantity"))
    return OffProduct(ean, name, brand.strip() if brand else None, values, micros, serving or None)


def lookup_barcode(http: httpx.Client, ean: str) -> OffProduct | None:
    response = http.get(PRODUCT_URL.format(ean=ean), params={"fields": FIELDS}, headers=HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    body = response.json()
    if body.get("status") != 1 or not body.get("product"):
        return None
    return parse_product(body["product"] | {"code": body.get("code") or ean})


def search(http: httpx.Client, query: str, limit: int = 10) -> list[OffProduct]:
    """Complete products only, in OFF's order (the caller ranks them)."""
    response = http.get(SEARCH_URL, params={"q": query, "page_size": limit, "fields": FIELDS}, headers=HEADERS)
    response.raise_for_status()
    products = (parse_product(hit) for hit in response.json().get("hits") or [])
    return [p for p in products if p is not None and p.complete]


def save_product(session: Session, product: OffProduct) -> Food:
    """Upsert by EAN (OFF data is refreshed, a Czech name set later is kept) plus its serving as a portion."""
    if not product.complete:
        raise ValueError(f"OFF product {product.ean} lacks a required macro")
    now = now_utc()
    row = {
        "name_cs": product.name,
        "brand": product.brand,
        "ean": product.ean,
        "source": FoodSource.openfoodfacts.value,
        "external_id": f"off:{product.ean}",
        "micronutrients": product.micronutrients,
        "updated_at": now,
    } | {c: product.values.get(c) for c in ("kcal", "protein_g", "carbs_g", "fat_g", *COLUMNS.values())}
    statement = insert(Food).values(row | {"created_at": now})
    refreshed = {c: statement.excluded[c] for c in row if c not in ("ean", "name_cs")}
    session.connection().execute(statement.on_conflict_do_update(index_elements=["ean"], set_=refreshed))
    food = session.exec(select(Food).where(Food.ean == product.ean).execution_options(populate_existing=True)).one()
    if product.serving_g:
        portion = insert(FoodPortion).values(food_id=food.id, label="1 porce", grams=product.serving_g)
        session.connection().execute(portion.on_conflict_do_nothing(index_elements=["food_id", "label"]))
    session.commit()
    return food
