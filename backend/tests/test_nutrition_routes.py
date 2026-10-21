"""Nutrition routes (Phase 5.4a): summary with coverage, food items, food database, barcode, profile, drafts."""

import datetime as dt
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.models.gym import Workout
from app.models.nutrition import Food, FoodAlias, FoodSource, MicrosStatus
from app.routers.nutrition import get_http
from app.services.nutrition.micro_refs import set_refs
from app.timeutils import day_bounds

D = dt.date(2026, 10, 10)


def food(session: Session, source: FoodSource = FoodSource.usda, micros: dict | None = None, **fields) -> Food:
    values = {"kcal": 100.0, "protein_g": 10.0, "carbs_g": 10.0, "fat_g": 2.0} | fields
    row = Food(source=source, micronutrients=micros or {}, **values)
    session.add(row)
    session.commit()
    return row


def put_item(client: TestClient, food_id: int, grams: float, item_id: uuid.UUID | None = None, **fields) -> dict:
    body = {"food_id": food_id, "amount_g": grams, "date": D.isoformat(), "meal_type": "lunch"} | fields
    response = client.put(f"/api/nutrition/items/{item_id or uuid.uuid4()}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def nutrient(summary: dict, key: str) -> dict:
    return next(n for n in summary["nutrients"] if n["key"] == key)


@pytest.fixture
def off_http():
    responses: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.get(request.url.path, httpx.Response(404))

    app.dependency_overrides[get_http] = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    yield responses
    app.dependency_overrides.pop(get_http, None)


def test_items_upsert_join_the_meal_and_edit_in_place(client: TestClient, session: Session) -> None:
    rice = food(session, name_en="Rice, cooked", kcal=130)
    item_id = uuid.uuid4()

    first = put_item(client, rice.id, 200, item_id)
    put_item(client, rice.id, 100)
    edited = put_item(client, rice.id, 150, item_id)
    day = client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()

    assert (first["kcal"], first["food_name"], first["food_source"]) == (260, "Rice, cooked", "usda")
    assert edited["kcal"] == 195
    assert len(day["meals"]) == 1 and len(day["meals"][0]["items"]) == 2
    assert day["totals"]["kcal"] == 325


def test_moving_an_item_joins_the_other_meal_and_drops_the_empty_one(client: TestClient, session: Session) -> None:
    chicken, rice = food(session, name_en="Chicken"), food(session, name_en="Rice")
    moved = uuid.uuid4()
    put_item(client, chicken.id, 150, moved)
    put_item(client, rice.id, 100, meal_type="breakfast")

    for _ in range(2):  # idempotent
        response = client.post(f"/api/nutrition/items/{moved}/move", json={"meal_type": "breakfast"})
        assert response.status_code == 200, response.text
    day = client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()
    to_empty = client.post(f"/api/nutrition/items/{moved}/move", json={"meal_type": "dinner"})
    after = client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()

    assert response.json()["kcal"] == 150
    assert [(m["meal_type"], len(m["items"])) for m in day["meals"]] == [("breakfast", 2)]
    assert to_empty.status_code == 200
    assert [(m["meal_type"], len(m["items"])) for m in after["meals"]] == [("breakfast", 1), ("dinner", 1)]
    assert client.post(f"/api/nutrition/items/{uuid.uuid4()}/move", json={"meal_type": "lunch"}).status_code == 404


def test_summary_reports_coverage_and_borrows_reference_micros(client: TestClient, session: Session) -> None:
    chicken = food(session, micros={"iron_mg": 1.0, "vitamin_c_mg": 0.0}, kcal=200, name_en="Chicken")
    pepper = food(session, micros={"iron_mg": 2.0, "vitamin_c_mg": 100.0}, kcal=30, name_en="Pepper")
    ham = food(session, FoodSource.openfoodfacts, micros={"vitamin_c_mg": 5.0}, kcal=100, name_cs="Šunka")
    set_refs(session, ham, [(chicken.id, 0.5), (pepper.id, 0.25)], MicrosStatus.mapped)
    session.commit()
    plain = food(session, FoodSource.kaloricke_tabulky, kcal=100, name_cs="Chléb")  # no micros at all
    put_item(client, chicken.id, 100)  # 200 kcal, iron 1.0
    put_item(client, ham.id, 100)  # 100 kcal, iron 0.5 + 0.5 borrowed, its own vitamin C wins
    put_item(client, plain.id, 100)  # 100 kcal, iron unknown
    client.post("/api/nutrition/quick-add", json={"id": str(uuid.uuid4()), "date": D.isoformat(), "kcal": 100})

    summary = client.get("/api/nutrition/summary", params={"date": D.isoformat()}).json()

    iron = nutrient(summary, "iron_mg")
    assert (iron["amount"], iron["coverage"], iron["target"]) == (2.0, 0.6, 14)
    assert nutrient(summary, "vitamin_c_mg")["amount"] == 5.0
    assert iron["sources"] == [
        {"name": "Chicken", "amount": 1.0, "estimated": False},
        {"name": "Šunka", "amount": 1.0, "estimated": True},
    ]
    assert iron["unknown"] == ["Chléb", "Rychlý zápis"]
    assert nutrient(summary, "kcal")["amount"] == 500
    assert nutrient(summary, "fiber_g") | {"label": None, "unknown": None} == {
        "key": "fiber_g", "label": None, "unit": "g", "amount": None, "coverage": 0.0, "target": 25, "percent": None,
        "sources": [], "unknown": None,
    }  # fmt: skip
    assert summary["training_day"] is False


def test_profile_base_is_the_target_without_runs(client: TestClient, session: Session) -> None:
    client.put("/api/nutrition/profile", json={"kcal_target": 2400, "protein_target_g": 175, "fat_target_g": 50})
    start, _ = day_bounds(D)
    session.add(Workout(id=uuid.uuid4(), name="Push", started_at=start + dt.timedelta(hours=17)))
    session.commit()

    summary = client.get("/api/nutrition/summary", params={"date": "2026-11-02"}).json()
    assert nutrient(summary, "kcal")["target"] == 2400  # the gym adds nothing (E41)
    assert nutrient(summary, "carbs_g")["target"] == 313  # (2400 - 175·4 - 50·9) / 4, half up
    assert client.get("/api/nutrition/profile").json()["kcal_target"] == 2400
    gym_day = client.get("/api/nutrition/summary", params={"date": D.isoformat()}).json()
    assert gym_day["training_day"] is True


def test_food_database_search_create_edit_and_guarded_delete(client: TestClient, session: Session) -> None:
    food(session, name_en="Potatoes, boiled, cooked in skin")
    created = client.post(
        "/api/nutrition/foods",
        json={"name_cs": "Rohlík tukový", "kcal": 290, "protein_g": 9, "carbs_g": 52, "fat_g": 5,
              "micronutrients": {"iron_mg": 1.1, "made_up": 5}, "portions": [{"label": "1 rohlík", "grams": 43}]},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    roll = created.json()

    by_czech = client.get("/api/nutrition/foods", params={"q": "rohlik"}).json()
    by_english = client.get("/api/nutrition/foods", params={"q": "potato boiled"}).json()
    patched = client.patch(f"/api/nutrition/foods/{roll['id']}", json={"kcal": 295, "fiber_g": 2.4}).json()
    put_item(client, roll["id"], 43)
    used = client.delete(f"/api/nutrition/foods/{roll['id']}")

    assert (roll["source"], roll["micronutrients"], roll["portions"]) == (
        "custom",
        {"iron_mg": 1.1},
        [{"label": "1 rohlík", "grams": 43}],
    )
    assert by_czech[0]["name"] == "Rohlík tukový"
    assert by_english[0]["name"] == "Potatoes, boiled, cooked in skin"
    assert (patched["kcal"], patched["fiber_g"], patched["protein_g"]) == (295, 2.4, 9)
    assert used.status_code == 409
    assert client.get("/api/nutrition/foods").json()[0]["use_count"] == 1


def test_barcode_uses_the_local_food_then_open_food_facts(client: TestClient, session: Session, off_http) -> None:
    local = food(session, FoodSource.custom, name_cs="Můj skyr", ean="11111111")
    off_http["/api/v2/product/8594033403478.json"] = httpx.Response(
        200,
        json={"status": 1, "product": {"code": "8594033403478", "product_name": "Smetanový jogurt bílý",
              "brands": "Clever", "nutriments": {"energy-kcal_100g": 115, "proteins_100g": 3,
                                                  "carbohydrates_100g": 3.3, "fat_100g": 10}}},
    )  # fmt: skip
    off_http["/api/v2/product/2222222222222.json"] = httpx.Response(
        200, json={"status": 1, "product": {"code": "2222222222222", "product_name": "Bez hodnot", "nutriments": {}}}
    )

    assert client.get("/api/nutrition/barcode/11111111").json()["id"] == local.id
    fetched = client.get("/api/nutrition/barcode/8594033403478").json()
    assert (fetched["source"], fetched["brand"], fetched["kcal"]) == ("openfoodfacts", "Clever", 115)
    assert session.exec(select(Food).where(Food.ean == "8594033403478")).one()
    assert client.get("/api/nutrition/barcode/9999999999999").status_code == 404
    incomplete = client.get("/api/nutrition/barcode/2222222222222")
    assert incomplete.status_code == 422 and incomplete.json()["detail"]["name"] == "Bez hodnot"


def test_confirming_a_draft_saves_once_and_learns_aliases(client: TestClient, session: Session) -> None:
    thigh = food(session, name_en="Chicken, thigh, meat only, raw", kcal=120)
    meal_id = uuid.uuid4()
    body = {
        "id": str(meal_id),
        "date": D.isoformat(),
        "meal_type": "lunch",
        "raw_input": "200 g kuřecích stehen a skyr",
        "items": [
            {
                "input": {"user_phrase": "kuřecích stehen", "canonical_name_cs": "Kuřecí stehno, syrové",
                          "amount_g": 200},
                "candidate": {"ref": f"food:{thigh.id}", "name": thigh.name, "source": "usda",
                              "per_100g": {"kcal": 120}},
                "amount_g": 200,
            },
            {
                "input": {"user_phrase": "skyr", "canonical_name_cs": "Skyr bílý (Milko)", "amount_g": 140},
                "candidate": {"ref": "off:8590000000001", "name": "Skyr bílý", "source": "openfoodfacts",
                              "brand": "Milko", "per_100g": {"kcal": 63, "protein_g": 11, "carbs_g": 4,
                                                             "fat_g": 0.2}},
                "amount_g": 140,
            },
        ],
    }  # fmt: skip

    first = client.post("/api/nutrition/drafts/confirm", json=body)
    again = client.post("/api/nutrition/drafts/confirm", json=body)

    assert first.status_code == 200, first.text
    meal = first.json()
    assert again.json() == meal
    assert [(i["label"], i["kcal"]) for i in meal["items"]] == [("kuřecích stehen", 240), ("skyr", 88.2)]
    aliases = {a.alias_normalized for a in session.exec(select(FoodAlias).where(FoodAlias.confirmed))}
    assert aliases == {"kurecich stehen", "kureci stehno, syrove", "skyr", "skyr bily (milko)"}
    assert session.get(Food, thigh.id).name_cs == "Kuřecí stehno, syrové"
    assert len(client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()["meals"]) == 1


def test_a_draft_with_an_unknown_food_is_rejected(client: TestClient) -> None:
    body = {
        "id": str(uuid.uuid4()),
        "items": [
            {
                "input": {"user_phrase": "x", "canonical_name_cs": "X", "amount_g": 10},
                "candidate": {"ref": "food:999999", "name": "X", "source": "usda", "per_100g": {}},
                "amount_g": 10,
            }
        ],
    }

    assert client.post("/api/nutrition/drafts/confirm", json=body).status_code == 422


def test_food_search_puts_names_starting_with_the_query_first(client: TestClient, session: Session) -> None:
    for name in ("Pepper, banana, raw", "Snacks, banana chips", "Bananas, raw"):
        food(session, name_en=name)

    names = [f["name"] for f in client.get("/api/nutrition/foods", params={"q": "banana"}).json()]

    assert names[0] == "Bananas, raw"


def test_without_a_query_the_list_shows_my_foods_not_the_usda_seed(client: TestClient, session: Session) -> None:
    eaten = food(session, name_en="Rice, cooked")
    food(session, name_en="APPLEBEE'S, chili")  # seeded, never eaten
    mine = food(session, FoodSource.custom, name_cs="Rohlík")
    put_item(client, eaten.id, 100)

    names = [f["name"] for f in client.get("/api/nutrition/foods").json()]
    usda = [f["name"] for f in client.get("/api/nutrition/foods", params={"source": "usda"}).json()]

    assert names == ["Rice, cooked", mine.name]
    assert set(usda) == {"Rice, cooked", "APPLEBEE'S, chili"}
