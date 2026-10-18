"""KalorickéTabulky history import (nutrition spec Amendments C10/G2, Phase 5.5) via `kaloricketabulky-sdk`.

Verified on real diary days (O3, 2026-10-17):
- `unit` is "count x unit-grams": "200 x 1 g" = 200 g, "449 g", "2,5 x kus (50 g)" = 125 g (the bracket is per
  piece: as a total, that fried toast would be 1052 kcal/100 g), "200 x 1 ml" (ml taken as g, drinks).
- Nutrient values are per entry; sodium and calcium are in grams. The diary's own totals come back as 0.
- Weight history is a snapshot of dated points in kg.
- The user's own recipes ("Recky protein") are plain entries whose composition changes day to day, and the API
  exposes no ingredients. So imported items keep KT's exact macros for that day (E16, the one exception to C8),
  and the food holds the newest composition for future logging.

The job is throttled (one request per REQUEST_INTERVAL_S, as the SDK author asks) and resumable: the state row
keeps a day cursor. A day is replaced as a whole (its imported meals are deleted and re-created with ids derived
from KT's). Meals logged in this app are never touched: on a day that has some, KT's meals are imported next to
them (the app's own entries and KT's can't be matched, so one logged in both places counts twice; the day gets
a warning).
"""

import asyncio
import datetime as dt
import logging
import re
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from kaloricketabulky.sdk import AuthError, Diary, DiaryFoodstuff, Snapshot, SnapshotType
from sqlalchemy import delete
from sqlmodel import Session, col, func, select

from app.models.body import DailyMetric
from app.models.nutrition import Food, FoodSource, KTImportState, MealLog, MealLogItem, MealSource, MealType
from app.timeutils import local_date, now_utc

log = logging.getLogger(__name__)

REQUEST_INTERVAL_S = 2.0
KJ_PER_KCAL = 4.184
MAX_WARNINGS = 200
# Deterministic ids for imported meals/items: re-importing a day re-creates the same rows
NAMESPACE = uuid.UUID("6f0f8c1e-2a8d-4d0e-9b8a-5b1c3e7d9a21")
MEAL_TYPES = {
    "snídaně": MealType.breakfast,
    "dopolední svačina": MealType.morning_snack,
    "oběd": MealType.lunch,
    "odpolední svačina": MealType.afternoon_snack,
    "večeře": MealType.dinner,
    "druhá večeře": MealType.second_dinner,
}
UNIT = re.compile(
    r"^\s*(?:(?P<count>[\d\s.,]+?)\s*x\s*)?(?:[^()\d][^()]*?\s*\(\s*)?(?P<grams>[\d\s.,]+?)\s*(?:g|ml)\s*\)?\s*$",
    re.IGNORECASE,
)


def _number(raw: str) -> float:
    return float(re.sub(r"\s", "", raw).replace(",", "."))


def parse_grams(unit: str | None) -> float | None:
    """Grams eaten from a KT unit string; None when it isn't in g/ml."""
    match = UNIT.match(unit or "")
    if match is None:
        return None
    try:
        grams = _number(match["grams"]) * (_number(match["count"]) if match["count"] else 1.0)
    except ValueError:
        return None
    return round(grams, 3) if grams > 0 else None


class KTClient(Protocol):
    async def login(self, email: str, password: str) -> None: ...
    async def get_diary(self, day: dt.date) -> Diary: ...
    async def get_snapshot(self, metric: Any, date_from: dt.date, date_to: dt.date) -> Snapshot: ...


@dataclass
class DayResult:
    items: int = 0
    foods_created: int = 0
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)


def _per_100g(value: float | None, grams: float) -> float | None:
    return None if value is None else round(max(0.0, value) / grams * 100, 3)


def _kcal(item: DiaryFoodstuff) -> float | None:
    if item.energy is None:
        return None
    return item.energy / KJ_PER_KCAL if (item.energy_unit or "kcal").lower() == "kj" else item.energy


def _entry_macros(item: DiaryFoodstuff) -> dict[str, float | None]:
    """This entry's own totals (what KT shows for that day)."""
    values = {"kcal": _kcal(item), "protein_g": item.protein, "carbs_g": item.carbohydrate, "fat_g": item.fat}
    return {k: None if v is None else round(max(0.0, v), 2) for k, v in values.items()}


def _food_values(item: DiaryFoodstuff, grams: float) -> dict[str, Any]:
    """Per-100 g values from one entry; sodium/calcium come in grams per entry and become mg."""
    micros = {
        key: round(max(0.0, raw) / grams * 100 * 1000, 3)
        for key, raw in (("sodium_mg", item.sodium), ("calcium_mg", item.calcium))
        if raw is not None
    }
    return {
        "kcal": _per_100g(_kcal(item), grams),
        "protein_g": _per_100g(item.protein, grams),
        "carbs_g": _per_100g(item.carbohydrate, grams),
        "fat_g": _per_100g(item.fat, grams),
        "sugar_g": _per_100g(item.sugar, grams),
        "saturated_fat_g": _per_100g(item.saturated_fatty_acid, grams),
        "fiber_g": _per_100g(item.fiber, grams),
        "salt_g": _per_100g(item.salt, grams),
        "micronutrients": micros,
    }


def _latest_import_day(session: Session, food: Food) -> dt.date | None:
    return session.exec(
        select(func.max(MealLog.logged_date))
        .join(MealLogItem, col(MealLogItem.meal_log_id) == MealLog.id)
        .where(MealLogItem.food_id == food.id, MealLog.source == MealSource.kaloricke_tabulky)
    ).one()


def _food(session: Session, item: DiaryFoodstuff, grams: float, result: DayResult, day: dt.date) -> Food | None:
    """The KT food behind an entry (by guid), created or refreshed so it holds the newest composition seen."""
    title = (item.title or "").strip()
    if not item.guid_type:
        result.warnings.append(f"{day}: '{title}' bez ID potraviny, přeskočeno")
        return None
    values = _food_values(item, grams)
    if any(values[k] is None for k in ("kcal", "protein_g", "carbs_g", "fat_g")):
        result.warnings.append(f"{day}: '{title}' nemá kcal/bílkoviny/sacharidy/tuky, přeskočeno")
        return None
    external_id = f"kt:{item.guid_type}"
    food = session.exec(select(Food).where(Food.external_id == external_id)).first()
    if food is None:
        food = Food(
            name_cs=title or None,
            name_en=None if title else external_id,
            source=FoodSource.kaloricke_tabulky,
            external_id=external_id,
            **values,
        )
        result.foods_created += 1
    elif (latest := _latest_import_day(session, food)) is None or day >= latest:
        for key, value in values.items():
            setattr(food, key, value)
        food.updated_at = now_utc()
    session.add(food)
    session.flush()
    return food


def import_day(session: Session, day: dt.date, diary: Diary) -> DayResult:
    """Replace the imported meals of one day with what KT has (atomic per day); the app's own meals stay."""
    result = DayResult()
    if not any(meal.items for meal in diary.meals):
        return result
    app_logged = session.exec(select(MealLog.id).where(MealLog.logged_date == day, col(MealLog.source).is_(None)))
    if app_logged.first() is not None:
        result.warnings.append(f"{day}: den má i jídla zapsaná v aplikaci, import je doplnil k nim (možné zdvojení)")
    # Items go with their meal (ON DELETE CASCADE)
    session.execute(
        delete(MealLog).where(col(MealLog.logged_date) == day, col(MealLog.source) == MealSource.kaloricke_tabulky)
    )
    session.flush()
    for meal in diary.meals:
        meal_type = MEAL_TYPES.get((meal.title or "").strip().lower(), MealType.other)
        meal_id = uuid.uuid5(NAMESPACE, f"{day}:{meal.id}")
        items = []
        for entry in meal.items:
            grams = parse_grams(entry.unit)
            if grams is None:
                result.warnings.append(f"{day}: '{(entry.title or '').strip()}' – neznámé množství '{entry.unit}'")
                continue
            food = _food(session, entry, grams, result, day)
            if food is not None:
                item_id = uuid.uuid5(NAMESPACE, f"{day}:{meal.id}:{entry.id}")
                # Exact KT macros for that day on the item (they win over the food's); the food covers the rest
                macros = _entry_macros(entry)
                items.append(
                    MealLogItem(
                        id=item_id, meal_log_id=meal_id, label=food.name, food_id=food.id, amount_g=grams, **macros
                    )
                )
        if items:
            session.add(MealLog(id=meal_id, logged_date=day, meal_type=meal_type, source=MealSource.kaloricke_tabulky))
            session.flush()
            session.add_all(items)
            result.items += len(items)
    session.commit()
    return result


def import_weights(session: Session, snapshot: Snapshot) -> int:
    """KT weights for days without a weight yet (a weight entered in this app wins)."""
    filled = 0
    for point in snapshot.values:
        if point.value is None or point.valid_from is None:
            continue
        day = local_date(point.valid_from)
        metric = session.get(DailyMetric, day) or DailyMetric(date=day)
        if metric.weight_kg is None:
            metric.weight_kg = round(point.value, 2)
            session.add(metric)
            filled += 1
    session.commit()
    return filled


def get_state(session: Session) -> KTImportState:
    return session.get(KTImportState, 1) or KTImportState(id=1)


def _save_state(session: Session, state: KTImportState, **changes: Any) -> KTImportState:
    for key, value in changes.items():
        setattr(state, key, value)
    state.updated_at = now_utc()
    session.add(state)
    session.commit()
    return state


def prepare(session: Session, date_from: dt.date, date_to: dt.date) -> KTImportState:
    """Mark a run as started; the same range after an error or restart continues from its cursor."""
    state = get_state(session)
    resume = state.status in ("running", "error") and (state.range_from, state.range_to) == (date_from, date_to)
    if resume:
        return _save_state(session, state, status="running", last_error=None)
    return _save_state(
        session, state, status="running", range_from=date_from, range_to=date_to, next_day=date_from, days_done=0,
        days_skipped=0, items_imported=0, foods_created=0, weights_filled=0, warnings=[], last_error=None,
    )  # fmt: skip


SessionFactory = Callable[[], AbstractContextManager[Session]]


def _day_step(session_factory: SessionFactory, day: dt.date, diary: Diary) -> None:
    """Import one day and advance the cursor (runs in a worker thread with its own session)."""
    with session_factory() as session:
        result = import_day(session, day, diary)
        state = get_state(session)
        _save_state(
            session, state, next_day=day + dt.timedelta(days=1), days_done=state.days_done + 1,
            days_skipped=state.days_skipped + int(result.skipped), items_imported=state.items_imported + result.items,
            foods_created=state.foods_created + result.foods_created,
            warnings=(state.warnings + result.warnings)[-MAX_WARNINGS:],
        )  # fmt: skip


def _weights_step(session_factory: SessionFactory, snapshot: Snapshot) -> None:
    with session_factory() as session:
        filled = import_weights(session, snapshot)
        _save_state(session, get_state(session), weights_filled=filled)


def _finish(session_factory: SessionFactory, **changes: Any) -> None:
    with session_factory() as session:
        _save_state(session, get_state(session), **changes)


async def run_import(
    client: KTClient,
    session_factory: SessionFactory,
    credentials: tuple[str, str],
    *,
    interval: float = REQUEST_INTERVAL_S,
) -> None:
    """Import days from the state's cursor to its end; the state row reports progress and errors."""
    with session_factory() as session:
        state = get_state(session)
        start, end, first_run = state.next_day, state.range_to, state.days_done == 0
    if start is None or end is None:
        return
    try:
        await client.login(*credentials)
        if first_run:
            snapshot = await client.get_snapshot(SnapshotType.WEIGHT, start, end)
            await asyncio.to_thread(_weights_step, session_factory, snapshot)
        day = start
        while day <= end:
            await asyncio.sleep(interval)
            try:
                diary = await client.get_diary(day)
            except AuthError:  # session expired: log in again once
                await client.login(*credentials)
                diary = await client.get_diary(day)
            await asyncio.to_thread(_day_step, session_factory, day, diary)
            day += dt.timedelta(days=1)
        await asyncio.to_thread(_finish, session_factory, status="done")
    except Exception as exc:  # reported in the UI; the same range resumes from the cursor
        log.exception("KT import failed")
        await asyncio.to_thread(_finish, session_factory, status="error", last_error=str(exc)[:500])
    finally:
        if (close := getattr(client, "aclose", None)) is not None:
            await close()


_task: asyncio.Task | None = None


def is_running() -> bool:
    return _task is not None and not _task.done()


def start_task(client: KTClient, session_factory: SessionFactory, credentials: tuple[str, str], **kwargs: Any) -> None:
    """Run the import in the background of the server's event loop (one at a time)."""
    global _task
    _task = asyncio.create_task(run_import(client, session_factory, credentials, **kwargs))
