"""Habit tracker "Rutina" (E20, docs/habits-module-spec.md)."""

import datetime as dt

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import SessionDep
from app.models.habits import AutoRule, Habit, HabitFrequency
from app.schemas.habits import (
    Board,
    BoardHabit,
    DayState,
    DayStateRead,
    HabitCreate,
    HabitOrder,
    HabitRead,
    HabitUpdate,
)
from app.services import habits as svc
from app.timeutils import now_utc, today

router = APIRouter(prefix="/api/habits", tags=["habits"])

THRESHOLD_RULES = {AutoRule.steps, AutoRule.sleep, AutoRule.protein}


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
            )
            for d in days
        ],
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
        if name in {"title", "frequency", "weekly_target", "points", "is_bonus", "start_date"} and value is None:
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
    svc.set_day(session, habit, day, body.done)
    return DayStateRead(habit_id=habit_id, date=day, done=body.done)
