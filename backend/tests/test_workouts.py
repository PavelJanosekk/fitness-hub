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


def put_template(client: TestClient, template_id: uuid.UUID, name: str, exercise_ids: list[int]) -> dict:
    body = {
        "name": name,
        "exercises": [
            {
                "exercise_id": i,
                "sets": [{"weight_kg": 60, "reps": 10}, {"weight_kg": 62.5, "reps": 8, "set_type": "drop"}],
            }
            for i in exercise_ids
        ],
    }
    response = client.put(f"/api/workouts/templates/{template_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_templates_are_managed_by_hand(client: TestClient, exercises: dict[str, int]) -> None:
    chest, back = uuid.uuid4(), uuid.uuid4()
    bench, fly = exercises["Bench Press (Barbell)"], exercises["Chest Fly"]

    created = put_template(client, chest, " Chest tri ", [bench, fly])
    put_template(client, back, "Back biceps", [exercises["Pull Up"]])
    renamed = put_template(client, chest, "Chest 3", [fly])  # same id again: replaces, keeps its place

    assert created["name"] == "Chest tri" and created["position"] == 0
    assert [(e["name"], len(e["sets"])) for e in created["exercises"]] == [
        ("Bench Press (Barbell)", 2),
        ("Chest Fly", 2),
    ]
    assert created["exercises"][0]["sets"][1] == {"set_type": "drop", "weight_kg": 62.5, "reps": 8}
    assert (renamed["name"], renamed["position"], len(renamed["exercises"])) == ("Chest 3", 0, 1)
    assert [t["name"] for t in client.get("/api/workouts/templates").json()] == ["Chest 3", "Back biceps"]

    assert client.delete(f"/api/workouts/templates/{chest}").status_code == 204
    assert client.delete(f"/api/workouts/templates/{chest}").status_code == 204  # idempotent
    assert [t["name"] for t in client.get("/api/workouts/templates").json()] == ["Back biceps"]


def test_template_rejects_unknown_exercises_and_empty_sets(client: TestClient) -> None:
    unknown = client.put(
        f"/api/workouts/templates/{uuid.uuid4()}",
        json={"name": "X", "exercises": [{"exercise_id": 999999, "sets": [{"reps": 5}]}]},
    )
    no_sets = client.put(
        f"/api/workouts/templates/{uuid.uuid4()}", json={"name": "X", "exercises": [{"exercise_id": 1, "sets": []}]}
    )

    assert unknown.status_code == 422
    assert no_sets.status_code == 422


def lift(
    client: TestClient, day: int, exercise_id: int, sets: list[tuple[float | None, int]], **set_fields
) -> uuid.UUID:
    workout_id = uuid.uuid4()
    put_workout(
        client, workout_id, started_at=T0 + dt.timedelta(days=day), ended_at=T0 + dt.timedelta(days=day, hours=1)
    )
    for order, (weight, reps) in enumerate(sets, start=1):
        put_set(
            client, workout_id, uuid.uuid4(), exercise_id, set_order=order, weight_kg=weight, reps=reps, **set_fields
        )
    return workout_id


def test_personal_records_need_an_earlier_workout_and_report_one_per_exercise(
    client: TestClient, exercises: dict[str, int]
) -> None:
    bench, pull_up = exercises["Bench Press (Barbell)"], exercises["Pull Up"]
    first = lift(client, 0, bench, [(80, 8)])
    heavier = lift(client, 7, bench, [(80, 8), (85, 5)])
    more_reps = lift(client, 14, bench, [(80, 10)])  # no heavier set, but a better estimated 1RM
    worse = lift(client, 21, bench, [(70, 8)])
    warmup_only_heavier = lift(client, 28, bench, [(120, 5)], set_type="warmup")
    bodyweight = [lift(client, 0, pull_up, [(None, 8)]), lift(client, 7, pull_up, [(None, 10)])]

    by_id = {w["id"]: w["prs"] for w in client.get("/api/workouts").json()}

    assert by_id[str(first)] == []  # the first time is never a record
    assert [(p["kind"], p["value"], p["reps"]) for p in by_id[str(heavier)]] == [("weight", 85, 5)]
    assert [(p["kind"], p["name"]) for p in by_id[str(more_reps)]] == [("e1rm", "Bench Press (Barbell)")]
    assert by_id[str(worse)] == [] and by_id[str(warmup_only_heavier)] == []
    assert by_id[str(bodyweight[0])] == []
    assert [(p["kind"], p["value"]) for p in by_id[str(bodyweight[1])]] == [("reps", 10)]


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


def test_editing_a_finished_workout_replaces_its_sets(client: TestClient, exercises: dict[str, int]) -> None:
    bench, pull_up = exercises["Bench Press (Barbell)"], exercises["Pull Up"]
    workout_id, kept, dropped, added = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    put_workout(client, workout_id, ended_at=T0 + dt.timedelta(hours=1))
    put_set(client, workout_id, kept, bench, completed_at=T0)
    put_set(client, workout_id, dropped, bench, set_order=2, completed_at=T0)
    edited_at = T0 - dt.timedelta(days=2)
    body = {
        "name": "Push",
        "started_at": edited_at.isoformat(),
        "ended_at": (edited_at + dt.timedelta(minutes=50)).isoformat(),
        "replace_sets": True,
        "sets": [
            {
                "id": str(kept),
                "exercise_id": bench,
                "exercise_order": 1,
                "set_order": 1,
                "weight_kg": 85,
                "reps": 6,
                "completed_at": edited_at.isoformat(),
            },
            {
                "id": str(added),
                "exercise_id": pull_up,
                "exercise_order": 2,
                "set_order": 1,
                "weight_kg": 0,
                "reps": 10,
                "completed_at": edited_at.isoformat(),
            },
        ],
    }

    response = client.put(f"/api/workouts/{workout_id}", json=body)

    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["name"] == "Push" and edited["ended_by"] == "user"
    assert [(s["id"], s["weight_kg"], s["reps"]) for s in edited["sets"]] == [(str(kept), 85, 6), (str(added), 0, 10)]
    assert all(dt.datetime.fromisoformat(s["completed_at"]) == edited_at for s in edited["sets"])


def test_past_workout_can_be_logged_in_one_request(client: TestClient, exercises: dict[str, int]) -> None:
    workout_id = uuid.uuid4()
    started = T0 - dt.timedelta(days=30)
    body = {
        "name": "Legs",
        "started_at": started.isoformat(),
        "ended_at": (started + dt.timedelta(hours=1)).isoformat(),
        "replace_sets": True,
        "sets": [
            {
                "id": str(uuid.uuid4()),
                "exercise_id": exercises["Pull Up"],
                "exercise_order": 1,
                "set_order": 1,
                "weight_kg": 0,
                "reps": 8,
                "completed_at": started.isoformat(),
            },
        ],
    }

    assert client.put(f"/api/workouts/{workout_id}", json=body).status_code == 200
    summary = next(w for w in client.get("/api/workouts").json() if w["id"] == str(workout_id))
    assert summary["set_count"] == 1 and summary["duration_min"] == 60


def test_replacing_sets_cannot_steal_another_workouts_set(client: TestClient, exercises: dict[str, int]) -> None:
    other, mine, set_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    put_workout(client, other)
    put_set(client, other, set_id, exercises["Pull Up"])
    put_workout(client, mine)
    body = {
        "replace_sets": True,
        "sets": [{"id": str(set_id), "exercise_id": exercises["Pull Up"], "exercise_order": 1, "set_order": 1}],
    }

    assert client.put(f"/api/workouts/{mine}", json=body).status_code == 409
    assert len(client.get(f"/api/workouts/{other}").json()["sets"]) == 1


def test_duplicate_exercise_name_conflicts(client: TestClient, exercises: dict[str, int]) -> None:
    response = client.post("/api/exercises", json={"name": "Pull Up", "muscle_group": "back"})

    assert response.status_code == 409


def test_exercise_muscle_group_can_be_corrected(client: TestClient, exercises: dict[str, int]) -> None:
    response = client.patch(f"/api/exercises/{exercises['Back Extension']}", json={"muscle_group": "legs"})

    assert response.status_code == 200
    assert response.json()["muscle_group"] == "legs"


def test_exercise_names_are_stripped_and_unique_ignoring_case(client: TestClient, exercises: dict[str, int]) -> None:
    body = {"name": "  Cable Fly  ", "muscle_group": "chest", "equipment": "cable"}
    created = client.post("/api/exercises", json=body)

    assert created.status_code == 201
    assert created.json()["name"] == "Cable Fly"
    assert client.post("/api/exercises", json={"name": "pull up", "muscle_group": "back"}).status_code == 409
    assert client.post("/api/exercises", json={"name": "   ", "muscle_group": "back"}).status_code == 422


def test_exercise_can_be_renamed_but_not_onto_another(client: TestClient, exercises: dict[str, int]) -> None:
    exercise_id = exercises["Back Extension"]

    renamed = client.patch(f"/api/exercises/{exercise_id}", json={"name": " Hyperextension ", "equipment": "machine"})
    # Changing only the case of its own name is not a conflict
    recased = client.patch(f"/api/exercises/{exercise_id}", json={"name": "hyperextension"})
    conflict = client.patch(f"/api/exercises/{exercise_id}", json={"name": "PULL UP"})

    assert renamed.status_code == 200
    assert renamed.json() == {
        "id": exercise_id,
        "name": "Hyperextension",
        "muscle_group": "back",
        "equipment": "machine",
    }
    assert recased.json()["name"] == "hyperextension"
    assert conflict.status_code == 409
