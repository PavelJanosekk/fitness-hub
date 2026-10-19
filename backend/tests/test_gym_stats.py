import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.seed import EXERCISES
from app.services.gym_stats import antagonist_muscle, gym_stats
from tests.test_workouts import T0, lift, put_set, put_workout

NOW = T0 + dt.timedelta(days=30)  # Saturday 31. 10. 2026


@pytest.mark.parametrize(
    ("name", "group", "muscle"),
    [
        ("Bench Press (Barbell)", "chest", "chest"),
        ("Chest Dip", "chest", "chest"),
        ("Seated Row (Machine)", "back", "back"),
        ("Kelso Shrug", "back", None),
        ("Overhead Press (Cable)", "shoulders", "front_delts"),
        ("Reverse Fly (Cable)", "shoulders", "rear_delts"),
        ("Lateral Raise (Dumbbell)", "shoulders", None),
        ("Hammer Curl (Dumbbell)", "biceps", "biceps"),
        ("Triceps Pushdown (Cable - Straight Bar)", "triceps", "triceps"),
        ("Lying Leg Curl (Machine)", "legs", "hamstrings"),
        ("Romanian Deadlift (Barbell)", "legs", "hamstrings"),
        ("Leg Extension (Machine)", "legs", "quads"),
        ("Bulharský výpad", "legs", "quads"),
        ("Seated Calf Raise (Plate Loaded)", "legs", None),
        ("Hanging Leg Raise", "core", None),
    ],
)
def test_antagonist_muscle_from_name_and_group(name: str, group: str, muscle: str | None) -> None:
    assert antagonist_muscle(name, group) == muscle


def test_seeded_curls_and_presses_are_classified() -> None:
    groups = ("chest", "back", "biceps", "triceps")
    unclassified = {n for n, g, _ in EXERCISES if g in groups and antagonist_muscle(n, g) is None}

    assert unclassified <= {"Back Extension", "Kelso Shrug", "Shrug (Dumbbell)", "Shrug (Barbell)"}


def test_stats_bucket_days_and_weeks_with_working_sets_only(
    session: Session, client: TestClient, exercises: dict[str, int]
) -> None:
    bench, curl, raise_ = (
        exercises["Bench Press (Barbell)"],
        exercises["Bicep Curl (Dumbbell)"],
        exercises["Lateral Raise (Dumbbell)"],
    )
    first = lift(client, 0, bench, [(80, 8), (80, 6)])  # Thursday 1. 10.
    put_set(client, first, uuid.uuid4(), bench, set_order=3, weight_kg=40, reps=10, set_type="warmup")
    put_set(client, first, uuid.uuid4(), curl, exercise_order=2, weight_kg=15, reps=10)
    lift(client, 14, raise_, [(10, 12)])
    late = uuid.uuid4()  # 23:30 in Prague on Saturday 17. 10. is still that local day
    put_workout(client, late, started_at=dt.datetime(2026, 10, 17, 21, 30, tzinfo=dt.UTC))
    put_set(client, late, uuid.uuid4(), bench, weight_kg=100, reps=1)

    stats = gym_stats(session, weeks=6, now=NOW)

    assert [(d.date.isoformat(), d.workouts, d.sets, d.volume_kg) for d in stats.days] == [
        ("2026-10-01", 1, 3, 1270.0),
        ("2026-10-15", 1, 1, 120.0),
        ("2026-10-17", 1, 1, 100.0),
    ]
    assert [w.week_start.isoformat() for w in stats.weeks] == [
        "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26",
    ]  # fmt: skip
    week = stats.weeks[1]
    assert (week.workouts, week.sets) == (1, {"chest": 2, "biceps": 1})
    assert week.volume_kg == {"chest": 1120.0, "biceps": 150.0}
    assert week.muscles == {"chest": 2, "biceps": 1}
    assert (stats.weeks[3].sets, stats.weeks[3].muscles, stats.weeks[3].unclassified_sets) == (
        {"shoulders": 1, "chest": 1},
        {"chest": 1},
        1,
    )
    assert (stats.exercises[0].name, stats.exercises[0].sessions) == ("Bench Press (Barbell)", 2)


def test_progression_reports_top_set_e1rm_and_records(client: TestClient, exercises: dict[str, int]) -> None:
    bench, pull_up = exercises["Bench Press (Barbell)"], exercises["Pull Up"]
    lift(client, 0, bench, [(80, 8), (70, 12)])
    lift(client, 7, bench, [(85, 3), (75, 10)])  # heavier, but the 10-rep set still gives the better 1RM
    lift(client, 14, bench, [(80, 5), (40, 20)])  # 20 reps: too long for the estimate, no reps record when loaded
    lift(client, 0, pull_up, [(None, 8)])
    lift(client, 7, pull_up, [(None, 10)])

    result = client.get(f"/api/exercises/{bench}/progression").json()
    pull = client.get(f"/api/exercises/{pull_up}/progression").json()

    assert result["weighted"] is True
    rows = [
        (s["date"], s["max_weight"], s["max_weight_reps"], s["e1rm"], s["e1rm_set"], s["pr"])
        for s in result["sessions"]
    ]
    assert rows == [
        ("2026-10-01", 80, 8, 101.3, "80 × 8", []),
        ("2026-10-08", 85, 3, 100.0, "75 × 10", ["weight"]),
        ("2026-10-15", 80, 5, 93.3, "80 × 5", []),
    ]
    assert result["sessions"][0]["volume_kg"] == 1480 and result["sessions"][2]["max_reps"] == 20
    assert pull["weighted"] is False
    assert [(s["max_reps"], s["pr"]) for s in pull["sessions"]] == [(8, []), (10, ["reps"])]
    assert client.get("/api/exercises/999999/progression").status_code == 404
