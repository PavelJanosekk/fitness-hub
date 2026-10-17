"""Intake: meal logs and their items. Food-based items take their nutrients live from `foods` (Amendments C8)."""

from sqlalchemy import func
from sqlmodel import Session

from app.models.nutrition import Food, MealLog, MealLogItem
from app.schemas.nutrition import QuickAdd
from app.timeutils import today

ITEM_MACROS = ("kcal", "protein_g", "carbs_g", "fat_g")


def item_value_sql(column: str):
    """SQL expression for an item's amount of a macro: the manual value (quick-add), else the food's per-100 g
    value scaled to the grams. Needs `.outerjoin(Food, Food.id == MealLogItem.food_id)`."""
    return func.coalesce(getattr(MealLogItem, column), getattr(Food, column) * MealLogItem.amount_g / 100)


def item_values(item: MealLogItem, food: Food | None) -> dict[str, float | None]:
    """The same in Python, for one item."""
    values: dict[str, float | None] = {}
    for column in ITEM_MACROS:
        manual = getattr(item, column)
        if manual is None and food is not None and item.amount_g is not None:
            manual = round(getattr(food, column) * item.amount_g / 100, 1)
        values[column] = manual
    return values


def quick_add(session: Session, body: QuickAdd) -> tuple[MealLog, MealLogItem]:
    """Idempotent: the client UUID identifies both the meal log and its single item."""
    day = body.date or today()
    meal = session.get(MealLog, body.id) or MealLog(id=body.id, logged_date=day)
    meal.logged_date = day
    meal.meal_type = body.meal_type
    item = session.get(MealLogItem, body.id) or MealLogItem(id=body.id, meal_log_id=body.id, label=body.label, kcal=0)
    item.label = body.label
    item.kcal = body.kcal
    item.protein_g = body.protein_g
    item.carbs_g = body.carbs_g
    item.fat_g = body.fat_g
    session.add(meal)
    session.add(item)
    session.commit()
    return meal, item
