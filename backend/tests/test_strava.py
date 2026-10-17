"""Strava OAuth + sync against a fake Strava API (httpx.MockTransport); no network access."""

import datetime as dt
from collections.abc import Callable, Iterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import settings
from app.main import app
from app.models.integrations import IntegrationToken
from app.models.running import Activity
from app.routers import integrations
from app.routers.integrations import get_http
from app.services.strava_client import map_activity, sync_activities

NOW = dt.datetime(2026, 10, 17, 12, 0, tzinfo=dt.UTC)


def strava_activity(activity_id: int, start: dt.datetime, **extra) -> dict:
    return {
        "id": activity_id,
        "name": "Morning Run",
        "sport_type": "Run",
        "type": "Run",
        "start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "distance": 10000.0,
        "moving_time": 3000,
        "elapsed_time": 3100,
        "average_heartrate": 147.6,
        "max_heartrate": 171.2,
        **extra,
    }


class FakeStrava:
    def __init__(self, pages: list[list[dict]], details: dict[int, dict] | None = None, rate_limit_page: int = 0):
        self.pages, self.details, self.rate_limit_page = pages, details or {}, rate_limit_page
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/oauth/token":
            form = parse_qs(request.content.decode())
            body = {"access_token": "new-access", "refresh_token": "new-refresh", "expires_at": NOW.timestamp() + 21600}
            if form["grant_type"] == ["authorization_code"]:
                body["athlete"] = {"id": 42}
            return httpx.Response(200, json=body)
        if path == "/api/v3/athlete/activities":
            page = int(request.url.params["page"])
            if page == self.rate_limit_page:
                return httpx.Response(429, json={"message": "Rate Limit Exceeded"})
            return httpx.Response(200, json=self.pages[page - 1] if page <= len(self.pages) else [])
        if path.endswith("/streams"):
            seconds = list(range(0, 1800))
            return httpx.Response(
                200,
                json={
                    "time": {"data": seconds},
                    "velocity_smooth": {"data": [3.0] * len(seconds)},
                    "heartrate": {"data": [145] * len(seconds)},
                    "moving": {"data": [True] * len(seconds)},
                    "grade_smooth": {"data": [0.0] * len(seconds)},
                },
            )
        if path.startswith("/api/v3/activities/"):
            return httpx.Response(200, json=self.details.get(int(path.rsplit("/", 1)[1]), {}))
        return httpx.Response(404)

    def activity_list_params(self) -> list[dict[str, str]]:
        return [dict(r.url.params) for r in self.requests if r.url.path == "/api/v3/athlete/activities"]


@pytest.fixture(autouse=True)
def strava_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "strava_client_id", "123")
    monkeypatch.setattr(settings, "strava_client_secret", "secret")
    monkeypatch.setattr(settings, "public_base_url", "https://hub.example.ts.net")


@pytest.fixture
def connected(session: Session) -> IntegrationToken:
    token = IntegrationToken(
        provider="strava",
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=NOW + dt.timedelta(hours=3),
    )
    session.add(token)
    session.commit()
    return token


@pytest.fixture
def fake_http() -> Iterator[Callable[[FakeStrava], httpx.Client]]:
    clients: list[httpx.Client] = []

    def make(fake: FakeStrava) -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(fake))
        clients.append(client)
        app.dependency_overrides[get_http] = lambda: client
        return client

    yield make
    for client in clients:
        client.close()


def test_map_activity() -> None:
    mapped = map_activity(strava_activity(7, NOW, calories=612.4))

    assert mapped["external_id"] == "strava:7"
    assert mapped["start_time"] == NOW
    assert (mapped["avg_hr"], mapped["max_hr"], mapped["calories"]) == (148, 171, 612)
    assert mapped["duration_seconds"] == 3000
    assert mapped["notes"] == "Morning Run"


def test_first_sync_backfills_pages_and_fetches_details_for_recent_runs(
    session: Session, connected: IntegrationToken, fake_http
) -> None:
    recent, old = NOW - dt.timedelta(days=1), NOW - dt.timedelta(days=60)
    fake = FakeStrava([[strava_activity(2, recent), strava_activity(1, old)]], details={2: {"calories": 700}})

    result = sync_activities(session, fake_http(fake), now=NOW)

    # recent run: detail refresh + streams; old run: detail and streams for the backfill
    assert (result.created, result.updated, result.details_fetched, result.complete) == (2, 0, 2, True)
    assert (result.streams_fetched, result.streams_pending) == (2, 0)
    calories = {a.external_id: a.calories for a in session.exec(select(Activity)).all()}
    assert calories == {"strava:2": 700, "strava:1": None}
    assert "after" not in fake.activity_list_params()[0]
    assert session.get(IntegrationToken, "strava").last_activity_start == recent


def test_next_sync_overlaps_a_week_and_updates_existing(
    session: Session, connected: IntegrationToken, fake_http
) -> None:
    start = NOW - dt.timedelta(days=1)
    sync_activities(session, fake_http(FakeStrava([[strava_activity(2, start, calories=500)]])), now=NOW)

    fake = FakeStrava([[strava_activity(2, start, name="Renamed")]])
    result = sync_activities(session, fake_http(fake), now=NOW)

    assert (result.created, result.updated) == (0, 1)
    assert fake.activity_list_params()[0]["after"] == str(int((start - dt.timedelta(days=7)).timestamp()))
    activity = session.exec(select(Activity)).one()
    assert activity.notes == "Renamed"
    assert activity.calories == 500  # summary has no calories; the fetched value is kept


def test_rate_limit_keeps_partial_results_but_not_the_cursor(
    session: Session, connected: IntegrationToken, fake_http
) -> None:
    fake = FakeStrava([[strava_activity(3, NOW - dt.timedelta(days=90))]], rate_limit_page=2)

    result = sync_activities(session, fake_http(fake), now=NOW)

    assert result.complete is False
    assert result.created == 1
    assert session.get(IntegrationToken, "strava").last_activity_start is None


def test_expired_token_is_refreshed(session: Session, connected: IntegrationToken, fake_http) -> None:
    connected.expires_at = NOW - dt.timedelta(minutes=1)
    session.add(connected)
    session.commit()
    fake = FakeStrava([[]])

    sync_activities(session, fake_http(fake), now=NOW)

    assert fake.requests[0].url.path == "/oauth/token"
    assert fake.requests[1].headers["Authorization"] == "Bearer new-access"
    assert session.get(IntegrationToken, "strava").refresh_token == "new-refresh"


def test_connect_redirects_to_strava_with_state(client: TestClient) -> None:
    response = client.get("/api/integrations/strava/connect", follow_redirects=False)

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["client_id"] == ["123"]
    assert query["redirect_uri"] == ["https://hub.example.ts.net/api/integrations/strava/callback"]
    assert query["scope"] == ["activity:read_all"]
    assert query["state"][0] in integrations._pending_states


def test_callback_exchanges_code_and_stores_token(client: TestClient, session: Session, fake_http) -> None:
    fake_http(FakeStrava([]))
    state = parse_qs(
        urlparse(client.get("/api/integrations/strava/connect", follow_redirects=False).headers["location"]).query
    )["state"][0]

    response = client.get(
        "/api/integrations/strava/callback",
        params={"state": state, "code": "abc", "scope": "read,activity:read_all"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/settings?strava=connected"
    token = session.get(IntegrationToken, "strava")
    assert (token.access_token, token.athlete_id) == ("new-access", "42")


def test_callback_rejects_unknown_state(client: TestClient) -> None:
    response = client.get("/api/integrations/strava/callback", params={"state": "forged", "code": "abc"})

    assert response.status_code == 400


def test_sync_endpoint_requires_connection(client: TestClient) -> None:
    assert client.post("/api/integrations/strava/sync").status_code == 409


def test_status_reports_strava_and_webhook_sources(
    client: TestClient, connected: IntegrationToken, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "webhook_token", "t")
    client.post(
        "/api/webhooks/health",
        json={"source": "apple_health", "days": ["2026-10-17"]},
        headers={"X-Webhook-Token": "t"},
    )

    status = client.get("/api/integrations/status").json()

    assert status["strava"]["configured"] is True
    assert status["strava"]["connected"] is True
    assert status["webhooks_enabled"] is True
    assert status["webhook_sources"]["apple_health"]["last_day"] == "2026-10-17"
