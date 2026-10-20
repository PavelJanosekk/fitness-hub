import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services.health_ingest import distribute

PRAGUE = ZoneInfo("Europe/Prague")
DAY = dt.date(2026, 10, 14)
TOKEN = "test-token"


@pytest.fixture(autouse=True)
def webhook_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_token", TOKEN)


def at(hour: int, minute: int = 0, day: dt.date = DAY) -> str:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=PRAGUE).isoformat()


def push(client: TestClient, source: str, days: list[dt.date] | None = None, **payload) -> list[dict]:
    body = {"source": source, "days": [d.isoformat() for d in (days or [DAY])], **payload}
    response = client.post("/api/webhooks/health", json=body, headers={"X-Webhook-Token": TOKEN})
    assert response.status_code == 200, response.text
    return response.json()


def steps(*samples: tuple[str, str, float]) -> list[dict]:
    return [{"start": s, "end": e, "count": c} for s, e, c in samples]


def day_steps(client: TestClient) -> dict:
    return client.get("/api/metrics/steps-breakdown", params={"date": DAY.isoformat()}).json()


def test_distribute_splits_a_sample_proportionally_across_buckets() -> None:
    start = dt.datetime(2026, 10, 14, 8, 10, tzinfo=dt.UTC)
    lo, hi = dt.datetime(2026, 10, 14, tzinfo=dt.UTC), dt.datetime(2026, 10, 15, tzinfo=dt.UTC)

    buckets = distribute(start, start + dt.timedelta(minutes=10), 100, lo, hi)

    assert buckets == {
        dt.datetime(2026, 10, 14, 8, 0, tzinfo=dt.UTC): pytest.approx(50),
        dt.datetime(2026, 10, 14, 8, 15, tzinfo=dt.UTC): pytest.approx(50),
    }


def test_distribute_keeps_only_the_part_inside_the_day() -> None:
    lo, hi = dt.datetime(2026, 10, 14, tzinfo=dt.UTC), dt.datetime(2026, 10, 15, tzinfo=dt.UTC)
    across_midnight = dt.datetime(2026, 10, 14, 23, 50, tzinfo=dt.UTC)

    buckets = distribute(across_midnight, across_midnight + dt.timedelta(minutes=20), 200, lo, hi)

    assert sum(buckets.values()) == pytest.approx(100)


def test_the_day_is_the_source_with_the_most_steps(client: TestClient) -> None:
    # Both carried in the morning; phone only at noon; watch only in the evening. No per-bucket merge (E39)
    push(client, "apple_health", steps=steps((at(8), at(8, 15), 1000), (at(12), at(12, 15), 500)))
    result = push(client, "samsung_health", steps=steps((at(8), at(8, 15), 1200), (at(18), at(18, 15), 800)))

    assert result == [{"date": DAY.isoformat(), "steps": 2000, "steps_method": "max_daily", "sleep_hours": None}]
    breakdown = day_steps(client)
    assert breakdown["source_totals"] == {"apple_health": 1500, "samsung_health": 2000}
    assert len(breakdown["buckets"]) == 3


def test_daily_total_without_intervals_falls_back_to_max(client: TestClient) -> None:
    push(client, "apple_health", steps=steps((at(9), at(10), 5000)))
    result = push(client, "samsung_health", daily=[{"date": DAY.isoformat(), "metric": "steps_total", "value": 7000}])

    assert result[0]["steps"] == 7000
    assert result[0]["steps_method"] == "max_daily"


def test_single_source(client: TestClient) -> None:
    result = push(client, "apple_health", steps=steps((at(9), at(10), 4321)))

    assert (result[0]["steps"], result[0]["steps_method"]) == (4321, "single_source")


def test_a_new_push_replaces_the_day_for_that_source(client: TestClient) -> None:
    push(client, "apple_health", steps=steps((at(9), at(10), 3000), (at(15), at(16), 2000)))
    push(client, "samsung_health", steps=steps((at(20), at(21), 100)))

    result = push(client, "apple_health", steps=steps((at(9), at(10), 3500)))

    assert result[0]["steps"] == 3500
    assert day_steps(client)["source_totals"] == {"apple_health": 3500, "samsung_health": 100}


def test_samples_outside_the_listed_days_are_ignored(client: TestClient) -> None:
    other_day = DAY - dt.timedelta(days=3)

    result = push(client, "apple_health", steps=steps((at(9, day=other_day), at(10, day=other_day), 999)))

    assert result[0]["steps"] is None


def test_manual_steps_win_over_devices(client: TestClient) -> None:
    push(client, "apple_health", steps=steps((at(9), at(10), 4000)))
    client.post("/api/metrics", json={"date": DAY.isoformat(), "steps": 12000})

    result = push(client, "samsung_health", steps=steps((at(9), at(10), 5000)))

    assert (result[0]["steps"], result[0]["steps_method"]) == (12000, "manual")


def test_sleep_is_attributed_to_wake_up_day_and_overlaps_count_once(client: TestClient) -> None:
    yesterday = DAY - dt.timedelta(days=1)
    sessions = [
        {"start": at(23, 30, day=yesterday), "end": at(6, 30)},  # 7 h night
        {"start": at(5, 0), "end": at(7, 0)},  # duplicate overlapping 30 min beyond the night
        {"start": at(14, 0), "end": at(14, 30)},  # nap
    ]

    result = push(client, "samsung_health", sleep_sessions=sessions)

    assert result[0]["sleep_hours"] == 8.0


def test_samsung_sleep_beats_apple_sleep(client: TestClient) -> None:
    push(client, "apple_health", sleep_sessions=[{"start": at(1), "end": at(5)}])

    result = push(client, "samsung_health", sleep_sessions=[{"start": at(0), "end": at(6)}])

    assert result[0]["sleep_hours"] == 6.0


def test_merged_steps_show_up_in_daily_metrics(client: TestClient) -> None:
    push(client, "apple_health", steps=steps((at(9), at(10), 6000)))

    series = client.get("/api/metrics", params={"start_date": DAY.isoformat(), "end_date": DAY.isoformat()}).json()

    assert series[0]["steps"] == 6000


def test_wrong_token_is_rejected(client: TestClient) -> None:
    body = {"source": "apple_health", "days": [DAY.isoformat()]}

    assert client.post("/api/webhooks/health", json=body).status_code == 401
    assert client.post("/api/webhooks/health", json=body, headers={"X-Webhook-Token": "nope"}).status_code == 401


def test_json_is_accepted_whatever_the_content_type(client: TestClient) -> None:
    body = {"source": "apple_health", "days": [DAY.isoformat()], "steps": steps((at(8), at(8, 10), 500))}
    response = client.post(
        "/api/webhooks/health",
        content=json.dumps(body),
        headers={"X-Webhook-Token": TOKEN, "Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["steps"] == 500


def test_invalid_payload_is_a_422_naming_the_problem(client: TestClient) -> None:
    body = {"source": "apple_health", "days": [DAY.isoformat()], "steps": steps((at(9), at(8), 500))}

    response = client.post("/api/webhooks/health", json=body, headers={"X-Webhook-Token": TOKEN})

    assert response.status_code == 422
    assert "end must not be before start" in response.text


def test_webhooks_are_disabled_without_a_configured_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_token", None)
    body = {"source": "apple_health", "days": [DAY.isoformat()]}

    response = client.post("/api/webhooks/health", json=body, headers={"X-Webhook-Token": TOKEN})

    assert response.status_code == 503


def test_long_samples_are_untimed_and_only_add_to_the_daily_total(client: TestClient) -> None:
    push(client, "apple_health", steps=steps((at(8), at(8, 15), 1000), (at(10), at(14), 2000)))
    result = push(client, "samsung_health", steps=steps((at(8), at(8, 15), 1200)))

    assert (result[0]["steps"], result[0]["steps_method"]) == (3000, "max_daily")
    breakdown = day_steps(client)
    assert breakdown["source_totals"] == {"apple_health": 3000, "samsung_health": 1200}
    assert len(breakdown["buckets"]) == 1
