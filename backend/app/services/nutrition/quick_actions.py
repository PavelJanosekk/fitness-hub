"""Quick actions (E42): saved one-tap meals logged through the normal item upsert."""

import uuid

from fastapi import HTTPException, status
from sqlmodel import Session, col, delete, select

from app.models.nutrition import Food, MealLogItem, QuickAction, QuickActionItem
from app.schemas.nutrition import ItemUpsert, QuickActionLog, QuickActionRead, QuickActionUpsert
from app.services.nutrition.meals import upsert_item
from app.timeutils import now_utc


def _items(session: Session, action_id: uuid.UUID) -> list[tuple[QuickActionItem, Food]]:
    return list(
        session.exec(
            select(QuickActionItem, Food)
            .join(Food, col(Food.id) == QuickActionItem.food_id)
            .where(QuickActionItem.quick_action_id == action_id)
            .order_by(col(QuickActionItem.position))
        ).all()
    )


def read_action(session: Session, action: QuickAction) -> QuickActionRead:
    items = [
        {
            "food_id": food.id,
            "food_name": food.name,
            "amount_g": item.amount_g,
            "kcal": food.kcal * item.amount_g / 100,
            "protein_g": food.protein_g * item.amount_g / 100,
        }
        for item, food in _items(session, action.id)
    ]
    return QuickActionRead(
        **action.model_dump(
            include={"id", "name", "emoji", "color", "meal_type", "start_minute", "end_minute", "position"}
        ),
        items=items,
        kcal=sum(i["kcal"] for i in items),
        protein_g=sum(i["protein_g"] for i in items),
    )


def list_actions(session: Session) -> list[QuickActionRead]:
    actions = session.exec(select(QuickAction).order_by(col(QuickAction.position), col(QuickAction.created_at))).all()
    return [read_action(session, action) for action in actions]


def upsert_action(session: Session, action_id: uuid.UUID, body: QuickActionUpsert) -> QuickAction:
    if body.start_minute >= body.end_minute:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The window must start before it ends")
    food_ids = {item.food_id for item in body.items}
    known = set(session.exec(select(Food.id).where(col(Food.id).in_(food_ids))).all())
    if known != food_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown food")
    fields = body.model_dump(exclude={"items"})
    if (action := session.get(QuickAction, action_id)) is None:
        action = QuickAction(id=action_id, **fields)
    else:
        action.sqlmodel_update({**fields, "updated_at": now_utc()})
    session.add(action)
    session.exec(delete(QuickActionItem).where(col(QuickActionItem.quick_action_id) == action_id))
    session.flush()
    for position, item in enumerate(body.items):
        session.add(
            QuickActionItem(quick_action_id=action_id, food_id=item.food_id, amount_g=item.amount_g, position=position)
        )
    session.commit()
    return action


def log_action(session: Session, action: QuickAction, body: QuickActionLog) -> list[tuple[MealLogItem, Food]]:
    """Every food into the day's meal of the action's type. An item id that already exists is left alone, so a
    retry (or a second tap with the same ids) adds nothing."""
    items = _items(session, action.id)
    if len(body.item_ids) != len(items):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "One item id per food of the action")
    logged = []
    for item_id, (item, food) in zip(body.item_ids, items, strict=True):
        existing = session.get(MealLogItem, item_id)
        if existing is None:
            upsert = ItemUpsert(food_id=food.id, amount_g=item.amount_g, meal_type=action.meal_type, date=body.date)
            existing = upsert_item(session, item_id, upsert, food, quick_action_id=action.id)
        logged.append((existing, food))
    return logged
