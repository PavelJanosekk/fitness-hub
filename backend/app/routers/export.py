import datetime as dt
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.database import SessionDep
from app.services.repo_export import (
    ExportError,
    ExportNotConfiguredError,
    ExportResult,
    PublicRepoError,
    export_now,
    state,
)

router = APIRouter(prefix="/api/export", tags=["export"])


def get_http() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=60) as client:
        yield client


HttpDep = Annotated[httpx.Client, Depends(get_http)]


class ExportStatus(BaseModel):
    configured: bool
    repo: str | None
    branch: str
    folder: str
    export_hour: int
    last_run_at: dt.datetime | None
    last_success_at: dt.datetime | None
    last_commit_sha: str | None
    last_changed_files: int
    last_error: str | None
    public_ok: bool  # the user confirmed exporting into this repo although it is public


@router.get("", response_model=ExportStatus)
def export_status(session: SessionDep) -> ExportStatus:
    current = state(session)
    return ExportStatus(
        configured=bool(settings.export_repo and settings.github_token),
        repo=settings.export_repo,
        branch=settings.export_branch,
        folder=settings.export_dir,
        export_hour=settings.export_hour,
        last_run_at=current.last_run_at,
        last_success_at=current.last_success_at,
        last_commit_sha=current.last_commit_sha,
        last_changed_files=current.last_changed_files,
        last_error=current.last_error,
        public_ok=bool(settings.export_repo) and current.public_ok_repo == settings.export_repo,
    )


@router.post("/sync", response_model=ExportResult)
def export_sync(session: SessionDep, http: HttpDep, confirm_public: bool = False) -> ExportResult:
    """409 with code "public_repo" asks the client to confirm sharing into a public repo (confirm_public=true)."""
    try:
        return export_now(session, http, confirm_public=confirm_public)
    except ExportNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except PublicRepoError:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "public_repo", "repo": settings.export_repo}) from None
    except ExportError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None


@router.delete("/public-consent", status_code=status.HTTP_204_NO_CONTENT)
def revoke_public_consent(session: SessionDep) -> None:
    """Stop exporting into the public repo; the next export asks again."""
    current = state(session)
    current.public_ok_repo = None
    session.add(current)
    session.commit()
