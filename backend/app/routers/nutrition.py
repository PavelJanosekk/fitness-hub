"""Intake routes: quick-add and the day view. The rest of the nutrition module joins in Phase 5."""

import datetime as dt
import uuid

from fastapi import APIRouter, Response, status
from sqlmodel import col, select

from app.database import SessionDep
from app.models.nutrition import Food, MealLog, MealLogItem, MealType
from app.schemas.nutrition import DayIntake, MealItemRead, MealRead, QuickAdd, Totals
from app.services.nutrition import item_values
from app.services.nutrition import quick_add as quick_add_meal
from app.timeutils import today

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

MEAL_ORDER = {meal_type.value: index for index, meal_type in enumerate(MealType)}


@router.post("/quick-add", response_model=MealRead)
def quick_add(body: QuickAdd, session: SessionDep) -> MealRead:
    """Idempotent: the client UUID identifies both the meal log and its single item."""
    meal, item = quick_add_meal(session, body)
    return _read_meal(meal, [_read_item(item, None)])


@router.get("/day", response_model=DayIntake)
def get_day(session: SessionDep, date: dt.date | None = None) -> DayIntake:
    day = date or today()
    meals = session.exec(select(MealLog).where(MealLog.logged_date == day).order_by(col(MealLog.created_at))).all()
    rows = session.exec(
        select(MealLogItem, Food)
        .outerjoin(Food, col(Food.id) == MealLogItem.food_id)
        .where(col(MealLogItem.meal_log_id).in_([m.id for m in meals]))
    ).all()
    items_by_meal: dict[uuid.UUID, list[MealItemRead]] = {}
    for item, food in rows:
        items_by_meal.setdefault(item.meal_log_id, []).append(_read_item(item, food))
    reads = [_read_meal(m, items_by_meal.get(m.id, [])) for m in sorted(meals, key=lambda m: MEAL_ORDER[m.meal_type])]
    return DayIntake(date=day, meals=reads, totals=_totals([i for r in reads for i in r.items]))


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, session: SessionDep) -> Response:
    item = session.get(MealLogItem, item_id)
    if item is not None:
        meal_id = item.meal_log_id
        session.delete(item)
        session.flush()
        remaining = session.exec(select(MealLogItem.id).where(MealLogItem.meal_log_id == meal_id)).first()
        if remaining is None and (meal := session.get(MealLog, meal_id)) is not None:
            session.delete(meal)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _read_item(item: MealLogItem, food: Food | None) -> MealItemRead:
    values = item_values(item, food)
    return MealItemRead(
        id=item.id,
        label=item.label,
        food_id=item.food_id,
        amount_g=item.amount_g,
        kcal=values["kcal"] or 0.0,
        protein_g=values["protein_g"],
        carbs_g=values["carbs_g"],
        fat_g=values["fat_g"],
    )


def _read_meal(meal: MealLog, items: list[MealItemRead]) -> MealRead:
    return MealRead(id=meal.id, logged_date=meal.logged_date, meal_type=meal.meal_type, notes=meal.notes, items=items)


def _totals(items: list[MealItemRead]) -> Totals:
    def total(values: list[float | None]) -> float | None:
        known = [v for v in values if v is not None]
        return round(sum(known), 1) if known else None

    return Totals(
        kcal=round(sum(i.kcal for i in items), 1),
        protein_g=total([i.protein_g for i in items]),
        carbs_g=total([i.carbs_g for i in items]),
        fat_g=total([i.fat_g for i in items]),
    )
