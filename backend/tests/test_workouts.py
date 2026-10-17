import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.gym import Workout, WorkoutSet
from app.services.workouts import auto_finish_stale

T0 = dt.datetime(2026, 10, 1, 16, 0, tzinfo=dt.UTC)


def put_workout(client: TestClient, workout_id: uuid.UUID, **fields) -> dict:
    body = {"name": "Chest tri", "started_at": T0.isoformat(), **fields}
    for key, value in body.items():
        if isinstance(value, dt.datetime):
            body[key] = value.isoformat()
    response = client.put(f"/api/workouts/{workout_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def put_set(client: TestClient, workout_id: uuid.UUID, set_id: uuid.UUID, exercise_id: int, **fields) -> dict:
    body = {"exercise_id": exercise_id, "exercise_order": 1, "set_order": 1, "weight_kg": 80, "reps": 8, **fields}
    for key, value in body.items():
        if isinstance(value, dt.datetime):
            body[key] = value.isoformat()
    response = client.put(f"/api/workouts/{workout_id}/sets/{set_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_set_upsert_is_idempotent_and_keeps_first_completion_time(
    client: TestClient, session: Session, exercises: dict[str, int]
) -> None:
    workout_id, set_id = uuid.uuid4(), uuid.uuid4()
    put_workout(client, workout_id)

    first = put_set(client, workout_id, set_id, exercises["Bench Press (Barbell)"])
    second = put_set(client, workout_id, set_id, exercises["Bench Press (Barbell)"], reps=9)

    assert second["reps"] == 9
    assert second["completed_at"] == first["completed_at"]
    assert len(session.exec(select(WorkoutSet).where(WorkoutSet.workout_id == workout_id)).all()) == 1


def test_creating_a_workout_requires_name_and_start(client: TestClient) -> None:
    response = client.put(f"/api/workouts/{uuid.uuid4()}", json={"notes": "x"})

    assert response.status_code == 422


def test_partial_update_does_not_reopen_a_finished_workout(client: TestClient) -> None:
    workout_id = uuid.uuid4()
    finished = put_workout(client, workout_id, ended_at=T0 + dt.timedelta(hours=1))
    assert finished["ended_by"] == "user"

    renamed = client.put(f"/api/workouts/{workout_id}", json={"name": "Push"}).json()

    assert renamed["name"] == "Push"
    assert renamed["ended_at"] == finished["ended_at"]
    assert renamed["ended_by"] == "user"


def test_set_for_unknown_workout_is_404(client: TestClient, exercises: dict[str, int]) -> None:
    response = client.put(
        f"/api/workouts/{uuid.uuid4()}/sets/{uuid.uuid4()}",
        json={"exercise_id": exercises["Pull Up"], "exercise_order": 1, "set_order": 1},
    )

    assert response.status_code == 404


def test_last_performance_uses_latest_finished_workout_only(client: TestClient, exercises: dict[str, int]) -> None:
    bench = exercises["Bench Press (Barbell)"]
    old, recent, active = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    put_workout(client, old, ended_at=T0 + dt.timedelta(hours=1))
    put_set(client, old, uuid.uuid4(), bench, weight_kg=70)
    put_workout(client, recent, started_at=T0 + dt.timedelta(days=3), ended_at=T0 + dt.timedelta(days=3, hours=1))
    put_set(client, recent, uuid.uuid4(), bench, set_order=2, weight_kg=85, reps=6)
    put_set(client, recent, uuid.uuid4(), bench, set_order=1, weight_kg=80, reps=8)
    put_workout(client, active, started_at=T0 + dt.timedelta(days=5))
    put_set(client, active, uuid.uuid4(), bench, weight_kg=90)

    result = client.get(f"/api/exercises/{bench}/last-performance").json()

    assert result["workout_id"] == str(recent)
    assert [(s["set_order"], s["weight_kg"], s["reps"]) for s in result["sets"]] == [(1, 80, 8), (2, 85, 6)]


def test_last_performance_without_history_is_empty(client: TestClient, exercises: dict[str, int]) -> None:
    result = client.get(f"/api/exercises/{exercises['Plank']}/last-performance").json()

    assert result["sets"] == []
    assert result["workout_id"] is None


def test_templates_use_the_latest_workout_of_each_name_in_exercise_order(
    client: TestClient, exercises: dict[str, int]
) -> None:
    older, newer = uuid.uuid4(), uuid.uuid4()
    put_workout(client, older)
    put_set(client, older, uuid.uuid4(), exercises["Chest Dip"])
    put_workout(client, newer, started_at=T0 + dt.timedelta(days=7))
    put_set(client, newer, uuid.uuid4(), exercises["Chest Fly"], exercise_order=2)
    put_set(client, newer, uuid.uuid4(), exercises["Bench Press (Barbell)"], exercise_order=1)
    put_set(client, newer, uuid.uuid4(), exercises["Bench Press (Barbell)"], exercise_order=1, set_order=2)

    templates = client.get("/api/workouts/templates").json()

    assert len(templates) == 1
    assert templates[0]["last_workout_id"] == str(newer)
    assert [(e["name"], e["set_count"]) for e in templates[0]["exercises"]] == [
        ("Bench Press (Barbell)", 2),
        ("Chest Fly", 1),
    ]


def test_auto_finish_closes_only_idle_workouts(session: Session, client: TestClient, exercises: dict[str, int]) -> None:
    idle, busy, empty = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    last_set_at = T0 + dt.timedelta(minutes=50)
    put_workout(client, idle)
    put_set(client, idle, uuid.uuid4(), exercises["Pull Up"], completed_at=last_set_at)
    put_workout(client, busy)
    put_set(client, busy, uuid.uuid4(), exercises["Pull Up"], completed_at=T0 + dt.timedelta(hours=2, minutes=30))
    put_workout(client, empty)
    now = T0 + dt.timedelta(hours=3)

    closed = auto_finish_stale(session, now=now)

    assert closed == 2
    assert session.get(Workout, idle).ended_at == last_set_at + dt.timedelta(minutes=2)
    assert session.get(Workout, idle).ended_by == "auto_idle"
    assert session.get(Workout, empty).ended_at == T0
    assert session.get(Workout, busy).ended_at is None


def test_workout_summary_volume_excludes_warmups(client: TestClient, exercises: dict[str, int]) -> None:
    workout_id = uuid.uuid4()
    put_workout(client, workout_id, ended_at=T0 + dt.timedelta(hours=1))
    squat = exercises["Squat (Barbell)"]
    put_set(client, workout_id, uuid.uuid4(), squat, set_type="warmup", weight_kg=60, reps=5)
    put_set(client, workout_id, uuid.uuid4(), squat, set_order=2, weight_kg=100, reps=5)
    put_set(client, workout_id, uuid.uuid4(), squat, set_order=3, weight_kg=100, reps=4)

    summary = client.get("/api/workouts").json()[0]

    assert summary["set_count"] == 2
    assert summary["total_volume_kg"] == 900
    assert summary["duration_min"] == 60


def test_deleting_a_set_is_idempotent(client: TestClient, exercises: dict[str, int]) -> None:
    workout_id, set_id = uuid.uuid4(), uuid.uuid4()
    put_workout(client, workout_id)
    put_set(client, workout_id, set_id, exercises["Pull Up"])

    assert client.delete(f"/api/workouts/sets/{set_id}").status_code == 204
    assert client.delete(f"/api/workouts/sets/{set_id}").status_code == 204


def test_duplicate_exercise_name_conflicts(client: TestClient, exercises: dict[str, int]) -> None:
    response = client.post("/api/exercises", json={"name": "Pull Up", "muscle_group": "back"})

    assert response.status_code == 409


def test_exercise_muscle_group_can_be_corrected(client: TestClient, exercises: dict[str, int]) -> None:
    response = client.patch(f"/api/exercises/{exercises['Back Extension']}", json={"muscle_group": "legs"})

    assert response.status_code == 200
    assert response.json()["muscle_group"] == "legs"
