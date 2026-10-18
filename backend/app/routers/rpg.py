"""RPG layer (E22): character, XP history with reasons, pauses."""

import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import Session, col, select

from app.database import SessionDep
from app.models.rpg import RpgPause
from app.schemas.rpg import Character, NextTitle, PauseIn, PauseRead, PauseUpdate, Skill, XpDay, XpEntryRead
from app.services import rpg
from app.services.habits import week_start
from app.timeutils import today

router = APIRouter(prefix="/api/rpg", tags=["rpg"])


@router.get("/character", response_model=Character)
def character(session: SessionDep) -> Character:
    on = today()
    ledger = rpg.build_ledger(session, on)
    level = rpg.level_of(ledger.total)
    upcoming = rpg.next_title(level)
    forgiven = [d for d in ledger.forgiven if (d.year, d.month) == (on.year, on.month)]
    return Character(
        level=level,
        title=rpg.title_of(level),
        next_title=NextTitle(level=upcoming[0], title=upcoming[1]) if upcoming else None,
        xp_total=ledger.total,
        level_start_xp=rpg.level_start(level),
        next_level_xp=rpg.level_start(level + 1),
        today_xp=sum(e.amount for e in ledger.entries if e.date == on),
        week_xp=sum(e.amount for e in ledger.entries if e.date >= week_start(on)),
        multiplier=ledger.multiplier,
        week_streak=ledger.week_streak,
        forgiven_this_month=forgiven[0] if forgiven else None,
        paused=ledger.paused_today,
        skills=[_skill(ledger, key, name, source) for key, name, source in rpg.SKILLS],
    )


def _skill(ledger: rpg.Ledger, key: str, name: str, source: str) -> Skill:
    state = ledger.skills.get(key) or rpg.SkillState(key)
    level = rpg.skill_level_of(state.xp)
    return Skill(
        key=key,
        name=name,
        source=source,
        xp=state.xp,
        level=level,
        level_start_xp=rpg.skill_level_start(level),
        next_level_xp=rpg.skill_level_start(level + 1),
        idle_days=state.idle_days,
        rusting=state.idle_days >= rpg.RUST_START_DAYS,
        losing=state.idle_days >= rpg.RUST_LOSS_DAYS,
    )


@router.get("/history", response_model=list[XpDay])
def history(session: SessionDep, days: int = 30) -> list[XpDay]:
    """XP entries of the last `days` days, newest day first; days without any entry are left out."""
    on = today()
    since = on - dt.timedelta(days=max(1, min(days, 3650)) - 1)
    by_day: dict[dt.date, list[rpg.XpEntry]] = defaultdict(list)
    for entry in rpg.build_ledger(session, on).entries:
        if entry.date >= since:
            by_day[entry.date].append(entry)
    return [
        XpDay(
            date=day,
            total=sum(e.amount for e in entries),
            entries=[XpEntryRead(amount=e.amount, kind=e.kind, text=e.text) for e in entries],
        )
        for day, entries in sorted(by_day.items(), reverse=True)
    ]


# --- Pauses ----------------------------------------------------------------------------------


def _check_overlap(session: Session, start: dt.date, end: dt.date | None, pause_id: int | None = None) -> None:
    if end is not None and end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date is before start_date")
    for other in session.exec(select(RpgPause)):
        if other.id == pause_id:
            continue
        if start <= (other.end_date or dt.date.max) and other.start_date <= (end or dt.date.max):
            raise HTTPException(status.HTTP_409_CONFLICT, "Overlaps another pause")


@router.get("/pauses", response_model=list[PauseRead])
def list_pauses(session: SessionDep) -> list[RpgPause]:
    return list(session.exec(select(RpgPause).order_by(col(RpgPause.start_date).desc())).all())


@router.post("/pauses", response_model=PauseRead, status_code=status.HTTP_201_CREATED)
def create_pause(body: PauseIn, session: SessionDep) -> RpgPause:
    _check_overlap(session, body.start_date, body.end_date)
    pause = RpgPause(**body.model_dump())
    session.add(pause)
    session.commit()
    session.refresh(pause)
    return pause


@router.patch("/pauses/{pause_id}", response_model=PauseRead)
def update_pause(pause_id: int, body: PauseUpdate, session: SessionDep) -> RpgPause:
    pause = session.get(RpgPause, pause_id)
    if pause is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pause not found")
    changes = body.model_dump(exclude_unset=True)
    end = changes.get("end_date", pause.end_date)
    _check_overlap(session, pause.start_date, end, pause_id)
    for name, value in changes.items():
        setattr(pause, name, value)
    session.add(pause)
    session.commit()
    session.refresh(pause)
    return pause


@router.delete("/pauses/{pause_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pause(pause_id: int, session: SessionDep) -> Response:
    pause = session.get(RpgPause, pause_id)
    if pause is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pause not found")
    session.delete(pause)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
