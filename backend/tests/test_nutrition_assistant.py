"""Nutrition assistant (Phase 5.4b) against the fake Gemini client: hybrid save, drafts, chooser, estimates."""

import datetime as dt
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fakes import FakeGemini
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import settings
from app.main import app
from app.models.nutrition import Food, FoodAlias, FoodSource, MealLog, MealLogItem, RecipeComponent
from app.routers.ai_coach import gemini_client
from app.routers.nutrition import get_http
from app.services.nutrition.assistant import Pick, parse_estimate
from app.services.nutrition.lookup import Ingredient, RecipePlan
from app.services.nutrition.resolver import MealItemInput, normalize


@pytest.fixture(autouse=True)
def models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gemini_model_fast", "fast-model")
    monkeypatch.setattr(settings, "gemini_model_smart", None)
    monkeypatch.setattr(settings, "gemini_model_fallbacks", None)


@pytest.fixture(autouse=True)
def web() -> dict[str, str]:
    """No real network: the recipe search and pages answer from this dict (url → html), everything else 404s."""
    pages: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.duckduckgo.com":
            links = "".join(f'<a class="result__a" href="{url}">r</a>' for url in pages)
            return httpx.Response(200, text=links)
        if (page := pages.get(str(request.url))) is not None:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page)
        return httpx.Response(404)

    app.dependency_overrides[get_http] = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    yield pages
    app.dependency_overrides.pop(get_http, None)


@pytest.fixture
def fake():
    def make(**kwargs) -> FakeGemini:
        client = FakeGemini(**kwargs)
        app.dependency_overrides[gemini_client] = lambda: client
        return client

    yield make
    app.dependency_overrides.pop(gemini_client, None)


def food(session: Session, **fields) -> Food:
    values = {"source": FoodSource.usda, "kcal": 120.0, "protein_g": 20.0, "carbs_g": 0.0, "fat_g": 4.0} | fields
    row = Food(**values)
    session.add(row)
    session.commit()
    return row


def item(phrase: str, canonical: str, grams: float, **fields) -> MealItemInput:
    return MealItemInput(user_phrase=phrase, canonical_name_cs=canonical, amount_g=grams, **fields)


def chat(client: TestClient, message: str = "Oběd: 200 g kuřecích stehen") -> dict:
    response = client.post("/api/nutrition/chat", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def test_known_confirmed_foods_are_saved_directly(client: TestClient, session: Session, fake) -> None:
    thigh = food(session, name_en="Chicken, thigh, meat only, raw", name_cs="Kuřecí stehno, syrové")
    session.add(FoodAlias(alias_normalized=normalize("kuřecích stehen"), food_id=thigh.id, confirmed=True))
    session.commit()
    gemini = fake(calls=[("log_meal_from_items", {"meal_type": "lunch", "items": [item("kuřecích stehen", "x", 200)]})])

    result = chat(client)

    assert result["drafts"] == []
    [saved] = result["saved_meals"]
    assert saved["items"] == [{"food": "Kuřecí stehno, syrové", "grams": 200, "kcal": 240}]
    assert gemini.results[0]["status"] == "saved"
    assert gemini.generated == []  # no chooser call needed
    meal = session.get(MealLog, uuid.UUID(saved["meal_id"]))
    assert meal is not None and meal.raw_user_input == "Oběd: 200 g kuřecích stehen"


def test_unknown_foods_become_a_draft_with_the_chosen_candidate(client: TestClient, session: Session, fake) -> None:
    raw = food(session, name_en="Chicken, broilers or fryers, dark meat, thigh, meat only, raw")
    food(session, name_en="Chicken, thigh, meat and skin, raw")
    lard = food(session, name_en="Lard", kcal=902, protein_g=0, fat_g=100)
    gemini = fake(
        calls=[
            (
                "log_meal_from_items",
                {
                    "meal_type": "lunch",
                    "items": [
                        item(
                            "kuřecích stehen",
                            "Kuřecí stehno, syrové",
                            200,
                            usda_query_en="Chicken, thigh, meat only, raw",
                        ),
                        item("lžíce sádla", "Sádlo", 13, usda_query_en="Lard"),
                    ],
                },
            )
        ]
    )
    gemini.generate_responses = [
        SimpleNamespace(parsed=[Pick(item=0, choice=0, confidence=0.92), Pick(item=1, choice=0, confidence=0.99)])
    ]

    result = chat(client)

    assert result["saved_meals"] == []
    [draft] = result["drafts"]
    assert (draft["kind"], draft["meal_type"], draft["raw_input"]) == ("meal", "lunch", "Oběd: 200 g kuřecích stehen")
    first, second = draft["items"]
    assert (first["chosen"]["ref"], first["confidence"], first["confirmed"]) == (f"food:{raw.id}", 0.92, False)
    assert second["chosen"]["ref"] == f"food:{lard.id}"
    assert gemini.results[0]["status"] == "needs_confirmation"
    assert gemini.results[0]["items"][1]["kcal"] == 117.3
    assert session.exec(select(MealLogItem)).all() == []
    assert session.exec(select(FoodAlias)).all() == []  # nothing learned before confirmation
    prompt = gemini.generated[0]["contents"]
    assert 'Položka 0: "kuřecích stehen"' in prompt and "0: Chicken, broilers or fryers" in prompt


def test_the_draft_round_trips_through_confirm(client: TestClient, session: Session, fake) -> None:
    lard = food(session, name_en="Lard", kcal=902, protein_g=0, fat_g=100)
    gemini = fake(
        calls=[
            (
                "log_meal_from_items",
                {"meal_type": "dinner", "items": [item("sádla", "Sádlo", 13, usda_query_en="Lard")]},
            )
        ]
    )
    gemini.generate_responses = [SimpleNamespace(parsed=[Pick(item=0, choice=0, confidence=0.9)])]
    [draft] = chat(client, "Večeře: lžíce sádla")["drafts"]

    body = {
        "id": str(uuid.uuid4()),
        "date": draft["date"],
        "meal_type": draft["meal_type"],
        "raw_input": draft["raw_input"],
        "items": [{"input": i["input"], "candidate": i["chosen"], "amount_g": i["amount_g"]} for i in draft["items"]],
    }
    confirmed = client.post("/api/nutrition/drafts/confirm", json=body)

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["items"][0]["food_id"] == lard.id
    assert session.get(Food, lard.id).name_cs == "Sádlo"


def test_chooser_failure_falls_back_to_the_best_scored_candidate(client: TestClient, session: Session, fake) -> None:
    lard = food(session, name_en="Lard", kcal=902, protein_g=0, fat_g=100)
    gemini = fake(
        calls=[
            ("log_meal_from_items", {"meal_type": "lunch", "items": [item("sádla", "Sádlo", 13, usda_query_en="Lard")]})
        ]
    )
    gemini.generate_responses = [RuntimeError("429 quota")]

    [draft] = chat(client)["drafts"]

    assert draft["items"][0]["chosen"]["ref"] == f"food:{lard.id}"
    assert draft["items"][0]["confidence"] is None


def test_nothing_found_asks_the_web_for_an_estimate(client: TestClient, session: Session, fake) -> None:
    gemini = fake(
        calls=[("log_meal_from_items", {"meal_type": "dinner", "items": [item("bramboráky", "Bramboráky", 150)]})]
    )
    estimate = (
        '```json\n{"name": "Bramboráky", "kcal": 230, "protein_g": 4.1, "carbs_g": 25, "fat_g": 12.5, '
        '"fiber_g": null}\n```'
    )
    gemini.generate_responses = [SimpleNamespace(text=estimate)]  # no candidates: nothing to choose from

    [draft] = chat(client, "Bramboráky 150 g")["drafts"]

    chosen = draft["items"][0]["chosen"]
    assert (chosen["ref"], chosen["source"], chosen["per_100g"]["kcal"], chosen["per_100g"]["fiber_g"]) == (
        "web",
        "web_estimate",
        230,
        None,
    )
    search_call = gemini.generated[0]["config"]
    assert search_call.tools[0].google_search is not None and search_call.response_schema is None
    assert chosen["grounded"] is True


RECIPE_PAGE = (
    '<script type="application/ld+json">{"@type": "Recipe", "name": "Bún chả", "recipeYield": "2 porce", '
    '"recipeIngredient": ["300 g bůčku", "200 g rýžových nudlí"]}</script>'
)


def bun_cha_plan() -> RecipePlan:
    ingredients = [  # 800 g finished
        Ingredient(
            name_cs="bůček", usda_query_en="Pork, fresh, belly, raw", grams=300, grams_in_dish=250, assumed=False
        ),
        Ingredient(
            name_cs="rýžové nudle", usda_query_en="Rice noodles, dry", grams=200, grams_in_dish=550, assumed=False
        ),
    ]
    return RecipePlan(ingredients=ingredients, portions=2)


def test_an_unknown_dish_is_computed_from_a_web_recipe_and_learned(
    client: TestClient, session: Session, fake, web: dict[str, str]
) -> None:
    pork = food(session, name_en="Pork, fresh, belly, raw", kcal=518, protein_g=9.3, carbs_g=0, fat_g=53)
    noodles = food(session, name_en="Rice noodles, dry", kcal=364, protein_g=6, carbs_g=80, fat_g=0.6)
    food(session, name_en="Buns, cinnamon", kcal=400)  # the kind of look-alike the USDA search offers
    web["https://www.toprecepty.cz/recept/bun-cha/"] = RECIPE_PAGE
    dish = item("bun cha", "Bún chả", 400, is_dish=True, portions=1, usda_query_en="Buns, cinnamon")
    gemini = fake(calls=[("log_meal_from_items", {"meal_type": "lunch", "items": [dish]})])
    gemini.generate_responses = [
        SimpleNamespace(parsed=[Pick(item=0, choice=0, confidence=0.3)]),
        SimpleNamespace(parsed=bun_cha_plan()),
    ]

    [draft] = chat(client, "Na oběd jsem měl bun cha")["drafts"]

    [entry] = draft["items"]
    chosen = entry["chosen"]
    assert (chosen["ref"], chosen["source"], chosen["per_100g"]["kcal"]) == ("recipe", "recipe", 285.25)
    assert chosen["recipe"]["source_url"] == "https://www.toprecepty.cz/recept/bun-cha/"
    assert entry["amount_g"] == 400  # 1 portion of 800 g / 2
    assert entry["candidates"][0]["ref"] == "recipe"
    assert "toprecepty.cz" in gemini.results[0]["items"][0]["recipe"]

    body = {
        "id": str(uuid.uuid4()),
        "date": draft["date"],
        "meal_type": draft["meal_type"],
        "items": [{"input": entry["input"], "candidate": chosen, "amount_g": entry["amount_g"]}],
    }
    confirmed = client.post("/api/nutrition/drafts/confirm", json=body)

    assert confirmed.status_code == 200, confirmed.text
    saved = session.get(Food, confirmed.json()["items"][0]["food_id"])
    assert saved is not None and (saved.source, saved.name_cs, saved.kcal) == ("recipe", "Bún chả", 285.25)
    assert {c.ingredient_food_id for c in session.exec(select(RecipeComponent))} == {pork.id, noodles.id}
    detail = client.get(f"/api/nutrition/foods/{saved.id}").json()
    assert detail["source_url"] == "https://www.toprecepty.cz/recept/bun-cha/"
    assert [(c["name"], c["amount_g"]) for c in detail["recipe_components"]] == [
        ("Pork, fresh, belly, raw", 300),
        ("Rice noodles, dry", 200),
    ]
    assert detail["portions"] == [{"label": "porce", "grams": 400}]

    gemini.generated, gemini.results = [], []
    chat(client, "Večer zase bun cha")  # learned: saved directly, no lookup
    assert gemini.results[0]["status"] == "saved" and gemini.generated == []


def test_lookup_route_computes_a_recipe_on_demand(client: TestClient, session: Session, fake) -> None:
    food(session, name_en="Pork, fresh, belly, raw", kcal=518, protein_g=9.3, carbs_g=0, fat_g=53)
    food(session, name_en="Rice noodles, dry", kcal=364, protein_g=6, carbs_g=80, fat_g=0.6)
    gemini = fake()
    gemini.generate_responses = [SimpleNamespace(parsed=bun_cha_plan())]
    entry = item("bun cha", "Bún chả", 350, portions=2).model_dump()

    response = client.post("/api/nutrition/lookup", json=entry)

    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["candidate"]["ref"], result["candidate"]["recipe"]["source_url"]) == ("recipe", None)
    assert result["amount_g"] == 800  # 2 portions of 400 g
    assert "Recept nemáme" in gemini.generated[0]["contents"]  # the search found nothing


def test_lookup_route_reports_a_dish_it_cannot_compute(client: TestClient, fake) -> None:
    gemini = fake()
    gemini.generate_responses = [SimpleNamespace(parsed=bun_cha_plan())]  # no USDA foods in the test database

    response = client.post("/api/nutrition/lookup", json=item("bun cha", "Bún chả", 350).model_dump())

    assert response.status_code == 404


def test_summary_tool_reports_nutrients_with_coverage(client: TestClient, session: Session, fake) -> None:
    rice = food(
        session, name_en="Rice, cooked", kcal=130, protein_g=2.7, carbs_g=28, fat_g=0.3, micronutrients={"iron_mg": 0.2}
    )
    client.put(f"/api/nutrition/items/{uuid.uuid4()}", json={"food_id": rice.id, "amount_g": 200, "meal_type": "lunch"})
    gemini = fake(calls=[("get_daily_nutrition_summary", {})])

    chat(client, "Kolik mám dnes železa?")

    result = gemini.results[0]
    iron = next(n for n in result["nutrients"] if n["name"] == "Železo")
    assert (iron["amount"], iron["coverage"], iron["target"]) == (0.4, 1.0, 14)
    assert result["meals"][0]["items"][0] == {"name": "Rice, cooked", "grams": 200, "kcal": 260}


def test_prompt_lists_known_foods_with_typical_portions(client: TestClient, session: Session, fake) -> None:
    skyr = food(session, source=FoodSource.custom, name_cs="Skyr bílý", kcal=63)
    for grams in (140, 140, 200):
        client.put(f"/api/nutrition/items/{uuid.uuid4()}", json={"food_id": skyr.id, "amount_g": grams})
    gemini = fake()

    chat(client, "Ahoj")

    instruction = gemini.created[0]["config"].system_instruction
    assert f"{skyr.id} | Skyr bílý | 140 g" in instruction
    assert "místního času" in instruction


def test_conversations_belong_to_one_assistant(client: TestClient, fake) -> None:
    fake()
    coach = client.post("/api/ai/chat", json={"message": "Ahoj"}).json()

    response = client.post("/api/nutrition/chat", json={"message": "Ahoj", "conversation_id": coach["conversation_id"]})

    assert response.status_code == 409


def test_voice_route_takes_audio(client: TestClient, fake) -> None:
    gemini = fake()
    recording = (Path(__file__).parent / "fixtures" / "recording-chrome.webm").read_bytes()

    response = client.post("/api/nutrition/voice", files={"audio": ("rec.webm", recording, "audio/webm")})

    assert response.status_code == 200, response.text
    audio_part, text_part = gemini.sent[0]
    assert audio_part.inline_data.mime_type == "audio/flac"
    assert "snědené jídlo" in text_part.text


def test_parse_estimate_needs_the_required_macros() -> None:
    entry = item("x", "X", 100)

    assert parse_estimate('{"kcal": 100, "protein_g": 1}', entry) is None
    assert parse_estimate("nic jsem nenašel {}", entry) is None
    assert parse_estimate("not json {", entry) is None


def test_unparseable_dates_are_reported_to_the_model(client: TestClient, fake) -> None:
    gemini = fake(calls=[("get_daily_nutrition_summary", {"date": "včera"})])

    chat(client, "Co jsem jedl včera?")

    assert gemini.results[0] == {"error": "date must be YYYY-MM-DD"}


def test_meals_go_to_the_day_open_in_the_app(client: TestClient, session: Session, fake) -> None:
    food(session, source=FoodSource.custom, name_cs="Tvaroh", kcal=98)
    gemini = fake(calls=[("log_meal_from_items", {"meal_type": "other", "items": [item("tvaroh", "Tvaroh", 200)]})])

    response = client.post("/api/nutrition/chat", json={"message": "200 g tvarohu", "date": "2026-10-10"})

    [saved] = response.json()["saved_meals"]
    assert saved["date"] == "2026-10-10"
    assert session.get(MealLog, uuid.UUID(saved["meal_id"])).logged_date == dt.date(2026, 10, 10)
    assert "2026-10-10" in gemini.created[0]["config"].system_instruction


def test_voice_meals_go_to_the_day_open_in_the_app(client: TestClient, session: Session, fake) -> None:
    food(session, source=FoodSource.custom, name_cs="Tvaroh", kcal=98)
    fake(calls=[("log_meal_from_items", {"meal_type": "other", "items": [item("tvaroh", "Tvaroh", 200)]})])

    response = client.post("/api/nutrition/voice", data={"text": "200 g tvarohu", "date": "2026-10-10"})

    assert response.json()["saved_meals"][0]["date"] == "2026-10-10"


def test_an_explicit_date_beats_the_open_day(client: TestClient, session: Session, fake) -> None:
    food(session, source=FoodSource.custom, name_cs="Tvaroh", kcal=98)
    call = {"meal_type": "other", "date": "2026-10-01", "items": [item("tvaroh", "Tvaroh", 200)]}
    fake(calls=[("log_meal_from_items", call)])

    response = client.post("/api/nutrition/chat", json={"message": "před týdnem tvaroh", "date": "2026-10-10"})

    assert response.json()["saved_meals"][0]["date"] == "2026-10-01"


def test_meal_on_a_given_date(client: TestClient, session: Session, fake) -> None:
    food(session, source=FoodSource.custom, name_cs="Skyr bílý", kcal=63)
    fake(
        calls=[
            (
                "log_meal_from_items",
                {"meal_type": "breakfast", "date": "2026-10-01", "items": [item("skyr", "Skyr bílý", 140)]},
            )
        ]
    )

    [saved] = chat(client, "Včera skyr")["saved_meals"]

    assert saved["date"] == "2026-10-01"
    assert session.get(MealLog, uuid.UUID(saved["meal_id"])).logged_date == dt.date(2026, 10, 1)


def test_nutrition_and_helpers_use_their_own_models(
    client: TestClient, session: Session, fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "gemini_model_nutrition", "nutrition-model")
    monkeypatch.setattr(settings, "gemini_model_lite", "lite-model")
    food(session, name_en="Lard", kcal=902, protein_g=0, fat_g=100)
    gemini = fake(
        calls=[
            ("log_meal_from_items", {"meal_type": "lunch", "items": [item("sádla", "Sádlo", 13, usda_query_en="Lard")]})
        ]
    )
    gemini.generate_responses = [SimpleNamespace(parsed=[Pick(item=0, choice=0, confidence=0.9)])]

    chat(client)
    gemini.calls = []  # the coach turn calls no tools
    client.post("/api/ai/chat", json={"message": "Ahoj"})

    assert [c["model"] for c in gemini.created] == ["nutrition-model", "fast-model"]
    assert gemini.generated[0]["model"] == "lite-model"


def test_estimate_falls_back_to_the_models_own_knowledge(client: TestClient, session: Session, fake) -> None:
    gemini = fake(
        calls=[("log_meal_from_items", {"meal_type": "dinner", "items": [item("bramboráky", "Bramboráky", 150)]})]
    )
    known = '{"name": "Bramboráky", "kcal": 230, "protein_g": 4, "carbs_g": 25, "fat_g": 12.5}'
    gemini.generate_responses = [
        RuntimeError("429: search grounding not in the free tier"),
        SimpleNamespace(text=known),
    ]

    [draft] = chat(client, "Bramboráky 150 g")["drafts"]

    chosen = draft["items"][0]["chosen"]
    assert (chosen["source"], chosen["grounded"]) == ("web_estimate", False)
    grounded_call, plain_call = gemini.generated[0]["config"], gemini.generated[1]["config"]
    assert grounded_call.tools and not plain_call.tools
    assert "Odhadni" in gemini.generated[1]["contents"]


def test_tools_accept_arguments_the_way_the_sdk_converts_them(session: Session) -> None:
    """AFC converts the model's JSON args with the SDK's own helpers; a top-level Literal broke that (live check)."""
    from google.genai import _extra_utils

    from app.services.nutrition.assistant import NutritionContext, build_nutrition_tools
    from app.services.nutrition.resolver import TopScoreChooser

    food(session, name_en="Lard", kcal=902, protein_g=0, fat_g=100)
    ctx = NutritionContext(session=session, http=None, chooser_factory=TopScoreChooser)
    log_meal, summary = build_nutrition_tools(ctx)
    args = {
        "meal_type": "lunch",
        "items": [
            {"user_phrase": "lžíci sádla", "canonical_name_cs": "Sádlo", "amount_g": 13, "usda_query_en": "Lard"}
        ],
    }

    result = _extra_utils.invoke_function_from_dict_args(args, log_meal)
    bad = _extra_utils.invoke_function_from_dict_args({"meal_type": "brunch", "items": args["items"]}, log_meal)

    assert result["status"] == "needs_confirmation"
    assert "meal_type must be one of" in bad["error"]
    assert "nutrients" in _extra_utils.invoke_function_from_dict_args({}, summary)
