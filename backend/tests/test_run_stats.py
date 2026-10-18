import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.running import Activity
from app.services.run_analysis import store_streams
from app.services.run_stats import vdot
from tests.test_running import RUN


@pytest.mark.parametrize(
    ("distance_m", "seconds", "expected"),
    [
        (10_000, 50 * 60 + 3, 40.0),  # Daniels' table: 10K 50:03 = VDOT 40
        (5_000, 19 * 60 + 57, 50.0),  # 5K 19:57 = VDOT 50
        (42_195, 3 * 3600 + 49 * 60 + 45, 40.0),  # marathon 3:49:45 = VDOT 40
    ],
)
def test_vdot_matches_daniels_tables(distance_m: float, seconds: int, expected: float) -> None:
    assert vdot(distance_m, seconds) == pytest.approx(expected, abs=0.3)


def test_vdot_needs_a_real_effort() -> None:
    assert vdot(2_000, 9 * 60) is None  # too short for the curve
    assert vdot(20_000, 5 * 3600) is None  # a hike, not a race effort


def test_stats_list_runs_oldest_first_with_metrics(client: TestClient, session: Session) -> None:
    later = client.post("/api/running/activities", json={**RUN, "external_id": "strava:2"}).json()
    earlier = client.post(
        "/api/running/activities",
        json={**RUN, "external_id": "strava:3", "start_time": "2026-10-04T23:30:00+02:00", "notes": "Heat run"},
    ).json()
    client.post("/api/running/activities", json={**RUN, "external_id": "strava:4", "activity_type": "Ride"})
    seconds = 2400
    store_streams(
        session,
        session.get(Activity, later["id"]),
        {
            "time": {"data": list(range(seconds))},
            "velocity_smooth": {"data": [3.0] * seconds},
            "heartrate": {"data": [146] * seconds},
            "moving": {"data": [True] * seconds},
            "grade_smooth": {"data": [0.0] * seconds},
        },
        172,
    )
    session.commit()

    stats = client.get("/api/running/stats").json()

    assert [r["id"] for r in stats["runs"]] == [earlier["id"], later["id"]]
    first, second = stats["runs"]
    assert (first["date"], first["heat"], first["ef_gap"]) == ("2026-10-04", True, None)
    assert second["distance_km"] == 10 and second["pace_s_per_km"] == 312
    assert second["ef_gap"] is not None and second["zone_seconds"]["z2"] > 0
    assert second["vdot"] == pytest.approx(vdot(10_000, 3120))
