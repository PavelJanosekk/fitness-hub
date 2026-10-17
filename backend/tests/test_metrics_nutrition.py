import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.body import DailySourceMetric
from app.models.nutrition import MealLog
from app.timeutils import today

D = dt.date(2026, 10, 10)


def quick_add(client: TestClient, day: dt.date, kcal: float, item_id: uuid.UUID | None = None, **fields) -> dict:
    body = {"id": str(item_id or uuid.uuid4()), "date": day.isoformat(), "kcal": kcal, **fields}
    response = client.post("/api/nutrition/quick-add", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_rolling_weight_average_skips_missing_days(client: TestClient) -> None:
    for day, weight in [(D - dt.timedelta(days=6), 80.0), (D - dt.timedelta(days=2), 79.0), (D, 78.0)]:
        client.post("/api/metrics", json={"date": day.isoformat(), "weight_kg": weight})

    series = client.get("/api/metrics", params={"start_date": D.isoformat(), "end_date": D.isoformat()}).json()

    assert series[0]["weight_kg"] == 78.0
    assert series[0]["weight_7d_avg"] == 79.0


def test_intake_comes_from_meal_logs_and_unlogged_days_are_not_zero(client: TestClient) -> None:
    quick_add(client, D - dt.timedelta(days=1), 2000, protein_g=150)
    quick_add(client, D, 1500)
    quick_add(client, D, 500, protein_g=40)

    series = client.get(
        "/api/metrics", params={"start_date": (D - dt.timedelta(days=2)).isoformat(), "end_date": D.isoformat()}
    ).json()

    unlogged, yesterday, day = series
    assert unlogged["calories_in"] is None
    assert yesterday["calories_in"] == 2000
    assert day["calories_in"] == 2000
    assert day["protein_g"] == 40
    assert day["calories_in_7d_avg"] == 2000


def test_metric_upsert_only_overwrites_given_fields_and_records_manual_steps(
    client: TestClient, session: Session
) -> None:
    client.post("/api/metrics", json={"date": D.isoformat(), "weight_kg": 80.5, "notes": "ráno"})
    stored = client.post("/api/metrics", json={"date": D.isoformat(), "steps": 9000}).json()

    assert stored["weight_kg"] == 80.5
    assert stored["notes"] == "ráno"
    assert stored["steps"] == 9000
    manual = session.exec(select(DailySourceMetric).where(DailySourceMetric.date == D)).one()
    assert (manual.source, manual.metric, manual.value) == ("manual", "steps_total", 9000)


def test_quick_add_is_idempotent_per_client_id(client: TestClient, session: Session) -> None:
    item_id = uuid.uuid4()
    quick_add(client, D, 400, item_id=item_id)
    quick_add(client, D, 450, item_id=item_id, meal_type="lunch")

    day = client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()

    assert len(day["meals"]) == 1
    assert day["meals"][0]["meal_type"] == "lunch"
    assert day["totals"]["kcal"] == 450
    assert day["totals"]["protein_g"] is None


def test_quick_add_defaults_to_today(client: TestClient) -> None:
    created = client.post("/api/nutrition/quick-add", json={"id": str(uuid.uuid4()), "kcal": 300}).json()

    assert created["logged_date"] == today().isoformat()


def test_deleting_the_last_item_removes_the_meal(client: TestClient, session: Session) -> None:
    item_id = uuid.uuid4()
    quick_add(client, D, 300, item_id=item_id)

    assert client.delete(f"/api/nutrition/items/{item_id}").status_code == 204
    assert session.get(MealLog, item_id) is None
    assert client.delete(f"/api/nutrition/items/{item_id}").status_code == 204
