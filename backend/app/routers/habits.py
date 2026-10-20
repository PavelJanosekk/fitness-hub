"""Habit tracker "Rutina" (E20, docs/habits-module-spec.md)."""

import datetime as dt

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import SessionDep
from app.models.habits import Ability, AutoRule, Habit, HabitFrequency, HabitLog
from app.schemas.habits import (
    AbilityBrief,
    AbilityDetail,
    AbilityEntryRead,
    AbilityMerge,
    AbilityRead,
    AbilityUpdate,
    Board,
    BoardHabit,
    DayState,
    DayStateRead,
    HabitCreate,
    HabitEntry,
    HabitOrder,
    HabitRead,
    HabitUpdate,
)
from app.services import abilities as ab
from app.services import habits as svc
from app.timeutils import now_utc, today

router = APIRouter(prefix="/api/habits", tags=["habits"])

THRESHOLD_RULES = {AutoRule.steps, AutoRule.sleep, AutoRule.protein}
REQUIRED_FIELDS = {"title", "frequency", "weekly_target", "points", "is_bonus", "log_mode", "start_date"}


def _get(session: Session, habit_id: int) -> Habit:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Habit not found")
    return habit


def _normalize(habit: Habit) -> None:
    """Fields that only make sense for one kind of habit are reset for the other."""
    if habit.frequency == HabitFrequency.daily:
        habit.weekly_target = 1
    else:
        habit.is_bonus = False
    if habit.auto_rule not in THRESHOLD_RULES:
        habit.auto_threshold = None


@router.get("/board", response_model=Board)
def board(session: SessionDep, start: dt.date | None = None) -> Board:
    """Every habit (archived ones too, for history) with its done days; the client derives status and charts."""
    current = today()
    days = svc.load_board(session, start, current)
    return Board(
        today=current,
        start=start or min((d.habit.start_date for d in days), default=current),
        habits=[
            BoardHabit(
                **HabitRead.model_validate(d.habit).model_dump(),
                done=sorted(d.manual),
                auto=dict(sorted(d.auto.items())),
                entries={day: HabitEntry(**vars(entry)) for day, entry in sorted(d.entries.items())},
            )
            for d in days
        ],
        paused=sorted(days[0].paused) if days else [],
        forgiven=sorted(days[0].forgiven) if days else [],
        abilities=[AbilityBrief.model_validate(s.ability) for s in ab.load(session)],
    )


@router.post("", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
def create_habit(body: HabitCreate, session: SessionDep) -> Habit:
    last = session.exec(select(func.max(Habit.position))).one()
    habit = Habit(
        **body.model_dump(exclude={"start_date"}),
        start_date=body.start_date or today(),
        position=(last or 0) + 1,
    )
    _normalize(habit)
    session.add(habit)
    session.commit()
    session.refresh(habit)
    return habit


@router.patch("/{habit_id}", response_model=HabitRead)
def update_habit(habit_id: int, body: HabitUpdate, session: SessionDep) -> Habit:
    habit = _get(session, habit_id)
    changes = body.model_dump(exclude_unset=True)
    if "archived" in changes:
        archived = changes.pop("archived")
        habit.archived_at = (habit.archived_at or now_utc()) if archived else None
    for name, value in changes.items():
        if name in REQUIRED_FIELDS and value is None:
            continue  # required fields: an explicit null means "unchanged"
        setattr(habit, name, value)
    _normalize(habit)
    session.add(habit)
    session.commit()
    session.refresh(habit)
    return habit


@router.put("/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder(body: HabitOrder, session: SessionDep) -> Response:
    habits = {h.id: h for h in session.exec(select(Habit)).all()}
    if set(body.ids) != set(habits) or len(body.ids) != len(habits):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "ids must list every habit exactly once")
    for position, habit_id in enumerate(body.ids):
        habits[habit_id].position = position
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: int, session: SessionDep) -> Response:
    """Deletes the habit with its whole history; archiving (PATCH archived=true) keeps it."""
    session.delete(_get(session, habit_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{habit_id}/days/{day}", response_model=DayStateRead)
def set_day(habit_id: int, day: dt.date, body: DayState, session: SessionDep) -> DayStateRead:
    """Ticks or unticks one day; idempotent, so queued offline writes can be replayed safely."""
    habit = _get(session, habit_id)
    if day > today() + dt.timedelta(days=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cannot tick a future day")
    if body.done and day < habit.start_date:
        habit.start_date = day  # ticking an earlier day means the habit already existed then
        session.add(habit)
    content = {name: getattr(body, name) for name in svc.ENTRY_FIELDS if name in body.model_fields_set}
    log = svc.set_day(session, habit, day, body.done, content)
    return DayStateRead(habit_id=habit_id, date=day, done=body.done, entry=_entry(session, log))


def _entry(session: Session, log: HabitLog | None) -> HabitEntry | None:
    if log is None or not (log.note or log.rating or log.ability_id):
        return None
    ability = session.get(Ability, log.ability_id) if log.ability_id else None
    return HabitEntry(note=log.note, rating=log.rating, ability_id=log.ability_id, ability=ability and ability.name)


# --- Dovednosti (E37) ------------------------------------------------------------------------


def _ability_read(state: ab.AbilityState) -> dict:
    level, level_name = ab.level_of(state.count)
    next_at = ab.LEVELS[level][0] if level < len(ab.LEVELS) else None
    last_note = next((e.note for e in reversed(state.entries) if e.note), None)
    return {
        **AbilityBrief.model_validate(state.ability).model_dump(),
        "count": state.count,
        "first_on": state.first_on,
        "last_on": state.last_on,
        "level": level,
        "level_name": level_name,
        "next_level_at": next_at,
        "last_note": last_note,
    }


def _ability_state(session: Session, ability_id: int) -> ab.AbilityState:
    state = next((s for s in ab.load(session) if s.ability.id == ability_id), None)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ability not found")
    return state


@router.get("/abilities", response_model=list[AbilityRead])
def list_abilities(session: SessionDep) -> list[dict]:
    """Every dovednost with its count, first / last day and level, the most recently used first."""
    return [_ability_read(s) for s in ab.load(session)]


@router.get("/abilities/{ability_id}", response_model=AbilityDetail)
def get_ability(ability_id: int, session: SessionDep) -> dict:
    state = _ability_state(session, ability_id)
    entries = [AbilityEntryRead(**vars(e)) for e in reversed(state.entries)]
    return {**_ability_read(state), "entries": entries}


@router.patch("/abilities/{ability_id}", response_model=AbilityRead)
def update_ability(ability_id: int, body: AbilityUpdate, session: SessionDep) -> dict:
    """Renames (a name another dovednost already has is refused: merge instead) or sets the icon."""
    ability = _ability_state(session, ability_id).ability
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name"):
        other = ab.find(session, changes["name"])
        if other is not None and other.id != ability.id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Dovednost {other.name} už existuje, slučte je")
        ability.name, ability.key = ab.clean_name(changes["name"]), ab.ability_key(changes["name"])
    if "icon" in changes:
        ability.icon = changes["icon"] or None
    session.add(ability)
    session.commit()
    return _ability_read(_ability_state(session, ability_id))


@router.post("/abilities/{ability_id}/merge", response_model=AbilityRead)
def merge_ability(ability_id: int, body: AbilityMerge, session: SessionDep) -> dict:
    """Moves every entry of this dovednost to `into_id` and deletes this one."""
    if body.into_id == ability_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cannot merge a dovednost into itself")
    source = _ability_state(session, ability_id).ability
    target = _ability_state(session, body.into_id).ability
    ab.merge(session, source, target)
    return _ability_read(_ability_state(session, body.into_id))


@router.delete("/abilities/{ability_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ability(ability_id: int, session: SessionDep) -> Response:
    """Deletes the dovednost; its entries keep their notes and stars."""
    session.delete(_ability_state(session, ability_id).ability)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
