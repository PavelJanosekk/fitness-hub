"""Phase 5.1: foods, food-based meal items computed live, and the USDA nutrient mapping."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models.nutrition import Food, FoodSource, MealLog, MealLogItem
from app.services.nutrition.nutrients import from_usda

D = dt.date(2026, 10, 10)


def add_food(session: Session, **fields) -> Food:
    values = {"name_cs": "Kuřecí prsa, syrová", "source": FoodSource.custom, "kcal": 120, "protein_g": 22.5}
    values |= {"carbs_g": 0, "fat_g": 2.6} | fields
    food = Food(**values)
    session.add(food)
    session.commit()
    return food


def log_food(session: Session, food: Food, grams: float, day: dt.date = D) -> MealLogItem:
    meal = MealLog(logged_date=day, meal_type="lunch")
    item = MealLogItem(meal_log_id=meal.id, label=food.name, food_id=food.id, amount_g=grams)
    session.add(meal)
    session.add(item)
    session.commit()
    return item


def day_view(client: TestClient, day: dt.date = D) -> dict:
    return client.get("/api/nutrition/day", params={"date": day.isoformat()}).json()


def test_food_items_are_computed_from_the_food(client: TestClient, session: Session) -> None:
    food = add_food(session)
    log_food(session, food, 200)

    item = day_view(client)["meals"][0]["items"][0]

    assert item["food_id"] == food.id
    assert item["amount_g"] == 200
    assert (item["kcal"], item["protein_g"], item["carbs_g"], item["fat_g"]) == (240, 45, 0, 5.2)


def test_fixing_a_food_fixes_its_history(client: TestClient, session: Session) -> None:
    food = add_food(session)
    log_food(session, food, 200)

    food.kcal = 110
    session.add(food)
    session.commit()

    assert day_view(client)["totals"]["kcal"] == 220


def test_day_totals_and_coach_intake_mix_food_and_quick_add_items(client: TestClient, session: Session) -> None:
    log_food(session, add_food(session), 200)
    response = client.post(
        "/api/nutrition/quick-add", json={"id": str(uuid.uuid4()), "date": D.isoformat(), "kcal": 300}
    )
    assert response.status_code == 200

    totals = day_view(client)["totals"]
    series = client.get("/api/metrics", params={"start_date": D.isoformat(), "end_date": D.isoformat()}).json()

    assert totals["kcal"] == 540
    # Protein is known only for the food item; unknown ≠ 0, so the total is the known part
    assert totals["protein_g"] == 45
    assert series[0]["calories_in"] == 540
    assert series[0]["protein_g"] == 45


def test_an_item_needs_a_food_with_grams_or_manual_kcal(session: Session) -> None:
    meal = MealLog(logged_date=D)
    session.add(meal)
    session.commit()

    session.add(MealLogItem(meal_log_id=meal.id, label="nic"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_food_in_use_cannot_be_deleted(session: Session) -> None:
    food = add_food(session)
    log_food(session, food, 100)

    session.delete(food)
    with pytest.raises(IntegrityError):
        session.commit()


def test_usda_mapping_uses_fallbacks_sums_and_derives_salt() -> None:
    values = from_usda(
        {
            2047: 165.0,  # Atwater general: used only because 1008 is missing
            1003: 31.0,
            1004: 3.6,
            1005: 0.0,
            1063: 0.5,  # sugars, Foundation's id
            1093: 400.0,  # sodium mg
            1177: 10.0,  # total folate, used because DFE (1190) is missing
            1270: 0.1,  # undifferentiated 18:3 instead of ALA
            1272: 0.05,  # DHA
        }
    )

    assert values["kcal"] == 165
    assert values["sugar_g"] == 0.5
    assert values["salt_g"] == 1.0
    assert values["sodium_mg"] == 400
    assert values["vitamin_b9_ug"] == 10
    assert values["omega3_g"] == pytest.approx(0.15)
    # Unknown stays unknown, never 0
    assert "fiber_g" not in values
    assert "vitamin_c_mg" not in values


def test_measured_energy_wins_over_atwater() -> None:
    assert from_usda({1008: 100.0, 2047: 120.0, 2048: 110.0})["kcal"] == 100
