"""Side quests (E45, docs/side-quests-module-spec.md)."""

import datetime as dt

from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import Session

from app.database import SessionDep
from app.models.side_quests import SideQuest
from app.schemas.side_quests import (
    CategoryInfo,
    DurationInfo,
    SideQuestBoard,
    SideQuestCreate,
    SideQuestRead,
    SideQuestUpdate,
    WeekQuest,
)
from app.services import habits as hs
from app.services import quests as qs
from app.services import side_quests as svc
from app.timeutils import today

router = APIRouter(prefix="/api/side-quests", tags=["side-quests"])

REQUIRED = {"title", "category", "duration", "active", "done_before_app"}  # null = unchanged


def _get(session: Session, quest_id: int) -> SideQuest:
    quest = session.get(SideQuest, quest_id)
    if quest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Side quest not found")
    return quest


def _read(state: svc.QuestState) -> SideQuestRead:
    quest = state.quest
    return SideQuestRead(**quest.model_dump(), done=state.done, xp=state.xp if state.done else svc.full_xp(quest))


def _item(session: Session, quest: SideQuest) -> SideQuestRead:
    session.refresh(quest)
    return _read(svc.QuestState(quest, svc.full_xp(quest) if svc.pays(quest) else 0))


@router.get("", response_model=SideQuestBoard)
def board(session: SessionDep) -> SideQuestBoard:
    """Every side quest with what it pays, and this week's side-quest quest; the client filters and groups."""
    on = today()
    states = svc.load(session, on)
    monday = hs.week_start(on)
    week_titles = [s.quest.title for s in states if s.xp and s.quest.done_on and s.quest.done_on >= monday]
    return SideQuestBoard(
        today=on,
        items=[_read(s) for s in states],
        durations=[DurationInfo(key=key, name=name, xp=xp) for key, (name, xp) in svc.DURATIONS.items()],
        categories=[CategoryInfo(key=key, name=name, skill=skill) for key, (name, skill) in svc.CATEGORIES.items()],
        week=WeekQuest(
            week_start=monday,
            active=monday >= qs.SIDE_QUEST_FROM,
            done=len(week_titles),
            xp=qs.QUEST_XP["side"],
            titles=week_titles,
        ),
        xp_total=sum(g.amount for g in svc.gains(states)),
    )


@router.post("", response_model=SideQuestRead, status_code=status.HTTP_201_CREATED)
def create_quest(body: SideQuestCreate, session: SessionDep) -> SideQuestRead:
    quest = SideQuest(**body.model_dump())
    session.add(quest)
    session.commit()
    return _item(session, quest)


@router.patch("/{quest_id}", response_model=SideQuestRead)
def update_quest(quest_id: int, body: SideQuestUpdate, session: SessionDep) -> SideQuestRead:
    """Edit, complete (done_on), un-complete (done_on null), start (active); idempotent."""
    quest = _get(session, quest_id)
    changes = body.model_dump(exclude_unset=True)
    if (day := changes.get("done_on")) is not None and day > today() + dt.timedelta(days=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cannot complete a future day")
    for name, value in changes.items():
        if name in REQUIRED and value is None:
            continue
        setattr(quest, name, value)
    if changes.get("done_on") is not None:
        quest.done_before_app, quest.active = False, False
    if quest.done_before_app:
        quest.done_on, quest.active = None, False
    session.add(quest)
    session.commit()
    return _item(session, quest)


@router.delete("/{quest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quest(quest_id: int, session: SessionDep) -> Response:
    session.delete(_get(session, quest_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
