import datetime as dt
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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
    name: str
    date: dt.date
    distance_km: float | None
    is_goal_race: bool
    goal: str | None


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
    races = session.exec(select(Race).order_by(col(Race.date))).all()
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
