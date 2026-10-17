"""Open Food Facts client against recorded response shapes (2026-10-17), no network."""

import httpx
import pytest
from sqlmodel import Session, select

from app.models.nutrition import Food, FoodPortion
from app.services.nutrition.off import lookup_barcode, parse_product, save_product, search

JOGURT = {
    "code": "8594033403478",
    "product_name": "Smetanový jogurt bílý",
    "product_name_cs": "Smetanový jogurt bílý",
    "brands": "Clever",
    "quantity": "100 g",
    "serving_quantity": None,
    "nutriments": {
        "carbohydrates_100g": 3.3,
        "energy-kcal_100g": 115,
        "energy_100g": 477.1,
        "fat_100g": 10,
        "proteins_100g": 3,
        "salt_100g": 0.0975,
        "saturated-fat_100g": 6.5,
        "sodium_100g": 0.039,
        "sugars_100g": 3.3,
    },
}


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lookup_maps_a_found_product() -> None:
    http = client(lambda request: httpx.Response(200, json={"status": 1, "code": JOGURT["code"], "product": JOGURT}))

    product = lookup_barcode(http, "8594033403478")

    assert product is not None and product.complete
    assert (product.name, product.brand) == ("Smetanový jogurt bílý", "Clever")
    assert product.values == {
        "kcal": 115,
        "protein_g": 3,
        "carbs_g": 3.3,
        "fat_g": 10,
        "sugar_g": 3.3,
        "saturated_fat_g": 6.5,
        "salt_g": 0.0975,
    }
    assert product.micronutrients == {"sodium_mg": 39}


@pytest.mark.parametrize(
    "response", [httpx.Response(404), httpx.Response(200, json={"status": 0, "status_verbose": "product not found"})]
)
def test_unknown_barcode_is_none(response: httpx.Response) -> None:
    assert lookup_barcode(client(lambda request: response), "123") is None


def test_kcal_falls_back_to_kilojoules_and_unknowns_stay_missing() -> None:
    product = parse_product({"code": "1", "product_name": "X", "nutriments": {"energy_100g": 418.4, "fat_100g": 1}})

    assert product is not None
    assert product.values == {"kcal": 100, "fat_g": 1}
    assert not product.complete


def test_search_keeps_complete_products_and_reads_brand_lists() -> None:
    hits = [
        {"code": "1", "product_name": "Sambal bilis", "nutriments": {}},
        JOGURT | {"code": "2", "brands": ["Clever", "Billa"]},
    ]
    http = client(lambda request: httpx.Response(200, json={"hits": hits, "count": 2}))

    products = search(http, "jogurt bily")

    assert [(p.ean, p.brand) for p in products] == [("2", "Clever")]


def test_save_product_upserts_by_ean_and_keeps_a_czech_name(session: Session) -> None:
    product = parse_product(JOGURT | {"serving_quantity": 140})
    assert product is not None

    food = save_product(session, product)
    food.name_cs = "Jogurt bílý smetanový (Clever)"
    session.add(food)
    session.commit()
    product.values["kcal"] = 116
    again = save_product(session, product)

    assert again.id == food.id
    assert (again.kcal, again.name_cs, again.source, again.external_id) == (
        116,
        "Jogurt bílý smetanový (Clever)",
        "openfoodfacts",
        "off:8594033403478",
    )
    portions = session.exec(select(FoodPortion).where(FoodPortion.food_id == food.id)).all()
    assert [(p.label, p.grams) for p in portions] == [("1 porce", 140)]
    assert len(session.exec(select(Food)).all()) == 1
