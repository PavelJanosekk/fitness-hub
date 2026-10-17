"""Food resolver (Phase 5.3): confirmed paths, candidates, chooser, aliases only on confirmation."""

import datetime as dt

import httpx
import pytest
from sqlmodel import Session, select

from app.models.nutrition import Food, FoodAlias, FoodSource, MealLog, MealLogItem
from app.services.nutrition.resolver import (
    Candidate,
    MealItemInput,
    Resolution,
    TopScoreChooser,
    confirm_aliases,
    materialize,
    normalize,
    resolve_items,
    search_usda,
)


class FakeChooser:
    def __init__(self, picks: list[tuple[int | None, float | None]] | None = None, estimate: Candidate | None = None):
        self.picks, self.estimate_result, self.seen = picks, estimate, []

    def choose(self, resolutions: list[Resolution]) -> list[tuple[int | None, float | None]]:
        self.seen.append(resolutions)
        return self.picks or [(0, 0.9) for _ in resolutions]

    def estimate(self, item: MealItemInput) -> Candidate | None:
        return self.estimate_result


def food(session: Session, source: FoodSource = FoodSource.usda, **fields) -> Food:
    row = Food(source=source, kcal=100, protein_g=10, carbs_g=10, fat_g=1, **fields)
    session.add(row)
    session.commit()
    return row


def item(phrase: str = "kuřecích stehen", canonical: str = "Kuřecí stehno, syrové", **fields) -> MealItemInput:
    return MealItemInput(user_phrase=phrase, canonical_name_cs=canonical, amount_g=200, **fields)


@pytest.fixture
def usda(session: Session) -> dict[str, Food]:
    names = [
        "Chicken, broilers or fryers, dark meat, thigh, meat only, raw",
        "Chicken, thigh, meat and skin, raw",
        "Potatoes, boiled, cooked in skin, flesh, without salt",
        "Lard",
    ]
    return {n: food(session, name_en=n) for n in names}


def test_normalize_is_lowercase_without_diacritics_and_extra_spaces() -> None:
    assert normalize("  Kuřecí   STEHNO, syrové ") == "kureci stehno, syrove"


def test_usda_search_ranks_full_coverage_first(session: Session, usda: dict[str, Food]) -> None:
    hits = search_usda(session, "Chicken, thigh, meat only, raw")

    assert hits[0][0].name_en == "Chicken, broilers or fryers, dark meat, thigh, meat only, raw"


def test_a_confirmed_alias_resolves_without_choosing(session: Session, usda: dict[str, Food]) -> None:
    thigh = usda["Chicken, broilers or fryers, dark meat, thigh, meat only, raw"]
    session.add(FoodAlias(alias_normalized=normalize("kuřecích stehen"), food_id=thigh.id, confirmed=True))
    session.commit()
    chooser = FakeChooser()

    [r] = resolve_items(session, None, [item()], chooser)

    assert (r.confirmed, r.via, r.food) == (True, "alias", thigh)
    assert chooser.seen == []


def test_an_unconfirmed_alias_does_not_confirm(session: Session, usda: dict[str, Food]) -> None:
    thigh = usda["Chicken, broilers or fryers, dark meat, thigh, meat only, raw"]
    session.add(FoodAlias(alias_normalized=normalize("kuřecích stehen"), food_id=thigh.id, confirmed=False))
    session.commit()

    [r] = resolve_items(session, None, [item(usda_query_en="Chicken, thigh, meat only, raw")], FakeChooser())

    assert not r.confirmed
    assert r.chosen is not None and r.chosen.food == thigh
    assert r.confidence == 0.9


def test_known_food_id_confirms_only_a_food_already_eaten(session: Session, usda: dict[str, Food]) -> None:
    lard = usda["Lard"]
    [before] = resolve_items(session, None, [item("sádlo", "Sádlo", food_id=lard.id)], FakeChooser())
    meal = MealLog(logged_date=dt.date(2026, 10, 1))
    session.add(meal)
    session.add(MealLogItem(meal_log_id=meal.id, label="sádlo", food_id=lard.id, amount_g=10))
    session.commit()
    [after] = resolve_items(session, None, [item("sádlo", "Sádlo", food_id=lard.id)], FakeChooser())

    assert not before.confirmed
    assert (after.confirmed, after.via) == (True, "food_id")


def test_exact_czech_name_confirms_user_foods_only(session: Session) -> None:
    kt = food(session, FoodSource.kaloricke_tabulky, name_cs="Rohlík tukový")
    food(session, name_cs="Brambory vařené", name_en="Potatoes, boiled")  # USDA, never eaten

    [roll, potatoes] = resolve_items(
        session, None, [item("rohlík", "rohlik tukovy"), item("brambor", "Brambory vařené")], FakeChooser()
    )

    assert (roll.confirmed, roll.via, roll.food) == (True, "exact_name", kt)
    assert not potatoes.confirmed
    assert potatoes.chosen is not None and potatoes.chosen.name == "Brambory vařené"


def test_without_candidates_the_web_estimate_is_offered(session: Session) -> None:
    estimate = Candidate("web", "Bramboráky domácí", FoodSource.web_estimate, {"kcal": 230.0})

    [r] = resolve_items(session, None, [item("bramboráky", "Bramboráky")], FakeChooser(estimate=estimate))

    assert r.candidates == [estimate]
    assert r.chosen is estimate


def test_nothing_found_and_no_estimate_leaves_the_item_open(session: Session) -> None:
    [r] = resolve_items(session, None, [item("xyz", "Xyz")], TopScoreChooser())

    assert (r.confirmed, r.chosen, r.candidates) == (False, None, [])


def test_branded_items_get_open_food_facts_candidates(session: Session) -> None:
    hit = {
        "code": "859",
        "product_name": "Skyr bílý",
        "brands": ["Milko"],
        "nutriments": {"energy-kcal_100g": 63, "proteins_100g": 11, "carbohydrates_100g": 4, "fat_100g": 0.2},
    }
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"hits": [hit]})))

    [r] = resolve_items(
        session,
        http,
        [item("skyr od milka", "Skyr bílý (Milko)", is_branded=True, brand_search_query="Milko skyr")],
        FakeChooser(),
    )

    assert r.chosen is not None
    assert (r.chosen.ref, r.chosen.brand, r.chosen.per_100g["protein_g"]) == ("off:859", "Milko", 11)


def test_confirming_writes_both_aliases_and_names_a_usda_food(session: Session, usda: dict[str, Food]) -> None:
    thigh = usda["Chicken, broilers or fryers, dark meat, thigh, meat only, raw"]
    session.add(FoodAlias(alias_normalized=normalize("kuřecích stehen"), food_id=usda["Lard"].id))
    session.commit()

    confirm_aliases(session, item(), thigh)
    session.commit()

    aliases = {a.alias_normalized: (a.food_id, a.confirmed) for a in session.exec(select(FoodAlias))}
    assert aliases == {"kurecich stehen": (thigh.id, True), "kureci stehno, syrove": (thigh.id, True)}
    assert thigh.name_cs == "Kuřecí stehno, syrové"


def test_materialize_creates_foods_for_off_products_and_web_estimates(session: Session) -> None:
    per_100g = {"kcal": 63.0, "protein_g": 11.0, "carbs_g": 4.0, "fat_g": 0.2, "sugar_g": None}
    product = materialize(session, Candidate("off:859", "Skyr bílý", "openfoodfacts", per_100g, "Milko"), item())
    web = materialize(session, Candidate("web", "Bramboráky", "web_estimate", per_100g), item("b", "Bramboráky"))

    assert (product.source, product.ean, product.sugar_g) == ("openfoodfacts", "859", None)
    assert (web.source, web.name_cs, web.kcal) == ("web_estimate", "Bramboráky", 63)
