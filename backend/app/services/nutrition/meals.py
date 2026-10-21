"""Writing food-based meals: dictated meals (auto-saved or confirmed drafts) and hand-added items."""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models.nutrition import Food, MealLog, MealLogItem
from app.schemas.nutrition import ItemUpsert
from app.timeutils import today


@dataclass
class MealEntry:
    label: str  # the user's phrase, shown next to the food name
    food: Food
    amount_g: float


def save_meal(
    session: Session,
    *,
    meal_id: uuid.UUID,
    day: dt.date,
    meal_type: str,
    entries: list[MealEntry],
    raw_input: str | None = None,
) -> MealLog:
    """Idempotent on meal_id: a repeated confirmation returns the meal saved the first time."""
    if (existing := session.get(MealLog, meal_id)) is not None:
        return existing
    meal = MealLog(id=meal_id, logged_date=day, meal_type=meal_type, raw_user_input=raw_input)
    session.add(meal)
    for entry in entries:
        session.add(MealLogItem(meal_log_id=meal.id, label=entry.label, food_id=entry.food.id, amount_g=entry.amount_g))
    session.commit()
    return meal


def upsert_item(
    session: Session, item_id: uuid.UUID, body: ItemUpsert, food: Food, quick_action_id: uuid.UUID | None = None
) -> MealLogItem:
    """A new item joins the day's latest meal of that type (or starts one); an existing item keeps its meal and
    gets the new food/grams (inline gram editing). `quick_action_id` marks a new item logged by a quick action."""
    item = session.get(MealLogItem, item_id)
    if item is None:
        day = body.date or today()
        meal = session.exec(
            select(MealLog)
            .where(MealLog.logged_date == day, MealLog.meal_type == body.meal_type)
            .order_by(col(MealLog.created_at).desc())
        ).first()
        if meal is None:
            meal = MealLog(logged_date=day, meal_type=body.meal_type)
            session.add(meal)
        item = MealLogItem(
            id=item_id, meal_log_id=meal.id, label=body.label or food.name, quick_action_id=quick_action_id
        )
    item.food_id, item.amount_g = food.id, body.amount_g
    item.kcal = item.protein_g = item.carbs_g = item.fat_g = None  # a food item takes its values from the food
    if body.label:
        item.label = body.label
    session.add(item)
    session.commit()
    return item


def move_item(session: Session, item: MealLogItem, meal_type: str) -> MealLogItem:
    """Idempotent: the item joins the day's latest meal of that type (or starts one); a meal left empty is
    deleted, as when its last item is removed."""
    source = session.get(MealLog, item.meal_log_id)
    if source is None or source.meal_type == meal_type:
        return item
    target = session.exec(
        select(MealLog)
        .where(MealLog.logged_date == source.logged_date, MealLog.meal_type == meal_type)
        .order_by(col(MealLog.created_at).desc())
    ).first()
    if target is None:
        target = MealLog(logged_date=source.logged_date, meal_type=meal_type)
        session.add(target)
        session.flush()
    item.meal_log_id = target.id
    session.add(item)
    session.flush()
    if session.exec(select(MealLogItem.id).where(MealLogItem.meal_log_id == source.id)).first() is None:
        session.delete(source)
    session.commit()
    return item
