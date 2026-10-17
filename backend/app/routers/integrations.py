import datetime as dt
import secrets
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import select

from app.config import settings
from app.database import SessionDep
from app.models.body import HealthSourceStatus
from app.models.integrations import IntegrationToken
from app.services import strava_client as strava
from app.timeutils import now_utc

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

STATE_TTL = dt.timedelta(minutes=10)
# OAuth CSRF states; in memory is fine for a single-worker, single-user app
_pending_states: dict[str, dt.datetime] = {}


def get_http() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=20) as client:
        yield client


HttpDep = Annotated[httpx.Client, Depends(get_http)]


class StravaStatus(BaseModel):
    configured: bool
    connected: bool
    athlete_id: str | None = None
    last_synced_at: dt.datetime | None = None
    last_activity_start: dt.datetime | None = None


class WebhookSourceStatus(BaseModel):
    last_received_at: dt.datetime
    last_day: dt.date


class IntegrationsStatus(BaseModel):
    strava: StravaStatus
    webhooks_enabled: bool
    webhook_sources: dict[str, WebhookSourceStatus]


def _redirect_uri(request: Request) -> str:
    base = settings.public_base_url or str(request.base_url)
    return f"{base.rstrip('/')}/api/integrations/strava/callback"


@router.get("/strava/connect")
def strava_connect(request: Request) -> RedirectResponse:
    now = now_utc()
    for state, created in list(_pending_states.items()):
        if now - created > STATE_TTL:
            del _pending_states[state]
    state = secrets.token_urlsafe(24)
    try:
        url = strava.authorize_url(_redirect_uri(request), state)
    except strava.StravaNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    _pending_states[state] = now
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/strava/callback")
def strava_callback(
    session: SessionDep,
    http: HttpDep,
    state: str,
    code: str | None = None,
    scope: str = "",
    error: str | None = None,
) -> RedirectResponse:
    created = _pending_states.pop(state, None)
    if created is None or now_utc() - created > STATE_TTL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or expired OAuth state; start again")
    if error or not code:
        return RedirectResponse("/settings?strava=denied", status_code=status.HTTP_302_FOUND)
    if "activity:read" not in scope:
        return RedirectResponse("/settings?strava=missing_scope", status_code=status.HTTP_302_FOUND)
    try:
        strava.exchange_code(session, http, code)
    except strava.StravaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return RedirectResponse("/settings?strava=connected", status_code=status.HTTP_302_FOUND)


@router.post("/strava/sync", response_model=strava.SyncResult)
def strava_sync(session: SessionDep, http: HttpDep) -> strava.SyncResult:
    try:
        return strava.sync_activities(session, http)
    except strava.StravaNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except strava.StravaNotConnectedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Strava request failed: {exc}") from None


@router.get("/status", response_model=IntegrationsStatus)
def integrations_status(session: SessionDep) -> IntegrationsStatus:
    token = session.get(IntegrationToken, strava.PROVIDER)
    return IntegrationsStatus(
        strava=StravaStatus(
            configured=bool(settings.strava_client_id and settings.strava_client_secret),
            connected=token is not None,
            athlete_id=token.athlete_id if token else None,
            last_synced_at=token.last_synced_at if token else None,
            last_activity_start=token.last_activity_start if token else None,
        ),
        webhooks_enabled=bool(settings.webhook_token),
        webhook_sources={
            s.source: WebhookSourceStatus(last_received_at=s.last_received_at, last_day=s.last_day)
            for s in session.exec(select(HealthSourceStatus)).all()
        },
    )
