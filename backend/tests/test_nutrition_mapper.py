"""Micronutrient mapping of new foods (E26) against the fake Gemini client: the batch mapper, its daily budget,
free mapping from a draft's USDA query, autofill, and references through the food routes."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from fakes import FakeGemini
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import settings
from app.main import app
from app.models.nutrition import Food, FoodSource, MicrosStatus
from app.routers.ai_coach import gemini_client
from app.routers.nutrition import get_http
from app.services.nutrition import mapper
from app.services.nutrition.autofill import AutofillAnswer, Estimate
from app.services.nutrition.mapper import Component, FoodComponents
from app.services.nutrition.micro_refs import refs_for


@pytest.fixture(autouse=True)
def lite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gemini_model_lite", "lite-model")
    monkeypatch.setattr(settings, "micros_mapper_daily_requests", 10)
    monkeypatch.setattr(mapper, "budget", mapper._DailyBudget())


@pytest.fixture
def gemini():
    client = FakeGemini()
    app.dependency_overrides[gemini_client] = lambda: client
    yield client
    app.dependency_overrides.pop(gemini_client, None)


@pytest.fixture
def off_hits():
    hits: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": hits})

    app.dependency_overrides[get_http] = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    yield hits
    app.dependency_overrides.pop(get_http, None)


def food(session: Session, source: FoodSource, name: str, micros: dict | None = None, **fields) -> Food:
    values = {"kcal": 100.0, "protein_g": 10.0, "carbs_g": 10.0, "fat_g": 2.0} | fields
    names = {"name_en": name} if source == FoodSource.usda else {"name_cs": name}
    row = Food(source=source, micronutrients=micros or {}, **names, **values)
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def usda(session: Session) -> dict[str, Food]:
    return {
        "chicken": food(
            session, FoodSource.usda, "Chicken, broilers or fryers, breast, meat only, raw", {"iron_mg": 0.4}
        ),
        "broccoli": food(session, FoodSource.usda, "Broccoli, raw", {"vitamin_c_mg": 89.2}, fiber_g=2.6),
    }


def answer(*foods: FoodComponents) -> SimpleNamespace:
    return SimpleNamespace(parsed=list(foods))


def test_mapper_maps_a_batch_and_leaves_unanswered_foods_pending(session: Session, usda) -> None:
    dish = food(session, FoodSource.kaloricke_tabulky, "kureci rýže", kcal=78, protein_g=14.4)
    konjac = food(session, FoodSource.kaloricke_tabulky, "Shirataki")
    skipped = food(session, FoodSource.openfoodfacts, "Tyčinka")
    client = FakeGemini()
    client.generate_responses = [
        answer(
            FoodComponents(
                food=0,
                components=[
                    Component(usda_query_en="Chicken, broilers or fryers, breast, meat only, raw", grams_per_100g=60),
                    Component(usda_query_en="Broccoli, raw", grams_per_100g=20),
                    Component(usda_query_en="Unicorn steak", grams_per_100g=10),
                ],
            ),
            FoodComponents(food=1, components=[]),
        )
    ]

    mapped = mapper.map_foods(session, client, [dish, konjac, skipped])

    assert mapped == 1
    assert client.generated[0]["model"] == "lite-model"
    assert "0: kureci rýže: 78 kcal, B 14.4 g" in client.generated[0]["contents"]
    refs = refs_for(session, [dish.id, konjac.id])  # type: ignore[list-item]
    assert [(r.food.id, r.grams_per_g) for r in refs[dish.id]] == [
        (usda["chicken"].id, 0.6),
        (usda["broccoli"].id, 0.2),
    ]  # type: ignore[index]
    assert (dish.micros_status, konjac.micros_status, skipped.micros_status) == ("mapped", "unmatched", None)


def test_run_respects_the_daily_budget_and_survives_errors(
    session: Session, usda, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = food(session, FoodSource.custom, "Brokolice")
    client = FakeGemini()
    client.generate_responses = [RuntimeError("429 RESOURCE_EXHAUSTED")]

    assert mapper.run(session, client) == 0
    assert first.micros_status is None  # left pending for the next run

    monkeypatch.setattr(settings, "micros_mapper_daily_requests", 1)  # the failed call used it up
    client.generate_responses = [
        answer(FoodComponents(food=0, components=[Component(usda_query_en="Broccoli, raw", grams_per_100g=100)]))
    ]
    assert mapper.run(session, client) == 0
    assert len(client.generated) == 1

    monkeypatch.setattr(mapper, "budget", mapper._DailyBudget())
    assert mapper.run(session, client) == 1
    assert first.micros_status == "mapped"
    assert mapper.run(session, client) == 0 and len(client.generated) == 2  # nothing pending: no call


def test_map_from_query_needs_no_gemini_call(session: Session, usda) -> None:
    product = food(session, FoodSource.openfoodfacts, "Kuřecí prsa Albert")
    kt = food(session, FoodSource.kaloricke_tabulky, "Brokolice")
    kt.micros_status = MicrosStatus.manual

    assert mapper.map_from_query(session, product, "Chicken, broilers or fryers, breast, meat only, raw")
    assert not mapper.map_from_query(session, kt, "Broccoli, raw")  # the user's mapping stays
    assert not mapper.map_from_query(session, food(session, FoodSource.web_estimate, "Kokos"), "Zzz qqq")
    session.commit()
    assert [r.food.id for r in refs_for(session, [product.id])[product.id]] == [usda["chicken"].id]  # type: ignore[index, list-item]


def test_autofill_prefers_usda_for_a_basic_food(client: TestClient, usda, gemini, off_hits) -> None:
    gemini.generate_responses = [
        SimpleNamespace(
            parsed=AutofillAnswer(
                name_cs="Brokolice",
                usda_query_en="Broccoli, raw",
                estimate=Estimate(kcal=30, protein_g=3, carbs_g=5, fat_g=0.3),
                components=[Component(usda_query_en="Broccoli, raw", grams_per_100g=100)],
            )
        )
    ]

    body = client.post("/api/nutrition/foods/autofill", json={"name_cs": "brokolice"}).json()

    assert (body["source"], body["source_label"], body["values"]["kcal"]) == ("usda", "Broccoli, raw", 100)
    assert body["micro_refs"] == [{"ref_food_id": usda["broccoli"].id, "grams_per_g": 1, "name": "Broccoli, raw"}]


def test_autofill_uses_off_for_a_branded_product_else_the_estimate(client: TestClient, usda, gemini, off_hits) -> None:
    branded = AutofillAnswer(
        name_cs="Skyr bílý",
        is_branded=True,
        brand_search_query="Milko skyr",
        usda_query_en="Yogurt, Greek, plain, nonfat",
        estimate=Estimate(kcal=60, protein_g=11, carbs_g=4, fat_g=0.1),
        components=[Component(usda_query_en="Broccoli, raw", grams_per_100g=100)],
    )
    off_hits.append(
        {
            "code": "8594",
            "product_name": "Skyr bílý",
            "brands": ["Milko"],
            "nutriments": {
                "energy-kcal_100g": 63,
                "proteins_100g": 11,
                "carbohydrates_100g": 4,
                "fat_100g": 0.1,
                "calcium_100g": 0.12,
            },
        }
    )
    gemini.generate_responses = [SimpleNamespace(parsed=branded)]

    from_off = client.post("/api/nutrition/foods/autofill", json={"name_cs": "Skyr", "brand": "Milko"}).json()

    off_hits.clear()
    gemini.generate_responses = [SimpleNamespace(parsed=branded)]
    estimated = client.post("/api/nutrition/foods/autofill", json={"name_cs": "Skyr", "brand": "Milko"}).json()

    assert (from_off["source"], from_off["source_label"], from_off["values"]["kcal"]) == (
        "openfoodfacts", "Skyr bílý (Milko)", 63,
    )  # fmt: skip
    assert from_off["micronutrients"] == {"calcium_mg": 120.0}
    assert (estimated["source"], estimated["values"]["kcal"], estimated["values"]["fiber_g"]) == ("estimate", 60, None)
    assert [r["ref_food_id"] for r in estimated["micro_refs"]] == [usda["broccoli"].id]


def test_autofill_reports_gemini_failure(client: TestClient, gemini) -> None:
    gemini.generate_responses = [RuntimeError("429")]

    response = client.post("/api/nutrition/foods/autofill", json={"name_cs": "Brokolice"})

    assert response.status_code == 503


def test_food_routes_save_and_show_references(client: TestClient, session: Session, usda) -> None:
    chicken, broccoli = usda["chicken"].id, usda["broccoli"].id
    created = client.post(
        "/api/nutrition/foods",
        json={"name_cs": "Kuře s brokolicí", "kcal": 90, "protein_g": 15, "carbs_g": 2, "fat_g": 2,
              "micro_refs": [{"ref_food_id": chicken, "grams_per_g": 0.6},
                             {"ref_food_id": broccoli, "grams_per_g": 0.3}]},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["micros_status"] == "mapped"
    assert [r["name"] for r in body["micro_refs"]] == [
        "Chicken, broilers or fryers, breast, meat only, raw",
        "Broccoli, raw",
    ]
    assert body["borrowed"] == {"fiber_g": 0.78, "iron_mg": 0.24, "vitamin_c_mg": 26.76}

    edited = client.patch(
        f"/api/nutrition/foods/{body['id']}", json={"micro_refs": [{"ref_food_id": broccoli, "grams_per_g": 1}]}
    ).json()
    listed = client.get("/api/nutrition/foods", params={"q": "brokolici"}).json()
    itself = {"micro_refs": [{"ref_food_id": body["id"], "grams_per_g": 1}]}
    bad = client.patch(f"/api/nutrition/foods/{body['id']}", json=itself)

    assert (edited["micros_status"], edited["borrowed"]) == ("manual", {"fiber_g": 2.6, "vitamin_c_mg": 89.2})
    assert next(f for f in listed if f["id"] == body["id"])["borrowed"]["vitamin_c_mg"] == 89.2
    assert bad.status_code == 422


def test_confirmed_draft_maps_a_new_off_food_from_its_query(client: TestClient, session: Session, usda) -> None:
    response = client.post(
        "/api/nutrition/drafts/confirm",
        json={
            "id": str(uuid.uuid4()),
            "meal_type": "lunch",
            "items": [
                {
                    "input": {
                        "user_phrase": "kuřecí prsa",
                        "canonical_name_cs": "Kuřecí prsa Albert",
                        "amount_g": 150,
                        "usda_query_en": "Chicken, broilers or fryers, breast, meat only, raw",
                    },
                    "candidate": {
                        "ref": "web",
                        "name": "Kuřecí prsa Albert",
                        "source": "web_estimate",
                        "per_100g": {"kcal": 110, "protein_g": 23, "carbs_g": 0, "fat_g": 1.5},
                    },
                    "amount_g": 150,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    food_id = response.json()["items"][0]["food_id"]

    created = client.get(f"/api/nutrition/foods/{food_id}").json()
    assert (created["source"], created["micros_status"]) == ("web_estimate", "mapped")
    assert created["borrowed"] == {"iron_mg": 0.4}


def test_nutrients_lists_labels_in_order(client: TestClient) -> None:
    nutrients = client.get("/api/nutrition/nutrients").json()

    assert nutrients[0] == {"key": "kcal", "label": "Energie", "unit": "kcal", "micro": False, "reference": 2000}
    assert {"key": "iron_mg", "label": "Železo", "unit": "mg", "micro": True, "reference": 14} in nutrients


@pytest.mark.parametrize("schema", [list[FoodComponents], AutofillAnswer], ids=["mapper", "autofill"])
def test_response_schemas_convert_for_gemini(schema) -> None:
    """google-genai rejects some JSON-schema keywords (e.g. exclusiveMinimum from gt=) before sending anything."""
    from google.genai import _transformers, client

    _transformers.t_schema(client.Client(api_key="test")._api_client, schema)
