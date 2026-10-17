"""Strava OAuth + activity polling (docs/SPEC.md §6.5, decision E10). No public webhook needed."""

import datetime as dt
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlmodel import Session, select

from app.config import settings
from app.models.integrations import IntegrationToken
from app.models.running import Activity
from app.services.run_analysis import current_lthr, runs_missing_streams, store_streams
from app.services.run_metrics import STREAM_KEYS
from app.timeutils import now_utc

PROVIDER = "strava"
AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_URL = "https://www.strava.com/api/v3"
SCOPE = "activity:read_all"
PER_PAGE = 100
# Re-read a week before the newest known activity: late uploads (watch -> Samsung Health -> Strava) start earlier
SYNC_OVERLAP = dt.timedelta(days=7)
# Calories only come from the per-activity detail endpoint; fetch it for recent activities, within a budget
DETAIL_WINDOW = dt.timedelta(days=14)
# RPE and the description (fueling log, pain notes) are often added after the run: re-read recent ones
DETAIL_REFRESH = dt.timedelta(hours=36)
MAX_DETAILS_PER_SYNC = 20
# Per-second streams for stream metrics (E12); the history backfills a few runs per sync
STREAMS_PER_SYNC = 10
REFRESH_MARGIN = dt.timedelta(minutes=5)


class StravaError(Exception):
    pass


class StravaNotConfiguredError(StravaError):
    pass


class StravaNotConnectedError(StravaError):
    pass


class StravaRateLimitedError(StravaError):
    pass


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    details_fetched: int = 0
    streams_fetched: int = 0
    streams_pending: int = 0  # runs still without streams after this sync (backfill in progress)
    complete: bool = True  # False when the activity listing was rate-limited; the cursor is then left unchanged


def require_config() -> tuple[str, str]:
    if not settings.strava_client_id or not settings.strava_client_secret:
        raise StravaNotConfiguredError("Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET")
    return settings.strava_client_id, settings.strava_client_secret


def authorize_url(redirect_uri: str, state: str) -> str:
    client_id, _ = require_config()
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _store_token(session: Session, payload: dict[str, Any]) -> IntegrationToken:
    token = session.get(IntegrationToken, PROVIDER) or IntegrationToken(
        provider=PROVIDER, access_token="", refresh_token="", expires_at=now_utc()
    )
    token.access_token = payload["access_token"]
    token.refresh_token = payload["refresh_token"]
    token.expires_at = dt.datetime.fromtimestamp(payload["expires_at"], tz=dt.UTC)
    if athlete := payload.get("athlete"):
        token.athlete_id = str(athlete["id"])
    session.add(token)
    return token


def exchange_code(session: Session, http: httpx.Client, code: str) -> IntegrationToken:
    client_id, client_secret = require_config()
    response = http.post(
        TOKEN_URL,
        data={"client_id": client_id, "client_secret": client_secret, "code": code, "grant_type": "authorization_code"},
    )
    if response.status_code != 200:
        raise StravaError(f"Token exchange failed ({response.status_code})")
    token = _store_token(session, response.json())
    session.commit()
    return token


def _access_token(session: Session, http: httpx.Client, now: dt.datetime) -> str:
    token = session.get(IntegrationToken, PROVIDER)
    if token is None:
        raise StravaNotConnectedError("Strava is not connected")
    if token.expires_at - REFRESH_MARGIN <= now:
        client_id, client_secret = require_config()
        response = http.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            },
        )
        if response.status_code in (400, 401):
            raise StravaNotConnectedError("Strava authorization was revoked; connect again")
        response.raise_for_status()
        token = _store_token(session, response.json())
        session.commit()
    return token.access_token


def map_activity(data: dict[str, Any]) -> dict[str, Any]:
    def rounded(key: str) -> int | None:
        value = data.get(key)
        return round(value) if value is not None else None

    return {
        "external_id": f"strava:{data['id']}",
        "source": PROVIDER,
        "start_time": dt.datetime.fromisoformat(data["start_date"].replace("Z", "+00:00")),
        "activity_type": data.get("sport_type") or data.get("type") or "Workout",
        "distance_meters": float(data.get("distance") or 0),
        "duration_seconds": int(data.get("moving_time") or data.get("elapsed_time") or 0),
        "avg_hr": rounded("average_heartrate"),
        "max_hr": rounded("max_heartrate"),
        "calories": rounded("calories"),
        "notes": data.get("name"),
    }


def _get(http: httpx.Client, path: str, access_token: str, params: dict[str, Any] | None = None) -> Any:
    response = http.get(f"{API_URL}{path}", params=params, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code == 429:
        raise StravaRateLimitedError("Strava rate limit reached")
    if response.status_code == 401:
        raise StravaNotConnectedError("Strava rejected the access token; connect again")
    response.raise_for_status()
    return response.json()


def _strava_id(activity: Activity) -> str:
    return (activity.external_id or "").removeprefix("strava:")


def _apply_detail(activity: Activity, detail: dict[str, Any]) -> None:
    if detail.get("calories") is not None:
        activity.calories = round(detail["calories"])
    if detail.get("perceived_exertion") is not None:
        activity.rpe = round(detail["perceived_exertion"])
    activity.description = detail.get("description") or activity.description
    activity.notes = detail.get("name") or activity.notes


def sync_activities(session: Session, http: httpx.Client, now: dt.datetime | None = None) -> SyncResult:
    now = now or now_utc()
    access_token = _access_token(session, http, now)
    token = session.get(IntegrationToken, PROVIDER)
    assert token is not None
    after = token.last_activity_start - SYNC_OVERLAP if token.last_activity_start else None

    result = SyncResult()
    newest = token.last_activity_start
    needs_details: list[Activity] = []
    listing_done = False
    try:
        page = 1
        while True:
            params: dict[str, Any] = {"per_page": PER_PAGE, "page": page}
            if after is not None:
                params["after"] = int(after.timestamp())
            items = _get(http, "/athlete/activities", access_token, params)
            if not items:
                break
            for item in items:
                fields = map_activity(item)
                activity = session.exec(select(Activity).where(Activity.external_id == fields["external_id"])).first()
                if activity is None:
                    activity = Activity(**fields)
                    result.created += 1
                else:
                    if fields["calories"] is None:
                        fields["calories"] = activity.calories  # summaries carry no calories; keep fetched ones
                    for key, value in fields.items():
                        setattr(activity, key, value)
                    result.updated += 1
                session.add(activity)
                newest = max(newest, activity.start_time) if newest else activity.start_time
                age = now - activity.start_time
                if age <= DETAIL_REFRESH or (activity.calories is None and age <= DETAIL_WINDOW):
                    needs_details.append(activity)
            page += 1
        listing_done = True
        session.flush()

        detailed: set[int] = set()
        for activity in sorted(needs_details, key=lambda a: a.start_time, reverse=True)[:MAX_DETAILS_PER_SYNC]:
            _apply_detail(activity, _get(http, f"/activities/{_strava_id(activity)}", access_token))
            detailed.add(activity.id or 0)
            result.details_fetched += 1

        lthr = current_lthr(session)
        for activity in runs_missing_streams(session, STREAMS_PER_SYNC):
            if activity.id not in detailed:
                _apply_detail(activity, _get(http, f"/activities/{_strava_id(activity)}", access_token))
                result.details_fetched += 1
            streams = _get(
                http,
                f"/activities/{_strava_id(activity)}/streams",
                access_token,
                {"keys": STREAM_KEYS, "key_by_type": "true"},
            )
            store_streams(session, activity, streams, lthr)
            result.streams_fetched += 1
    except StravaRateLimitedError:
        result.complete = listing_done
    session.flush()
    result.streams_pending = len(runs_missing_streams(session, 10_000))

    token.last_synced_at = now
    if result.complete:
        token.last_activity_start = newest
    session.add(token)
    session.commit()
    return result
