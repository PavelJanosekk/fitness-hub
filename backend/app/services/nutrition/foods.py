"""The local food database: search for the food manager and the barcode path, create/edit custom foods."""

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.nutrition import Food, FoodPortion, FoodSource, MealLogItem
from app.schemas.nutrition import FoodCreate, FoodRead, FoodUpdate, PortionRead
from app.services.nutrition.nutrients import MICRO_KEYS
from app.services.nutrition.resolver import normalize
from app.timeutils import now_utc


def _normalized(column):
    return func.f_unaccent(func.lower(column))


def use_counts(session: Session, food_ids: list[int]) -> dict[int, int]:
    rows = session.exec(
        select(MealLogItem.food_id, func.count())
        .where(col(MealLogItem.food_id).in_(food_ids))
        .group_by(col(MealLogItem.food_id))
    ).all()
    return {food_id: count for food_id, count in rows if food_id is not None}


def read_food(session: Session, food: Food, use_count: int | None = None, with_portions: bool = False) -> FoodRead:
    portions = []
    if with_portions:
        rows = session.exec(
            select(FoodPortion).where(FoodPortion.food_id == food.id).order_by(col(FoodPortion.grams))
        ).all()
        portions = [PortionRead(label=p.label, grams=p.grams) for p in rows]
    if use_count is None:
        use_count = use_counts(session, [food.id]).get(food.id, 0) if food.id else 0  # type: ignore[list-item]
    return FoodRead.model_validate(food, from_attributes=True).model_copy(
        update={"name": food.name, "portions": portions, "use_count": use_count}
    )


def search_foods(
    session: Session, q: str | None, source: str | None = None, limit: int = 50, offset: int = 0
) -> list[FoodRead]:
    """With a query: best name matches (Czech or English, accents ignored). Without: most eaten first."""
    statement = select(Food)
    if source:
        statement = statement.where(Food.source == source)
    if q and q.strip():
        query = normalize(q)
        score = func.greatest(
            func.word_similarity(query, _normalized(func.concat_ws(" ", Food.name_cs, Food.brand))),
            func.word_similarity(query, _normalized(Food.name_en)),
        )
        # A name that starts with the query is what the user means ("banana" → "Bananas, raw", not "Pepper, banana")
        prefix = func.greatest(
            _normalized(Food.name_cs).startswith(query), _normalized(Food.name_en).startswith(query)
        ).is_(True)
        statement = statement.where(score >= 0.4).order_by(prefix.desc(), score.desc(), func.length(Food.name_en))
    else:
        eaten = select(func.count()).where(MealLogItem.food_id == Food.id).correlate(Food).scalar_subquery()
        statement = statement.order_by(eaten.desc(), col(Food.name_cs).nulls_last(), col(Food.name_en))
    foods = session.exec(statement.offset(offset).limit(limit)).all()
    counts = use_counts(session, [f.id for f in foods if f.id is not None])
    return [read_food(session, f, counts.get(f.id or 0, 0)) for f in foods]


def create_food(session: Session, body: FoodCreate) -> Food:
    values = body.model_dump(exclude={"portions"})
    values["micronutrients"] = {k: v for k, v in body.micronutrients.items() if k in MICRO_KEYS}
    food = Food(source=FoodSource.custom, **values)
    session.add(food)
    session.flush()
    for portion in body.portions:
        session.add(FoodPortion(food_id=food.id, label=portion.label, grams=portion.grams))  # type: ignore[arg-type]
    session.commit()
    return food


def update_food(session: Session, food: Food, body: FoodUpdate) -> Food:
    """Edits apply to the whole history: items reference the food, nothing is snapshotted (C8)."""
    changes = body.model_dump(exclude_unset=True)
    if (micros := changes.get("micronutrients")) is not None:
        changes["micronutrients"] = {k: v for k, v in micros.items() if k in MICRO_KEYS}
    for key, value in changes.items():
        if key in ("kcal", "protein_g", "carbs_g", "fat_g") and value is None:
            continue  # required columns can't be cleared
        setattr(food, key, value)
    food.updated_at = now_utc()
    session.add(food)
    session.commit()
    return food
