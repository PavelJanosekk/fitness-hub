"""The local food database: search for the food manager and the barcode path, create/edit custom foods."""

from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.models.nutrition import Food, FoodPortion, FoodSource, MealLogItem, MicrosStatus
from app.schemas.nutrition import FoodCreate, FoodRead, FoodUpdate, MicroRefIn, MicroRefRead, PortionRead
from app.services.nutrition.micro_refs import Ref, effective_values, refs_for, set_refs
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


def read_food(
    session: Session,
    food: Food,
    use_count: int | None = None,
    with_portions: bool = False,
    refs: list[Ref] | None = None,
) -> FoodRead:
    """`refs` None = load them; pass the batch-loaded list (possibly empty) when reading many foods."""
    portions = []
    if with_portions:
        rows = session.exec(
            select(FoodPortion).where(FoodPortion.food_id == food.id).order_by(col(FoodPortion.grams))
        ).all()
        portions = [PortionRead(label=p.label, grams=p.grams) for p in rows]
    if use_count is None:
        use_count = use_counts(session, [food.id]).get(food.id, 0) if food.id else 0  # type: ignore[list-item]
    if refs is None:
        refs = refs_for(session, [food.id]).get(food.id, []) if food.id else []  # type: ignore[list-item]
    own = effective_values(food, None)
    borrowed = {k: v for k, v in effective_values(food, refs).items() if k not in own}
    micro_refs = [MicroRefRead(ref_food_id=r.food.id, name=r.food.name, grams_per_g=r.grams_per_g) for r in refs]  # type: ignore[arg-type]
    return FoodRead.model_validate(food, from_attributes=True).model_copy(
        update={
            "name": food.name,
            "portions": portions,
            "use_count": use_count,
            "micro_refs": micro_refs,
            "borrowed": borrowed,
        }
    )


def search_foods(
    session: Session,
    q: str | None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
    hidden: bool = False,
) -> list[FoodRead]:
    """With a query: best name matches (Czech or English, accents ignored). Without: the user's foods (eaten,
    custom, imported, USDA foods with a Czech name), most eaten first; a source filter lists that whole source.
    Hidden foods (E28 duplicates) only with `hidden=True`, which lists just them."""
    statement = select(Food).where(Food.hidden == hidden)
    eaten = select(func.count()).where(MealLogItem.food_id == Food.id).correlate(Food).scalar_subquery()
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
        # ...and among those, a food the user already eats beats the 2000 USDA foods they never touched
        statement = statement.where(score >= 0.4).order_by(
            prefix.desc(), (eaten > 0).desc(), score.desc(), func.length(Food.name_en)
        )
    else:
        if not source and not hidden:
            # "My foods": eaten, user-made/imported or translated (E28), not the untranslated USDA seed
            statement = statement.where(or_(eaten > 0, Food.source != FoodSource.usda, col(Food.name_cs).is_not(None)))
        statement = statement.order_by(eaten.desc(), col(Food.name_cs).nulls_last(), col(Food.name_en))
    foods = session.exec(statement.offset(offset).limit(limit)).all()
    ids = [f.id for f in foods if f.id is not None]
    counts, refs = use_counts(session, ids), refs_for(session, ids)
    return [read_food(session, f, counts.get(f.id or 0, 0), refs=refs.get(f.id or 0, [])) for f in foods]


def _apply_refs(session: Session, food: Food, refs: list[MicroRefIn], status: MicrosStatus) -> None:
    valid = {
        f.id
        for f in session.exec(select(Food).where(col(Food.id).in_([r.ref_food_id for r in refs]))).all()
        if f.source == FoodSource.usda
    }
    if missing := {r.ref_food_id for r in refs} - valid:
        raise ValueError(f"not USDA foods: {sorted(missing)}")
    set_refs(session, food, [(r.ref_food_id, r.grams_per_g) for r in refs], status)


def create_food(session: Session, body: FoodCreate) -> Food:
    values = body.model_dump(exclude={"portions", "micro_refs"})
    values["micronutrients"] = {k: v for k, v in body.micronutrients.items() if k in MICRO_KEYS}
    food = Food(source=FoodSource.custom, **values)
    session.add(food)
    session.flush()
    if body.micro_refs is not None:
        _apply_refs(session, food, body.micro_refs, MicrosStatus.mapped if body.micro_refs else MicrosStatus.unmatched)
    for portion in body.portions:
        session.add(FoodPortion(food_id=food.id, label=portion.label, grams=portion.grams))  # type: ignore[arg-type]
    session.commit()
    return food


def update_food(session: Session, food: Food, body: FoodUpdate) -> Food:
    """Edits apply to the whole history: items reference the food, nothing is snapshotted (C8)."""
    changes = body.model_dump(exclude_unset=True, exclude={"micro_refs"})
    if body.micro_refs is not None:
        _apply_refs(session, food, body.micro_refs, MicrosStatus.manual)
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
