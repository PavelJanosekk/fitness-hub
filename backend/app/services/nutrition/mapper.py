"""Gemini mapper for new foods (E26): which USDA foods, in what amounts, describe a food.

One structured call per batch of foods returns each food's components as USDA-style English queries with grams
per 100 g; the local USDA search (`resolver.search_usda`) turns each query into a reference. Gemini never supplies
nutrient numbers here. Applied automatically (user decision): a food with no usable component is `unmatched`.

Free-tier friendly: lite model (E15), batches of BATCH foods, at most `settings.micros_mapper_daily_requests`
calls per day (counted in-process; a restart may allow a few extra).
"""

import datetime as dt
import logging
import threading
from typing import Any

from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.config import settings
from app.models.nutrition import Food, FoodSource, MealLogItem, MicrosStatus
from app.services.gemini_service import lite_model
from app.services.nutrition.micro_refs import set_refs
from app.services.nutrition.resolver import search_usda
from app.timeutils import today

log = logging.getLogger(__name__)

BATCH = 15
MIN_SCORE = 0.6  # search_usda score of the best hit below which a component is dropped

MAPPER_PROMPT = """Pro každou potravinu urči, z jakých potravin databáze USDA SR Legacy se skládá, aby šlo
odhadnout její vitamíny a minerály. Pro každou složku dej usda_query_en (anglický popis ve stylu USDA, např.
"Chicken, broilers or fryers, breast, meat only, raw"; stav raw/cooked podle toho, jak se potravina váží)
a grams_per_100g (kolik gramů složky je ve 100 g potraviny).
- Jednoduchá potravina = jedna složka, 100 g. Balený výrobek = obecný ekvivalent ("Yogurt, Greek, plain, nonfat").
- Jídlo nebo směs = hlavní suroviny (dohromady zhruba 100 g; voda se nepočítá). Drž se maker uvedených u potraviny.
- Koření a ochucovadla vynech, pokud netvoří podstatnou část.
- Když nic z USDA rozumně neodpovídá (sladidla, konjak), dej prázdný seznam složek.

Potraviny (hodnoty na 100 g):
"""


class Component(BaseModel):
    usda_query_en: str = Field(min_length=2, max_length=200)
    grams_per_100g: float = Field(gt=0, le=500)


class FoodComponents(BaseModel):
    food: int = Field(description="Food number")
    components: list[Component]


class _DailyBudget:
    def __init__(self) -> None:
        self.day: dt.date | None = None
        self.used = 0
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            if self.day != today():
                self.day, self.used = today(), 0
            if self.used >= settings.micros_mapper_daily_requests:
                return False
            self.used += 1
            return True


budget = _DailyBudget()


def _describe(index: int, food: Food) -> str:
    brand = f" [{food.brand}]" if food.brand else ""
    fiber = f", vláknina {food.fiber_g:g} g" if food.fiber_g is not None else ""
    return (
        f"{index}: {food.name}{brand}: {food.kcal:g} kcal, B {food.protein_g:g} g, S {food.carbs_g:g} g, "
        f"T {food.fat_g:g} g{fiber}"
    )


def resolve_components(session: Session, components: list[Component]) -> list[tuple[int, float]]:
    refs = []
    for component in components:
        hits = search_usda(session, component.usda_query_en, limit=1)
        if hits and hits[0][1] >= MIN_SCORE and hits[0][0].id is not None:
            refs.append((hits[0][0].id, component.grams_per_100g / 100))
    return refs


def map_foods(session: Session, client: Any, foods: list[Food]) -> int:
    """Map up to BATCH foods in one call; returns how many got references. Raises on a Gemini error, leaving the
    foods pending for the next run."""
    foods = foods[:BATCH]
    if not foods:
        return 0
    response = client.models.generate_content(
        model=lite_model(),
        contents=MAPPER_PROMPT + "\n".join(_describe(i, f) for i, f in enumerate(foods)),
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=list[FoodComponents], temperature=0
        ),
    )
    answers = {a.food: a.components for a in (response.parsed or []) if isinstance(a, FoodComponents)}
    mapped = 0
    for i, food in enumerate(foods):
        if i not in answers:
            continue  # missing from the answer: stays pending
        refs = resolve_components(session, answers[i])
        set_refs(session, food, refs, MicrosStatus.mapped if refs else MicrosStatus.unmatched)
        mapped += bool(refs)
    session.commit()
    return mapped


def map_from_query(session: Session, food: Food, usda_query_en: str | None) -> bool:
    """A food the assistant just created (OFF product, web estimate) with the item's USDA query as its single
    reference: no Gemini call. False (food stays pending for `run`) when the query finds nothing close."""
    if not usda_query_en or food.micros_status is not None or food.source == FoodSource.usda:
        return False
    refs = resolve_components(session, [Component(usda_query_en=usda_query_en, grams_per_100g=100)])
    if refs:
        set_refs(session, food, refs, MicrosStatus.mapped)
    return bool(refs)


def map_in_background(food_ids: list[int]) -> None:
    """BackgroundTasks entry: map just-created foods right away (within the daily budget). Off where background
    jobs are off (dev, tests): the scheduler's job does it in prod anyway."""
    from app.database import engine
    from app.services.gemini_service import AINotConfiguredError, get_client

    if not settings.scheduler_enabled:
        return
    try:
        client = get_client()
    except AINotConfiguredError:
        return  # the scheduler retries once a key is set
    with Session(engine) as session:
        run(session, client, ids=food_ids, max_requests=1)


def pending_foods(session: Session, limit: int = BATCH, ids: list[int] | None = None) -> list[Food]:
    """Foods never mapped, most eaten first (they matter most for the day totals)."""
    eaten = select(func.count()).where(MealLogItem.food_id == Food.id).correlate(Food).scalar_subquery()
    statement = select(Food).where(Food.source != FoodSource.usda, col(Food.micros_status).is_(None))
    if ids is not None:
        statement = statement.where(col(Food.id).in_(ids))
    return list(session.exec(statement.order_by(eaten.desc(), col(Food.id)).limit(limit)).all())


def run(session: Session, client: Any, ids: list[int] | None = None, max_requests: int = 3) -> int:
    """Map pending foods (only `ids` when given) within the daily budget; returns the number mapped."""
    mapped = 0
    for _ in range(max_requests):
        foods = pending_foods(session, ids=ids)
        if not foods or not budget.take():
            break
        try:
            mapped += map_foods(session, client, foods)
        except Exception as exc:  # quota (429), network, model errors: try again on the next run
            session.rollback()
            log.warning("micros mapper: %s", exc)
            break
    return mapped
