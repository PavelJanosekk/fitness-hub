"""Micronutrient references (E26): the mapping file, the weighted sum, and what a manual mapping protects."""

from sqlmodel import Session, select

from app.models.nutrition import Food, FoodMicroRef, FoodSource, MicrosStatus
from app.services.nutrition.micro_refs import apply_mapping, effective_micros, needs_mapping, refs_for, set_refs


def food(session: Session, source: FoodSource, external_id: str | None = None, micros: dict | None = None) -> Food:
    row = Food(
        source=source,
        external_id=external_id,
        name_cs=external_id or "Jídlo",
        kcal=100,
        protein_g=10,
        carbs_g=10,
        fat_g=2,
        micronutrients=micros or {},
    )
    session.add(row)
    session.commit()
    return row


def test_mapping_file_sets_refs_and_reports_unknown_ids(session: Session) -> None:
    chicken = food(session, FoodSource.usda, "usda:171077", {"iron_mg": 0.4, "zinc_mg": 0.8})
    broccoli = food(session, FoodSource.usda, "usda:170379", {"iron_mg": 0.7, "vitamin_c_mg": 89.2})
    dish = food(session, FoodSource.kaloricke_tabulky, "kt:dish", {"calcium_mg": 95.0})
    noodles = food(session, FoodSource.kaloricke_tabulky, "kt:shirataki")
    mine = food(session, FoodSource.kaloricke_tabulky, "kt:mine")
    set_refs(session, mine, [(broccoli.id, 1)], MicrosStatus.manual)  # type: ignore[list-item]
    session.commit()

    result = apply_mapping(
        session,
        "# comment\n"
        "kt:dish | kureci rýže | 171077:0.6 170379:0.2 999999:0.1\n"
        "kt:shirataki | Shirataki | -\n"
        "kt:mine | mine | 171077:1\n"
        "kt:gone | deleted food | 171077:1\n",
    )

    assert (result.mapped, result.unmatched, result.skipped_manual) == (1, 1, 1)
    assert (result.missing_foods, result.missing_usda) == (["kt:gone"], ["999999"])
    refs = refs_for(session, [dish.id, noodles.id, mine.id])  # type: ignore[list-item]
    assert [(r.food.id, r.grams_per_g) for r in refs[dish.id]] == [(chicken.id, 0.6), (broccoli.id, 0.2)]  # type: ignore[index]
    assert noodles.id not in refs and [r.food.id for r in refs[mine.id]] == [broccoli.id]  # type: ignore[index]
    assert (dish.micros_status, noodles.micros_status, mine.micros_status) == ("mapped", "unmatched", "manual")
    # Own calcium wins; iron and zinc are weighted sums over the refs that know them
    assert effective_micros(dish, refs[dish.id]) == {  # type: ignore[index]
        "calcium_mg": 95.0, "iron_mg": 0.38, "zinc_mg": 0.48, "vitamin_c_mg": 17.84,
    }  # fmt: skip


def test_set_refs_replaces_merges_duplicates_and_skips_self(session: Session) -> None:
    chicken = food(session, FoodSource.usda, "usda:1")
    dish = food(session, FoodSource.custom)
    assert needs_mapping(dish) and not needs_mapping(chicken)

    set_refs(session, dish, [(chicken.id, 0.3), (chicken.id, 0.2), (dish.id, 1)], MicrosStatus.mapped)  # type: ignore[list-item]
    set_refs(session, dish, [(chicken.id, 0.25)], MicrosStatus.manual)  # type: ignore[list-item]
    session.commit()

    rows = session.exec(select(FoodMicroRef).where(FoodMicroRef.food_id == dish.id)).all()
    assert [(r.ref_food_id, r.grams_per_g) for r in rows] == [(chicken.id, 0.25)]
    assert not needs_mapping(dish)


def test_deleting_a_reference_food_drops_the_ref(session: Session) -> None:
    chicken = food(session, FoodSource.usda, "usda:2")
    dish = food(session, FoodSource.custom)
    set_refs(session, dish, [(chicken.id, 1)], MicrosStatus.mapped)  # type: ignore[list-item]
    session.commit()

    session.delete(chicken)
    session.commit()

    assert refs_for(session, [dish.id]) == {}  # type: ignore[list-item]
