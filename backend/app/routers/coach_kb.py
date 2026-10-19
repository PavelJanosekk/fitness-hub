import datetime as dt
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlmodel import col, select

from app.config import settings
from app.database import SessionDep
from app.models.coach import CoachDocument, Race, TrainingWeek
from app.services.coach_kb import KBSyncResult, KnowledgeBaseError, profile, read_document, sync_knowledge_base

router = APIRouter(prefix="/api/coach", tags=["coach"])


def get_http() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=20) as client:
        yield client


HttpDep = Annotated[httpx.Client, Depends(get_http)]


class DocumentInfo(BaseModel):
    path: str
    sha: str
    fetched_at: dt.datetime
    characters: int


class RaceRead(BaseModel):
    id: int
    name: str
    date: dt.date
    distance_km: float | None
    is_goal_race: bool
    goal: str | None
    source: str


class RaceCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    date: dt.date
    distance_km: float | None = Field(default=None, gt=0, le=500)
    is_goal_race: bool = False
    goal: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class KBStatus(BaseModel):
    repo: str | None
    branch: str
    lthr: int | None
    max_hr: int | None
    kb_updated: dt.date | None
    last_synced_at: dt.datetime | None
    last_sync_error: str | None
    sync_warnings: list[str]
    documents: list[DocumentInfo]
    races: list[RaceRead]
    plan_weeks: int


class DocumentRead(BaseModel):
    path: str
    content: str
    fetched_at: dt.datetime


@router.get("/kb", response_model=KBStatus)
def kb_status(session: SessionDep) -> KBStatus:
    athlete = profile(session)
    docs = session.exec(select(CoachDocument).order_by(col(CoachDocument.path))).all()
    races = session.exec(select(Race).where(~col(Race.hidden)).order_by(col(Race.date))).all()
    return KBStatus(
        repo=settings.coach_kb_repo,
        branch=settings.coach_kb_branch,
        lthr=athlete.lthr,
        max_hr=athlete.max_hr,
        kb_updated=athlete.kb_updated,
        last_synced_at=athlete.last_synced_at,
        last_sync_error=athlete.last_sync_error,
        sync_warnings=athlete.sync_warnings or [],
        documents=[
            DocumentInfo(path=d.path, sha=d.sha, fetched_at=d.fetched_at, characters=len(d.content)) for d in docs
        ],
        races=[RaceRead.model_validate(r, from_attributes=True) for r in races],
        plan_weeks=len(session.exec(select(TrainingWeek.week_start)).all()),
    )


@router.post("/races", response_model=RaceRead, status_code=status.HTTP_201_CREATED)
def create_race(body: RaceCreate, session: SessionDep) -> RaceRead:
    """A race added in the app; it survives knowledge base syncs."""
    race = Race(**body.model_dump(exclude={"goal"}), goal=body.goal or None, source="user")
    session.add(race)
    session.commit()
    session.refresh(race)
    return RaceRead.model_validate(race, from_attributes=True)


@router.delete("/races/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_race(race_id: int, session: SessionDep) -> None:
    """Deletes a race added in the app; a knowledge base race is only hidden, so the next sync doesn't bring it back."""
    race = session.get(Race, race_id)
    if race is None or race.hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Race not found")
    if race.source == "user":
        session.delete(race)
    else:
        race.hidden = True
        session.add(race)
    session.commit()


@router.post("/kb/sync", response_model=KBSyncResult)
def kb_sync(session: SessionDep, http: HttpDep) -> KBSyncResult:
    if not settings.coach_kb_repo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Set COACH_KB_REPO")
    try:
        return sync_knowledge_base(session, http)
    except KnowledgeBaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None


@router.get("/kb/documents/{name}", response_model=DocumentRead)
def kb_document(name: str, session: SessionDep) -> DocumentRead:
    doc = read_document(session, name)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentRead(path=doc.path, content=doc.content, fetched_at=doc.fetched_at)
