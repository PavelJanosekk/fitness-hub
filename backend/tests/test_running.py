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


def _detail_streams(seconds: int) -> dict:
    """A 3 m/s run: 1 km climb by 10 m every km, then flat; cadence per leg like Strava."""
    distance = [3.0 * t for t in range(seconds)]
    return {
        "time": {"data": list(range(seconds))},
        "distance": {"data": distance},
        "velocity_smooth": {"data": [3.0] * seconds},
        "heartrate": {"data": [140 + t // 600 for t in range(seconds)]},
        "moving": {"data": [True] * seconds},
        "grade_smooth": {"data": [1.0] * seconds},
        "altitude": {"data": [200 + d / 100 for d in distance]},
        "cadence": {"data": [85] * seconds},
        "latlng": {"data": [[50.0 + t / 100_000, 14.4] for t in range(seconds)]},
    }


def test_run_detail_has_series_splits_route_and_zones(client: TestClient, session) -> None:
    from app.models.running import Activity
    from app.services.run_analysis import store_streams

    created = client.post("/api/running/activities", json={**RUN, "external_id": "manual:detail"}).json()
    store_streams(session, session.get(Activity, created["id"]), _detail_streams(2400), 172)
    session.commit()

    detail = client.get(f"/api/running/activities/{created['id']}").json()

    assert detail["streams"] == "full"
    series = detail["series"]
    assert set(series) == {"time_s", "distance_km", "pace", "gap", "hr", "altitude", "cadence", "lat", "lng"}
    assert len(series["time_s"]) <= 400 and len({len(v) for v in series.values()}) == 1
    assert series["pace"][0] == 333 and series["gap"][0] < 333  # uphill: GAP faster than pace
    assert series["cadence"][0] == 170
    # 7.2 km: seven full splits and a 0.2 km remainder
    assert [s["km"] for s in detail["splits"]] == [1.0] * 7 + [0.2]
    assert detail["splits"][0]["pace"] == 333 and detail["splits"][0]["elevation_m"] == 10
    assert detail["elevation_gain_m"] == 70  # computed from altitude in 2 m steps: no Strava value
    assert detail["zone_bounds"]["z2"] == "138-153" and sum(detail["zone_seconds"].values()) == 2400
    assert len(detail["route"]) <= 801 and detail["route"][0] == [50.0, 14.4]


def test_run_detail_unknown_activity_is_404(client: TestClient) -> None:
    assert client.get("/api/running/activities/999999").status_code == 404
