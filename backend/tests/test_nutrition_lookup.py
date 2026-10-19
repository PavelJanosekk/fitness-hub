"""Smart lookup (E30): DuckDuckGo results, schema.org recipes, the Gemini ingredient plan and the USDA computation.
Web pages are synthetic (same structure as the live ones checked on 2026-10-19), no network."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fakes import FakeGemini
from sqlmodel import Session

from app.config import settings
from app.models.nutrition import Food, FoodSource
from app.services.nutrition import lookup as lookup_module
from app.services.nutrition.lookup import (
    Ingredient,
    RecipePlan,
    compute,
    fetch_page,
    find_web_recipe,
    lookup_dish,
    parse_recipe,
    result_urls,
)
from app.services.nutrition.resolver import MealItemInput

TOPRECEPTY_LINK = "https%3A%2F%2Fwww.toprecepty.cz%2Frecept%2F1%2Dbun%2Dcha%2F"
SEARCH_PAGE = f"""<div class="result results_links results_links_deep result--ad">
<a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad_domain=shop.example&amp;ad_provider=x">Ad</a>
</div>
<div class="result results_links results_links_deep web-result">
<a rel="nofollow" class="result__a"
   href="//duckduckgo.com/l/?uddg={TOPRECEPTY_LINK}&amp;rut=abc">Bún chả</a>
</div>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D1">
Video</a></div>
<div class="result"><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffresh.example.cz%2Fbun-cha" class="result__a">
2</a></div>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg={TOPRECEPTY_LINK}">dup</a></div>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=http%3A%2F%2F192.168.1.10%2Fr">LAN</a></div>
"""


def recipe_page(data: object) -> str:
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head><body></body></html>'


TOPRECEPTY = recipe_page(
    {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Bún chả &amp; grilovaný bůček",
        "recipeYield": "3 porce",
        "recipeIngredient": ["300 g bůčku", "rýžové nudle <b>Bún</b>", "Na marinádu:", "2 lžíce rybí omáčky"],
        "nutrition": {"@type": "NutritionInformation", "calories": "1 550 kcal"},
    }
)


def test_result_urls_decode_the_redirect_and_skip_ads_videos_duplicates_and_addresses() -> None:
    assert result_urls(SEARCH_PAGE) == [
        "https://www.toprecepty.cz/recept/1-bun-cha/",
        "https://fresh.example.cz/bun-cha",
    ]


def test_parse_recipe_reads_the_ingredient_lines_and_ignores_the_pages_nutrition() -> None:
    recipe = parse_recipe(TOPRECEPTY, "https://www.toprecepty.cz/recept/1-bun-cha/")

    assert recipe is not None
    assert (recipe.title, recipe.servings) == ("Bún chả & grilovaný bůček", "3 porce")
    assert recipe.ingredients == ["300 g bůčku", "rýžové nudle Bún", "Na marinádu:", "2 lžíce rybí omáčky"]


@pytest.mark.parametrize(
    "data",
    [
        {"@graph": [{"@type": "WebPage"}, {"@type": ["Recipe", "NewsArticle"], "recipeIngredient": ["a", "b"]}]},
        [{"@type": "BreadcrumbList"}, {"@type": "Recipe", "recipeIngredient": ["a", "b"], "recipeYield": ["2", "2x"]}],
        {"@type": "WebPage", "mainEntity": {"@type": "Recipe", "recipeIngredient": ["a", "b"]}},
    ],
)
def test_parse_recipe_finds_nested_recipes(data: object) -> None:
    recipe = parse_recipe(recipe_page(data), "https://x.cz")

    assert recipe is not None and recipe.ingredients == ["a", "b"]


def test_parse_recipe_needs_a_recipe_with_ingredients() -> None:
    assert parse_recipe(recipe_page({"@type": "Article"}), "u") is None
    assert parse_recipe(recipe_page({"@type": "Recipe", "recipeIngredient": ["jen jedna"]}), "u") is None
    assert parse_recipe('<script type="application/ld+json">{broken</script>', "u") is None


def test_fetch_page_follows_public_redirects_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        if request.url.path == "/internal":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        if request.url.path == "/pdf":
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<p>ok</p>")

    http = httpx.Client(transport=httpx.MockTransport(handler))

    assert fetch_page(http, "https://recepty.example.cz/old") == ("https://recepty.example.cz/new", "<p>ok</p>")
    assert fetch_page(http, "https://recepty.example.cz/internal") is None
    assert fetch_page(http, "https://recepty.example.cz/pdf") is None
    assert fetch_page(http, "http://localhost/x") is None


def usda(session: Session, name_en: str, kcal: float, protein: float, carbs: float, fat: float) -> Food:
    row = Food(source=FoodSource.usda, name_en=name_en, kcal=kcal, protein_g=protein, carbs_g=carbs, fat_g=fat)
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def pantry(session: Session) -> dict[str, Food]:
    return {
        "pork": usda(session, "Pork, fresh, belly, raw", 518, 9.3, 0, 53),
        "noodles": usda(session, "Rice noodles, dry", 364, 6, 80, 0.6),
        "fish": usda(session, "Sauce, fish, ready-to-serve", 35, 5.1, 3.6, 0),
        "water": usda(session, "Beverages, water, tap, drinking", 0, 0, 0, 0),
    }


def bun_cha(**fields) -> MealItemInput:
    return MealItemInput(user_phrase="bun cha", canonical_name_cs="Bún chả", amount_g=400, is_dish=True, **fields)


def ingredient(name: str, query: str, grams: float, cooked: float | None = None, assumed: bool = False) -> Ingredient:
    in_dish = grams if cooked is None else cooked
    return Ingredient(name_cs=name, usda_query_en=query, grams=grams, grams_in_dish=in_dish, assumed=assumed)


def plan(noodles_cooked: float = 500, portions: float = 3, extra: list[Ingredient] | None = None) -> RecipePlan:
    ingredients = [
        ingredient("bůček", "Pork, fresh, belly, raw", 300, cooked=200),
        ingredient("rýžové nudle", "Rice noodles, dry", 200, cooked=noodles_cooked, assumed=True),
        ingredient("rybí omáčka", "Sauce, fish, ready-to-serve", 30),
        ingredient("voda", "Beverages, water, tap, drinking", 170),
        ingredient("sůl", "Salt, table", 0, assumed=True),  # zero: skipped
    ]
    return RecipePlan(ingredients=ingredients + (extra or []), portions=portions)


def test_compute_sums_the_usda_ingredients_over_the_finished_weight(session: Session, pantry: dict[str, Food]) -> None:
    # finished: 200 g pork + 500 g noodles + 30 g sauce + 170 g water = 900 g
    candidate = compute(session, bun_cha(), plan(), "https://www.toprecepty.cz/recept/1-bun-cha/")

    assert candidate is not None
    assert (candidate.ref, candidate.source, candidate.name) == ("recipe", "recipe", "Bún chả")
    # (518 * 300 + 364 * 200 + 35 * 30) / 900
    assert candidate.per_100g["kcal"] == 254.72
    assert candidate.per_100g["sugar_g"] is None  # optional macros come from the references once saved
    recipe = candidate.recipe
    assert recipe is not None
    assert (recipe["yield_g"], recipe["portion_g"], recipe["source_url"]) == (
        900,
        300,
        "https://www.toprecepty.cz/recept/1-bun-cha/",
    )
    noodles = next(i for i in recipe["ingredients"] if i["name"] == "rýžové nudle")
    assert (noodles["food_id"], noodles["assumed"], noodles["grams"]) == (pantry["noodles"].id, True, 200)
    assert [i["name"] for i in recipe["ingredients"]] == ["bůček", "rýžové nudle", "rybí omáčka", "voda"]


def test_compute_keeps_the_finished_weight_plausible(session: Session, pantry: dict[str, Food]) -> None:
    shrunk = plan(portions=0)
    for item in shrunk.ingredients:
        item.grams_in_dish = 1  # 4 g of finished dish from 700 g of ingredients
    candidate = compute(session, bun_cha(), shrunk, None)

    assert candidate is not None and candidate.recipe is not None
    assert (candidate.recipe["yield_g"], candidate.recipe["portion_g"]) == (700, 700)  # raw mass, one portion


def test_compute_refuses_a_dish_that_mostly_doesnt_resolve(session: Session, pantry: dict[str, Food]) -> None:
    unknown = [ingredient("tajná směs", "Zzz qqq", 400)]

    assert compute(session, bun_cha(), plan(extra=unknown), None) is None


@pytest.fixture
def lite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gemini_model_lite", "lite-model")


def web(pages: dict[str, str], search_status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.duckduckgo.com":
            assert request.url.params["q"] == "Bún chả recept"
            return httpx.Response(search_status, text=SEARCH_PAGE)
        if (page := pages.get(str(request.url))) is not None:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lookup_computes_the_first_web_recipe(session: Session, pantry: dict[str, Food], lite: None) -> None:
    gemini = FakeGemini()
    gemini.generate_responses = [SimpleNamespace(parsed=plan())]
    http = web({"https://fresh.example.cz/bun-cha": TOPRECEPTY})  # the first result has no recipe (404)

    candidate = lookup_dish(session, http, gemini, bun_cha())

    assert candidate is not None and candidate.recipe is not None
    assert candidate.recipe["source_url"] == "https://fresh.example.cz/bun-cha"
    [call] = gemini.generated
    assert call["model"] == "lite-model" and call["config"].response_schema is RecipePlan
    assert "- 300 g bůčku" in call["contents"] and "počet porcí: 3 porce" in call["contents"]
    assert "1 550" not in call["contents"]  # the page's own nutrition is ignored


def test_without_a_web_recipe_gemini_writes_a_typical_one(
    session: Session, pantry: dict[str, Food], lite: None
) -> None:
    gemini = FakeGemini()
    gemini.generate_responses = [SimpleNamespace(parsed=plan(portions=1))]

    candidate = lookup_dish(session, web({}, search_status=202), gemini, bun_cha())

    assert candidate is not None and candidate.recipe is not None
    assert (candidate.recipe["source_url"], candidate.recipe["portion_g"]) == (None, 900)
    assert "Recept nemáme" in gemini.generated[0]["contents"]


def test_a_bot_check_pauses_the_search_and_found_recipes_are_reused() -> None:
    requests: list[str] = []
    blocked = {"on": True}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        if request.url.host == "html.duckduckgo.com":
            return httpx.Response(202 if blocked["on"] else 200, text=SEARCH_PAGE)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=TOPRECEPTY)

    http = httpx.Client(transport=httpx.MockTransport(handler))

    assert find_web_recipe(http, "Bún chả") is None
    blocked["on"] = False
    assert find_web_recipe(http, "Bún chả") is None  # paused: not asked again
    assert requests == ["html.duckduckgo.com"]

    lookup_module.state.paused_until = None
    first = find_web_recipe(http, "Bún chả")
    again = find_web_recipe(http, "bun cha")

    assert first is not None and again is first
    assert requests == ["html.duckduckgo.com", "html.duckduckgo.com", "www.toprecepty.cz"]


def test_gemini_errors_propagate_to_the_caller(session: Session, lite: None) -> None:
    gemini = FakeGemini()
    gemini.generate_responses = [RuntimeError("429 quota")]

    with pytest.raises(RuntimeError):
        lookup_dish(session, None, gemini, bun_cha())
