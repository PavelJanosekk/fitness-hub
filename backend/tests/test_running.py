import datetime as dt

from fastapi.testclient import TestClient

RUN = {
    "external_id": "strava:1",
    "source": "strava",
    "start_time": "2026-10-12T07:00:00+02:00",
    "activity_type": "Run",
    "distance_meters": 10000,
    "duration_seconds": 3120,
    "avg_hr": 148,
}


def test_activity_pace_is_computed(client: TestClient) -> None:
    created = client.post("/api/running/activities", json=RUN).json()

    assert created["pace_sec_per_km"] == 312
    assert created["pace"] == "5:12"


def test_duplicate_external_id_conflicts(client: TestClient) -> None:
    client.post("/api/running/activities", json=RUN)

    assert client.post("/api/running/activities", json=RUN).status_code == 409


def test_plan_items_include_linked_activity(client: TestClient) -> None:
    activity = client.post("/api/running/activities", json=RUN).json()
    day = dt.date(2026, 10, 12)
    created = client.post(
        "/api/running/plan",
        json={"planned_date": day.isoformat(), "title": "Long Run Z2", "completed_activity_id": activity["id"]},
    ).json()
    client.post("/api/running/plan", json={"id": created["id"], "planned_date": day.isoformat(), "title": "LR 10k"})

    plan = client.get("/api/running/plan", params={"start_date": day.isoformat(), "end_date": day.isoformat()}).json()

    assert len(plan) == 1
    assert plan[0]["title"] == "LR 10k"
    # Updating without completed_activity_id clears the link (full replace)
    assert plan[0]["completed_activity"] is None


def test_plan_link_to_unknown_activity_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/running/plan", json={"planned_date": "2026-10-12", "title": "x", "completed_activity_id": 999999}
    )

    assert response.status_code == 422


def test_activity_list_includes_stream_metrics_and_heat(client: TestClient, session) -> None:
    from app.models.running import Activity
    from app.services.run_analysis import store_streams

    created = client.post(
        "/api/running/activities", json={**RUN, "external_id": "strava:9", "notes": "Easy heat"}
    ).json()
    seconds = 2400
    store_streams(
        session,
        session.get(Activity, created["id"]),
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

    listed = client.get("/api/running/activities").json()[0]

    assert listed["heat"] is True
    assert listed["gap_sec_per_km"] == 333.3
    assert listed["pct_above_easy"] == 0 and listed["z4_minutes"] == 0
