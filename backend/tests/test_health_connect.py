"""Life Dashboard Companion receiver, with payloads shaped like its documented webhook format."""

import datetime as dt
import hashlib
import hmac
import json
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import settings

PRAGUE = ZoneInfo("Europe/Prague")
DAY = dt.date(2026, 10, 14)
TOKEN = "test-token"
SAMSUNG = "com.sec.android.app.shealth"
URL = "/api/webhooks/health-connect"


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_token", TOKEN)
    monkeypatch.setattr(settings, "health_connect_secret", None)
    monkeypatch.setattr(settings, "health_connect_origins", SAMSUNG)


def utc(hour: int, minute: int = 0, day: dt.date = DAY) -> str:
    local = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=PRAGUE)
    return local.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # the app sends UTC with "Z"


def step(uuid: str, start: str, end: str, count: int, source: str = SAMSUNG) -> dict:
    return {"uuid": uuid, "source": source, "count": count, "start_time": start, "end_time": end}


def send(client: TestClient, payload: dict, **headers: str) -> dict:
    body = {"timestamp": utc(23), "app_version": "1.23.0", "source": "health_connect", **payload}
    response = client.post(URL, content=json.dumps(body), headers={"X-Webhook-Token": TOKEN, **headers})
    assert response.status_code == 200, response.text
    return response.json()


def steps_of(client: TestClient) -> dict:
    return client.get("/api/metrics/steps-breakdown", params={"date": DAY.isoformat()}).json()


def test_records_merge_with_the_iphone_per_bucket(client: TestClient) -> None:
    send(client, {"sequence": 1, "steps": [step("a", utc(8), utc(8, 15), 1200), step("b", utc(18), utc(18, 15), 800)]})
    client.post(
        "/api/webhooks/health",
        json={
            "source": "apple_health",
            "days": [DAY.isoformat()],
            "steps": [
                {"start": utc(8), "end": utc(8, 15), "count": 1000},
                {"start": utc(12), "end": utc(12, 15), "count": 500},
            ],
        },
        headers={"X-Webhook-Token": TOKEN},
    )

    breakdown = steps_of(client)

    assert (breakdown["steps"], breakdown["steps_method"]) == (2500, "buckets")
    assert breakdown["source_totals"] == {"samsung_health": 2000, "apple_health": 1500}


def test_resent_and_edited_records_are_not_double_counted(client: TestClient) -> None:
    send(client, {"sequence": 1, "steps": [step("a", utc(9), utc(10), 3000)]})
    send(client, {"sequence": 1, "steps": [step("a", utc(9), utc(10), 3000)]})  # retry of the same payload

    result = send(client, {"sequence": 2, "steps": [step("a", utc(9), utc(10), 3400)]})  # source edited it

    assert result["days"][0]["steps"] == 3400


def test_deleted_records_are_removed(client: TestClient) -> None:
    send(client, {"sequence": 1, "steps": [step("a", utc(9), utc(10), 3000), step("b", utc(11), utc(12), 1000)]})

    result = send(client, {"sequence": 2, "deleted_records": [{"type": "steps", "uuid": "a"}]})

    assert result["deleted"] == 1
    assert result["days"][0]["steps"] == 1000


def test_only_allowed_apps_count(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fit = "com.google.android.apps.fitness"
    payload = {"sequence": 1, "steps": [step("a", utc(9), utc(10), 3000), step("b", utc(9), utc(10), 2900, fit)]}

    assert send(client, payload)["days"][0]["steps"] == 3000

    monkeypatch.setattr(settings, "health_connect_origins", "*")
    assert send(client, {**payload, "sequence": 2})["days"][0]["steps"] == 5900


def test_sleep_goes_to_the_wake_up_day(client: TestClient) -> None:
    night = {
        "uuid": "n1",
        "source": SAMSUNG,
        "session_end_time": utc(6, 30),
        "duration_seconds": 7 * 3600,
        "stages": [],
    }

    result = send(client, {"sequence": 1, "sleep": [night]})

    assert result["days"] == [{"date": DAY.isoformat(), "steps": None, "steps_method": None, "sleep_hours": 7.0}]


def test_daily_totals_keep_the_highest_sequence(client: TestClient) -> None:
    def totals(sequence: int, value: int) -> dict:
        return {"sequence": sequence, "daily_totals": [{"date": DAY.isoformat(), "steps": value}]}

    send(client, totals(5, 6000))
    late = send(client, totals(3, 4000))  # an older payload delivered late
    newer = send(client, totals(6, 6500))

    assert late["days"] == []
    assert newer["days"][0]["steps"] == 6500


def test_daily_total_beats_an_incomplete_record_sum(client: TestClient) -> None:
    result = send(
        client,
        {
            "sequence": 1,
            "steps": [step("a", utc(9), utc(10), 1000)],
            "daily_totals": [{"date": DAY.isoformat(), "steps": 4200}],
        },
    )

    assert result["days"][0]["steps"] == 4200


def test_complete_buckets_are_stored_and_incomplete_ones_skipped(client: TestClient) -> None:
    buckets = [
        {"bucket_start": utc(8), "bucket_end": utc(9), "sample_count": 12, "total": 1840.0, "complete": True},
        {"bucket_start": utc(9), "bucket_end": utc(10), "sample_count": 3, "total": 200.0},
    ]

    result = send(client, {"sequence": 1, "steps": buckets, "_resolutions": {"steps": "1h"}})

    assert (result["stored"], result["ignored"]) == (1, 1)
    assert result["days"][0]["steps"] == 1840


def test_ios_companion_payloads_count_as_apple_health(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "health_connect_origins", "*")

    send(
        client,
        {"source": "healthkit_ios", "sequence": 1, "steps": [step("i", utc(9), utc(10), 2222, "com.apple.health")]},
    )

    assert steps_of(client)["source_totals"] == {"apple_health": 2222}


def test_test_ping_and_screen_time_are_accepted_and_ignored(client: TestClient) -> None:
    assert send(client, {"test": True, "message": "Test ping"})["stored"] == 0
    assert send(client, {"source": "screen_time", "sequence": 9})["days"] == []


def test_hmac_signature(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "health_connect_secret", " s3cret ")  # the app trims surrounding spaces
    body = json.dumps({"source": "health_connect", "sequence": 1, "steps": [step("a", utc(9), utc(10), 100)]}).encode()
    good = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()

    assert client.post(URL, content=body, headers={"X-Signature": good}).status_code == 200
    assert client.post(URL, content=body, headers={"X-Signature": "sha256=" + "0" * 64}).status_code == 401


def test_token_is_required_without_signature(client: TestClient) -> None:
    body = json.dumps({"source": "health_connect", "test": True})

    assert client.post(URL, content=body).status_code == 401
    assert client.post(URL, content=body, headers={"X-Webhook-Token": "wrong"}).status_code == 401


def test_malformed_payload_is_a_422(client: TestClient) -> None:
    response = client.post(
        URL, content=b'{"source": "health_connect", "sleep": [{"uuid": "x"}]}', headers={"X-Webhook-Token": TOKEN}
    )

    assert response.status_code == 422
