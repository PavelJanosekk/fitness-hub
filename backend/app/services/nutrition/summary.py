"""The day view of intake: meals with live-computed items, and per-nutrient totals with coverage (Amendment C1).

Coverage = share of the day's kcal that comes from items whose food has a value for that nutrient. A low
coverage means "unknown", not "deficient": quick-add items and foods without micros (KT, many OFF products)
lower it. A food without a micro borrows it from its micros reference food, scaled by the ratio (C10).
"""

import datetime as dt
import uuid

from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlmodel import Session, col, exists, select

from app.models.gym import Workout
from app.models.nutrition import Food, MealLog, MealLogItem, MealType, NutritionProfile
from app.models.running import Activity
from app.schemas.nutrition import MealItemRead, MealRead
from app.services.nutrition import ITEM_MACROS, item_values
from app.services.nutrition.nutrients import ALL, MICRO_KEYS
from app.timeutils import day_bounds

MEAL_ORDER = {meal_type.value: index for index, meal_type in enumerate(MealType)}


class NutrientTotal(BaseModel):
    key: str
    label: str
    unit: str
    amount: float | None  # sum over items with a known value; None when no item has one
    coverage: float | None  # 0-1 share of the day's kcal behind `amount`; None on a day without kcal
    target: float | None  # the profile target, else the EU reference
    percent: float | None


class DaySummary(BaseModel):
    date: dt.date
    training_day: bool
    meals: list[MealRead]
    nutrients: list[NutrientTotal]


def food_micros(food: Food | None, reference: Food | None) -> dict[str, float]:
    if food is None:
        return {}
    micros = dict(food.micronutrients or {})
    if reference is not None and food.micros_reference_ratio:
        for key, value in (reference.micronutrients or {}).items():
            micros.setdefault(key, round(value * food.micros_reference_ratio, 4))
    return micros


def _item_nutrients(item: MealLogItem, food: Food | None, reference: Food | None) -> dict[str, float | None]:
    """Every tracked nutrient for one item; a quick-add item knows only its manual macros."""
    values: dict[str, float | None] = dict.fromkeys((n.key for n in ALL), None) | item_values(item, food)
    if food is None or item.amount_g is None:
        return values
    scale = item.amount_g / 100
    micros = food_micros(food, reference)
    for nutrient in ALL:
        if nutrient.key in ITEM_MACROS:
            continue
        per_100g = micros.get(nutrient.key) if nutrient.key in MICRO_KEYS else getattr(food, nutrient.key)
        values[nutrient.key] = None if per_100g is None else per_100g * scale
    return values


def _rows(session: Session, day: dt.date) -> list[tuple[MealLog, MealLogItem, Food | None, Food | None]]:
    reference = aliased(Food)
    statement = (
        select(MealLog, MealLogItem, Food, reference)
        .join(MealLogItem, col(MealLogItem.meal_log_id) == MealLog.id)
        .outerjoin(Food, col(Food.id) == MealLogItem.food_id)
        .outerjoin(reference, col(reference.id) == Food.micros_reference_food_id)
        .where(MealLog.logged_date == day)
        .order_by(col(MealLog.created_at))
    )
    return list(session.exec(statement).all())  # type: ignore[arg-type]


def read_item(item: MealLogItem, food: Food | None) -> MealItemRead:
    values = item_values(item, food)
    return MealItemRead(
        id=item.id,
        label=item.label,
        food_id=item.food_id,
        food_name=food.name if food else None,
        food_source=food.source if food else None,
        amount_g=item.amount_g,
        kcal=values["kcal"] or 0.0,
        protein_g=values["protein_g"],
        carbs_g=values["carbs_g"],
        fat_g=values["fat_g"],
    )


def day_meals(session: Session, day: dt.date) -> list[MealRead]:
    meals: dict[uuid.UUID, MealRead] = {}
    for meal, item, food, _ in _rows(session, day):
        read = meals.setdefault(
            meal.id,
            MealRead(id=meal.id, logged_date=meal.logged_date, meal_type=meal.meal_type, notes=meal.notes, items=[]),
        )
        read.items.append(read_item(item, food))
    return sorted(meals.values(), key=lambda m: MEAL_ORDER[m.meal_type])


def is_training_day(session: Session, day: dt.date) -> bool:
    start, end = day_bounds(day)
    workout = exists().where(col(Workout.started_at) >= start, col(Workout.started_at) < end)
    activity = exists().where(col(Activity.start_time) >= start, col(Activity.start_time) < end)
    return bool(session.exec(select(or_(workout, activity))).one())


def _targets(profile: NutritionProfile | None, training_day: bool) -> dict[str, float]:
    if profile is None:
        return {}
    kcal = (profile.kcal_target_training_day if training_day else None) or profile.kcal_target
    candidates = {
        "kcal": kcal,
        "protein_g": profile.protein_target_g,
        "carbs_g": profile.carbs_target_g,
        "fat_g": profile.fat_target_g,
        "fiber_g": profile.fiber_target_g,
    }
    return {k: v for k, v in candidates.items() if v is not None}


def day_summary(session: Session, day: dt.date) -> DaySummary:
    rows = _rows(session, day)
    per_item = [_item_nutrients(item, food, ref) for _, item, food, ref in rows]
    day_kcal = sum(values["kcal"] or 0 for values in per_item)
    training_day = is_training_day(session, day)
    targets = _targets(session.get(NutritionProfile, 1), training_day)
    totals = []
    for nutrient in ALL:
        known = [(v[nutrient.key], v["kcal"] or 0) for v in per_item if v[nutrient.key] is not None]
        amount = round(sum(value for value, _ in known), 3) if known else None
        coverage = round(sum(kcal for _, kcal in known) / day_kcal, 3) if day_kcal > 0 else None
        target = targets.get(nutrient.key, nutrient.reference)
        percent = round(amount / target * 100, 1) if amount is not None and target else None
        totals.append(
            NutrientTotal(
                key=nutrient.key,
                label=nutrient.label_cs,
                unit=nutrient.unit,
                amount=amount,
                coverage=coverage,
                target=target,
                percent=percent,
            )
        )
    return DaySummary(date=day, training_day=training_day, meals=day_meals(session, day), nutrients=totals)
