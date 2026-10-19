"""Food resolver (Phase 5.3): confirmed paths, candidates, chooser, aliases only on confirmation."""

import datetime as dt

import httpx
import pytest
from sqlmodel import Session, select

from app.models.nutrition import (
    Food,
    FoodAlias,
    FoodMicroRef,
    FoodPortion,
    FoodSource,
    MealLog,
    MealLogItem,
    MicrosStatus,
    RecipeComponent,
)
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
    def __init__(self, picks: list[tuple[int | None, float | None]] | None = None, found: Candidate | None = None):
        self.picks, self.found, self.seen, self.looked_up = picks, found, [], []

    def choose(self, resolutions: list[Resolution]) -> list[tuple[int | None, float | None]]:
        self.seen.append(resolutions)
        return self.picks or [(0, 0.9) for _ in resolutions]

    def lookup(self, session: Session, http: httpx.Client | None, item: MealItemInput) -> Candidate | None:
        self.looked_up.append(item.canonical_name_cs)
        return self.found


def food(session: Session, source: FoodSource = FoodSource.usda, **fields) -> Food:
    row = Food(**({"source": source, "kcal": 100, "protein_g": 10, "carbs_g": 10, "fat_g": 1} | fields))
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


def test_hidden_usda_foods_are_found_only_as_references(session: Session) -> None:
    food(session, name_en="Garlic bread, frozen")
    garlic = food(session, name_en="Garlic, raw", hidden=True)  # the 1:1 reference of a KT food (E28)

    visible = search_usda(session, "Garlic, raw", limit=1)
    references = search_usda(session, "Garlic, raw", limit=1, include_hidden=True)

    assert visible[0][0].name_en == "Garlic bread, frozen"
    assert references[0][0] == garlic


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


def test_without_candidates_the_lookup_is_offered(session: Session) -> None:
    estimate = Candidate("web", "Bramboráky domácí", FoodSource.web_estimate, {"kcal": 230.0})
    chooser = FakeChooser(found=estimate)

    [r] = resolve_items(session, None, [item("bramboráky", "Bramboráky")], chooser)

    assert r.candidates == [estimate]
    assert (r.chosen, r.confidence) == (estimate, None)
    assert chooser.seen == []  # nothing to choose from


def bun_cha(**fields) -> MealItemInput:
    return item("bun cha", "Bún chả", is_dish=True, usda_query_en="Pork with rice noodles", **fields)


def recipe_candidate(portion_g: float = 450) -> Candidate:
    recipe = {"source_url": None, "yield_g": 900, "portion_g": portion_g, "ingredients": []}
    return Candidate("recipe", "Bún chả", FoodSource.recipe, {"kcal": 150.0}, recipe=recipe)


@pytest.mark.parametrize(
    ("dish", "picks", "looked_up"),
    [
        (True, [(0, 0.4)], True),  # a dish picked without confidence: Bun Bo Nam Bo is not Bún chả
        (True, [(0, None)], True),  # the chooser failed (top score)
        (True, [(0, 0.85)], False),
        (False, [(0, 0.4)], False),  # a plain food keeps its uncertain pick
        (False, [(None, 0.0)], True),  # the chooser says nothing fits
    ],
)
def test_the_lookup_runs_when_nothing_fits_or_a_dish_is_uncertain(
    session: Session, dish: bool, picks: list, looked_up: bool
) -> None:
    food(session, name_en="Pork, fresh, belly, raw")
    found = recipe_candidate()
    chooser = FakeChooser(picks=picks, found=found)
    entry = bun_cha() if dish else item("bůčku", "Vepřový bůček", usda_query_en="Pork, fresh, belly, raw")

    [r] = resolve_items(session, None, [entry], chooser)

    assert bool(chooser.looked_up) is looked_up
    if looked_up:
        assert (r.chosen, r.confidence, len(r.candidates)) == (found, None, 2)  # the old candidate stays
    else:
        assert r.chosen is not None and r.chosen.ref.startswith("food:")


def test_portions_use_the_recipe_portion_or_the_foods_own(session: Session) -> None:
    dish = food(session, FoodSource.recipe, name_cs="Svíčková")
    session.add(FoodPortion(food_id=dish.id, label="porce", grams=380))
    session.commit()
    chooser = FakeChooser(picks=[(None, 0.0)], found=recipe_candidate(portion_g=450))

    looked, known, plain = resolve_items(
        session,
        None,
        [bun_cha(portions=2), item("svíčkovou", "Svíčková", portions=1), item("xyz", "Xyz")],
        chooser,
    )

    assert (looked.item.amount_g, known.item.amount_g, known.via) == (900, 380, "exact_name")
    assert plain.item.amount_g == 200  # no portions said: the model's grams stay


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


def test_materialize_saves_a_recipe_recomputed_from_its_usda_ingredients(session: Session) -> None:
    pork = food(session, name_en="Pork, fresh, belly, raw", kcal=518, protein_g=9.3, carbs_g=0, fat_g=53)
    noodles = food(session, name_en="Rice noodles, dry", kcal=364, protein_g=6, carbs_g=80, fat_g=0.6)
    custom = food(session, FoodSource.custom, name_cs="Moje omáčka")
    recipe = {
        "source_url": "https://www.toprecepty.cz/recept/bun-cha/",
        "yield_g": 1000,
        "portion_g": 500,
        "ingredients": [
            {"name": "bůček", "grams": 300, "food_id": pork.id},
            {"name": "rýžové nudle", "grams": 200, "food_id": noodles.id, "assumed": True},
            {"name": "omáčka", "grams": 50, "food_id": custom.id},  # not a USDA food: adds nothing
            {"name": "bylinky", "grams": 20, "food_id": None},
        ],
    }
    forged = Candidate("recipe", "Bún chả", FoodSource.recipe, {"kcal": 1.0}, recipe=recipe)

    dish = materialize(session, forged, bun_cha())
    session.commit()

    assert (dish.source, dish.name_cs, dish.recipe_yield_g, dish.source_url) == (
        "recipe",
        "Bún chả",
        1000,
        "https://www.toprecepty.cz/recept/bun-cha/",
    )
    assert (dish.kcal, dish.protein_g, dish.carbs_g, dish.fat_g) == (228.2, 3.99, 16.0, 16.02)  # not the client's 1
    components = {c.ingredient_food_id: c.amount_g for c in session.exec(select(RecipeComponent))}
    assert components == {pork.id: 300, noodles.id: 200}
    refs = {r.ref_food_id: r.grams_per_g for r in session.exec(select(FoodMicroRef))}
    assert (refs, dish.micros_status) == ({pork.id: 0.3, noodles.id: 0.2}, MicrosStatus.mapped)
    [portion] = session.exec(select(FoodPortion).where(FoodPortion.food_id == dish.id)).all()
    assert (portion.label, portion.grams) == ("porce", 500)


def test_a_recipe_without_any_usda_ingredient_is_refused(session: Session) -> None:
    recipe = {"yield_g": 100, "ingredients": [{"name": "x", "grams": 100, "food_id": None}]}

    with pytest.raises(ValueError, match="USDA"):
        materialize(session, Candidate("recipe", "X", FoodSource.recipe, {}, recipe=recipe), item())


def test_materialize_creates_foods_for_off_products_and_web_estimates(session: Session) -> None:
    per_100g = {"kcal": 63.0, "protein_g": 11.0, "carbs_g": 4.0, "fat_g": 0.2, "sugar_g": None}
    product = materialize(session, Candidate("off:859", "Skyr bílý", "openfoodfacts", per_100g, "Milko"), item())
    web = materialize(session, Candidate("web", "Bramboráky", "web_estimate", per_100g), item("b", "Bramboráky"))

    assert (product.source, product.ean, product.sugar_g) == ("openfoodfacts", "859", None)
    assert (web.source, web.name_cs, web.kcal) == ("web_estimate", "Bramboráky", 63)
