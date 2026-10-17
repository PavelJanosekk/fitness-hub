"""Phase 1 intake: quick-add only. The full nutrition module (foods, resolver, assistant) arrives in Phase 5."""

import datetime as dt
import uuid

from fastapi import APIRouter, Response, status
from sqlmodel import col, select

from app.database import SessionDep
from app.models.nutrition import MealLog, MealLogItem, MealType
from app.schemas.nutrition import DayIntake, MealItemRead, MealRead, QuickAdd, Totals
from app.timeutils import today

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

MEAL_ORDER = {meal_type.value: index for index, meal_type in enumerate(MealType)}


@router.post("/quick-add", response_model=MealRead)
def quick_add(body: QuickAdd, session: SessionDep) -> MealRead:
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
    return _read_meal(meal, [item])


@router.get("/day", response_model=DayIntake)
def get_day(session: SessionDep, date: dt.date | None = None) -> DayIntake:
    day = date or today()
    meals = session.exec(select(MealLog).where(MealLog.logged_date == day).order_by(col(MealLog.created_at))).all()
    items = session.exec(select(MealLogItem).where(col(MealLogItem.meal_log_id).in_([m.id for m in meals]))).all()
    items_by_meal: dict[uuid.UUID, list[MealLogItem]] = {}
    for item in items:
        items_by_meal.setdefault(item.meal_log_id, []).append(item)
    reads = [_read_meal(m, items_by_meal.get(m.id, [])) for m in sorted(meals, key=lambda m: MEAL_ORDER[m.meal_type])]
    return DayIntake(date=day, meals=reads, totals=_totals(items))


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


def _read_meal(meal: MealLog, items: list[MealLogItem]) -> MealRead:
    return MealRead(
        id=meal.id,
        logged_date=meal.logged_date,
        meal_type=meal.meal_type,
        notes=meal.notes,
        items=[MealItemRead.model_validate(i) for i in items],
    )


def _totals(items: list[MealLogItem]) -> Totals:
    def total(values: list[float | None]) -> float | None:
        known = [v for v in values if v is not None]
        return round(sum(known), 1) if known else None

    return Totals(
        kcal=round(sum(i.kcal for i in items), 1),
        protein_g=total([i.protein_g for i in items]),
        carbs_g=total([i.carbs_g for i in items]),
        fat_g=total([i.fat_g for i in items]),
    )
