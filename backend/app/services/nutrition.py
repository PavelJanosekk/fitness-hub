from sqlmodel import Session

from app.models.nutrition import MealLog, MealLogItem
from app.schemas.nutrition import QuickAdd
from app.timeutils import today


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
