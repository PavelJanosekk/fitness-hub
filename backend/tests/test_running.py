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
