import datetime as dt
import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models.gym import Exercise
from app.schemas.gym import ProgressionTarget
from app.services.overload import PastSession, PastSet, Settings, next_target, settings_for
from app.timeutils import now_utc
from tests.test_workouts import put_set, put_workout

DAY = dt.date(2026, 10, 19)
DUMBBELL = Settings(rep_min=6, rep_max=10, weight_step=2.5, sets_max=3)
CABLE = Settings(rep_min=8, rep_max=12, weight_step=5.0, sets_max=3)


def past(days_ago: int, *sets: tuple[Any, ...]) -> PastSession:
    """A session `days_ago` before DAY; a set is (weight, reps) or (weight, reps, set_type)."""
    return PastSession(
        DAY - dt.timedelta(days=days_ago), [PastSet(s[2] if len(s) == 3 else "normal", s[0], s[1]) for s in sets]
    )


def target(*sessions: PastSession, settings: Settings = DUMBBELL) -> ProgressionTarget:
    result = next_target(list(sessions), settings, DAY)
    assert result is not None
    return result


def plan(result: ProgressionTarget) -> list[tuple[float | None, int | None]]:
    return [(s.weight_kg, s.reps) for s in result.sets]


def test_adds_a_set_before_adding_reps() -> None:
    result = target(past(2, (40, 6), (40, 6)))

    assert result.kind == "sets"
    assert plan(result) == [(40, 6), (40, 6), (40, 6)]
    assert [s.changed for s in result.sets] == [False, False, True]


def test_at_the_max_sets_one_rep_goes_to_the_weakest_set() -> None:
    result = target(past(3, (40, 7), (40, 6), (40, 6)))

    assert result.kind == "reps"
    assert plan(result) == [(40, 7), (40, 7), (40, 6)]
    assert [s.changed for s in result.sets] == [False, True, False]


def test_the_top_of_the_range_adds_weight_and_starts_at_the_bottom() -> None:
    result = target(past(3, (40, 10), (40, 11), (40, 10)))

    assert result.kind == "weight"
    assert result.weight_kg == 42.5
    assert plan(result) == [(42.5, 6), (42.5, 6), (42.5, 6)]


def test_below_the_range_goes_one_step_lighter_with_epley_reps() -> None:
    result = target(past(3, (42.5, 5), (42.5, 4)))

    assert result.kind == "lighter"
    assert plan(result) == [(40, 7), (40, 6)]


def test_three_sessions_without_beating_the_best_deload_by_about_ten_percent() -> None:
    result = target(
        past(12, (40, 8), (40, 7), (40, 7)),
        past(9, (40, 7), (40, 7), (40, 7)),
        past(6, (40, 8), (40, 7), (40, 7)),  # equal is not better
        past(3, (40, 7), (40, 7), (40, 6)),
    )

    assert result.kind == "deload"
    assert result.stalled_sessions == 3
    assert plan(result) == [(35, 7), (35, 7), (35, 6)]


def test_a_stall_without_a_reasonable_lighter_weight_keeps_progressing() -> None:
    # 10 kg on a 5 kg stack: one step down would be half the weight, and fewer reps would only deepen the stall
    sessions = [past(d, (10, 10), (10, 9), (10, 10)) for d in (12, 9, 6, 3)]

    result = target(*sessions, settings=CABLE)

    assert result.kind == "reps"
    assert result.stalled_sessions == 3
    assert plan(result) == [(10, 10), (10, 10), (10, 10)]


def test_a_new_weight_or_a_break_starts_the_stall_count_afresh() -> None:
    other_weight = target(past(40, (40, 9), (40, 9)), past(37, (40, 9)), past(34, (42.5, 6)), past(3, (40, 8)))
    after_break = target(past(60, (40, 9), (40, 9)), past(57, (40, 9)), past(54, (40, 9)), past(3, (40, 8)))

    assert other_weight.stalled_sessions == 0
    assert after_break.stalled_sessions == 0


def test_after_a_break_every_working_set_comes_down_by_the_same_steps() -> None:
    result = target(past(30, (60, 10, "warmup"), (110, 2), (90, 6), (90, 5)))

    assert result.kind == "comeback"
    assert result.days_since == 30
    assert result.weight_kg == 80
    assert plan(result) == [(60, 10), (100, 2), (80, 6), (80, 5)]


def test_after_a_break_without_a_load_the_reps_come_down() -> None:
    result = target(past(30, (0, 10), (0, 7)))

    assert result.kind == "comeback"
    assert plan(result) == [(0, 9), (0, 6)]


def test_without_a_load_reps_grow_past_the_range() -> None:
    result = target(past(3, (0, 12), (0, 12), (0, 11)))

    assert result.kind == "reps"
    assert plan(result) == [(0, 12), (0, 12), (0, 12)]
    assert target(past(3, (0, 12), (0, 12), (0, 12))).sets[0].reps == 13


def test_warm_ups_drop_sets_and_other_weights_are_kept_as_they_were() -> None:
    result = target(past(3, (20, 10, "warmup"), (32, 6), (40, 7), (40, 6), (30, 8, "drop")))

    # Working sets 32, 40, 40 = the max of 3: the weakest set at the most frequent weight gets the rep
    assert result.kind == "reps"
    assert plan(result) == [(20, 10), (32, 6), (40, 7), (40, 7), (30, 8)]
    assert result.sets[0].set_type == "warmup"
    assert result.sets[-1].set_type == "drop"


def test_the_added_set_follows_the_last_set_at_the_working_weight() -> None:
    result = target(past(3, (40, 6), (40, 5), (30, 10, "drop")))

    assert plan(result) == [(40, 6), (40, 5), (40, 5), (30, 10)]


def test_no_target_without_a_session_with_reps() -> None:
    assert next_target([], DUMBBELL, DAY) is None
    assert next_target([past(3, (None, None))], DUMBBELL, DAY) is None
    assert next_target([past(3, (20, 10, "warmup"))], DUMBBELL, DAY) is None


def test_settings_default_by_equipment_and_can_be_overridden() -> None:
    assert settings_for(Exercise(name="x", muscle_group="chest", equipment="cable")) == Settings(8, 12, 5.0, 3)
    assert settings_for(Exercise(name="x", muscle_group="chest", equipment="dumbbell")) == Settings(6, 10, 2.5, 3)
    assert settings_for(Exercise(name="x", muscle_group="chest")) == Settings(8, 12, 2.5, 3)
    custom = Exercise(name="x", muscle_group="chest", equipment="dumbbell", rep_min=12, weight_step=2, sets_max=4)
    assert settings_for(custom) == Settings(12, 12, 2, 4)  # a minimum above the default maximum widens the range


def test_last_performance_carries_the_target(client: TestClient, exercises: dict[str, int]) -> None:
    bench = exercises["Bench Press (Dumbbell)"]
    started = now_utc() - dt.timedelta(days=2)
    workout_id = uuid.uuid4()
    put_workout(client, workout_id, started_at=started, ended_at=started + dt.timedelta(hours=1))
    put_set(client, workout_id, uuid.uuid4(), bench, set_order=1, weight_kg=40, reps=6)
    put_set(client, workout_id, uuid.uuid4(), bench, set_order=2, weight_kg=40, reps=6)

    result = client.get(f"/api/exercises/{bench}/last-performance").json()

    assert result["target"]["kind"] == "sets"
    assert [(s["weight_kg"], s["reps"], s["changed"]) for s in result["target"]["sets"]] == [
        (40, 6, False),
        (40, 6, False),
        (40, 6, True),
    ]
    assert (result["target"]["rep_min"], result["target"]["rep_max"], result["target"]["weight_step"]) == (6, 10, 2.5)
    assert client.get(f"/api/exercises/{exercises['Plank']}/last-performance").json()["target"] is None


def test_progression_settings_are_saved_per_exercise(client: TestClient, exercises: dict[str, int]) -> None:
    bench = exercises["Bench Press (Dumbbell)"]

    saved = client.patch(f"/api/exercises/{bench}", json={"rep_min": 8, "rep_max": 12, "weight_step": 2}).json()
    assert (saved["rep_min"], saved["rep_max"], saved["weight_step"], saved["sets_max"]) == (8, 12, 2, None)

    reset = client.patch(f"/api/exercises/{bench}", json={"rep_min": None, "rep_max": None}).json()
    assert (reset["rep_min"], reset["rep_max"], reset["weight_step"]) == (None, None, 2)

    assert client.patch(f"/api/exercises/{bench}", json={"rep_min": 10, "rep_max": 8}).status_code == 422
    assert client.patch(f"/api/exercises/{bench}", json={"weight_step": 0}).status_code == 422
    created = client.post("/api/exercises", json={"name": "Landmine Press", "muscle_group": "shoulders", "sets_max": 4})
    assert created.json()["sets_max"] == 4
