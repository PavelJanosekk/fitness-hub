"""Progressive overload targets (E35): behaviour of the rules, including the acceptance scenarios of
docs/overload-module-spec.md §12 (numbered "scenario N" below)."""

import datetime as dt
import uuid

from fastapi.testclient import TestClient

from app.models.gym import Exercise
from app.schemas.gym import ProgressionTarget
from app.services.overload import PastSession, PastSet, Settings, next_target, settings_for
from app.timeutils import now_utc
from tests.test_workouts import put_set, put_workout

DAY = dt.date(2026, 10, 20)
DUMBBELL = Settings(rep_min=6, rep_max=10, weight_step=2.5)
CABLE = Settings(rep_min=8, rep_max=12, weight_step=5.0)
TOP_BACKOFF = Settings(rep_min=6, rep_max=10, weight_step=2.5, strategy="top_backoff")


def lifted(weight: float | None, reps: int | None, set_type: str = "normal") -> PastSet:
    """A set logged without a plan (imports, before E35)."""
    return PastSet(set_type, weight, reps)


def planned(weight: float, target: int, reps: int, role: str = "straight", at: float | None = None) -> PastSet:
    """A set planned at `weight` x `target`, lifted for `reps` (at another weight when `at` is given)."""
    return PastSet("normal", weight if at is None else at, reps, weight, target, role)


def session(days_ago: int, *sets: PastSet, unusual: bool = False, fatigue_from: str | None = None) -> PastSession:
    return PastSession(DAY - dt.timedelta(days=days_ago), list(sets), unusual, fatigue_from)


def same(days: tuple[int, ...], *sets: PastSet) -> list[PastSession]:
    """The same session repeated on several days (oldest first)."""
    return [session(d, *sets) for d in days]


def target(*sessions: PastSession, settings: Settings = DUMBBELL) -> ProgressionTarget:
    result = next_target(list(sessions), settings, DAY)
    assert result is not None
    return result


def plan(result: ProgressionTarget) -> list[tuple[float | None, int | None]]:
    return [(s.weight_kg, s.reps) for s in result.sets]


def reasons(result: ProgressionTarget) -> list[str]:
    return [b.reason for b in result.blocks]


def priority(result: ProgressionTarget) -> list[int]:
    return [i for i, s in enumerate(result.sets) if s.priority]


def test_the_first_set_gets_the_rep_when_the_last_targets_were_met() -> None:  # scenario 1
    result = target(
        session(7, lifted(40, 8), lifted(40, 7), lifted(40, 6)),
        session(3, planned(40, 8, 8), planned(40, 7, 7), planned(40, 6, 6)),
    )

    assert reasons(result) == ["plus_rep"]
    assert plan(result) == [(40, 9), (40, 7), (40, 6)]
    assert priority(result) == [0]


def test_with_the_first_set_at_the_top_the_first_weak_later_set_gets_the_rep() -> None:  # scenario 3
    result = target(*same((7, 3), lifted(40, 10), lifted(40, 5), lifted(40, 5)))

    assert reasons(result) == ["plus_rep"]
    assert plan(result) == [(40, 10), (40, 6), (40, 5)]
    assert priority(result) == [1]


def test_the_top_of_the_range_with_holding_later_sets_adds_weight() -> None:  # scenario 2
    for reps in ([10, 8, 6], [10, 7, 5]):
        result = target(*same((7, 3), *(lifted(40, r) for r in reps)))
        assert reasons(result) == ["weight_up"], reps
        assert {s.weight_kg for s in result.sets} == {42.5}

    # Epley only for the first set (40 x 10 -> 7 at 42.5); the others keep this session's drop-off
    estimate = target(*same((7, 3), lifted(40, 10), lifted(40, 8), lifted(40, 6)))
    assert plan(estimate) == [(42.5, 7), (42.5, 6), (42.5, 4)]
    assert reasons(target(*same((7, 3), lifted(40, 10), lifted(40, 5), lifted(40, 4)))) == ["plus_rep"]


def test_more_weight_starts_from_the_users_own_sets_at_it() -> None:
    result = target(
        session(20, lifted(42.5, 7), lifted(42.5, 6), lifted(42.5, 5)),
        session(10, lifted(40, 9), lifted(40, 8), lifted(40, 6)),
        session(3, lifted(40, 10), lifted(40, 8), lifted(40, 6)),
    )

    assert reasons(result) == ["return_up"]
    assert plan(result) == [(42.5, 7), (42.5, 6), (42.5, 5)]


def test_a_jump_that_is_big_for_the_weight_warns() -> None:
    result = target(*same((7, 3), lifted(10, 12), lifted(10, 11)), settings=CABLE)

    assert reasons(result) == ["weight_up"]
    assert result.sets[0].weight_kg == 15
    assert "big_jump" in result.warnings


def test_a_single_drop_keeps_the_plan_and_offers_a_lighter_option_for_today() -> None:  # scenario 4
    result = target(
        session(7, planned(40, 10, 10), planned(40, 7, 7), planned(40, 6, 6)),
        session(3, planned(40, 10, 10), planned(40, 7, 4), planned(40, 6, 4)),
    )

    assert reasons(result) == ["check_drop"]
    assert plan(result) == [(40, 10), (40, 7), (40, 6)]
    assert result.suggestion is not None and result.suggestion.kind == "lighter"
    assert {s.weight_kg for s in result.suggestion.sets} == {37.5}


def test_a_drop_twice_in_a_row_lowers_the_weight_one_step() -> None:  # scenario 5
    result = target(
        session(10, planned(40, 10, 10), planned(40, 7, 7), planned(40, 6, 6)),
        *same((6, 3), planned(40, 10, 10), planned(40, 7, 4), planned(40, 6, 4)),
    )

    assert reasons(result) == ["lower"]
    assert plan(result) == [(37.5, 10), (37.5, 7), (37.5, 6)]


def test_the_top_set_and_the_back_off_sets_progress_on_their_own() -> None:  # scenario 6
    result = target(
        session(7, planned(30, 9, 9, "top"), planned(25, 8, 8, "backoff"), planned(25, 7, 7, "backoff")),
        session(3, planned(30, 10, 10, "top"), planned(25, 8, 8, "backoff"), planned(25, 7, 7, "backoff")),
        settings=TOP_BACKOFF,
    )

    assert reasons(result) == ["weight_up", "plus_rep"]
    assert plan(result) == [(32.5, 6), (25, 9), (25, 7)]
    assert [s.role for s in result.sets] == ["top", "backoff", "backoff"]


def test_without_roles_the_strategy_reads_the_structure_from_the_weights() -> None:
    sessions = same((7, 3), lifted(30, 9), lifted(25, 9), lifted(25, 6))

    straight = target(*sessions)
    top_backoff = target(*sessions, settings=TOP_BACKOFF)

    # Straight: the sets at the most frequent weight progress, the heavier one stays as it was
    assert plan(straight) == [(30, 9), (25, 10), (25, 6)]
    assert [s.role for s in straight.sets] == [None, "straight", "straight"]
    assert plan(top_backoff) == [(30, 10), (25, 10), (25, 6)]
    assert [s.role for s in top_backoff.sets] == ["top", "backoff", "backoff"]


def test_a_manual_weight_change_is_not_taken_as_the_new_plan() -> None:  # scenario 7
    result = target(
        session(7, planned(40, 8, 8), planned(40, 7, 7), planned(40, 6, 6)),
        session(3, planned(40, 9, 9), planned(40, 7, 8, at=37.5), planned(40, 6, 8, at=37.5)),
    )

    assert reasons(result) == ["hold"]
    assert plan(result) == [(40, 9), (40, 7), (40, 6)]
    assert "last_not_comparable" in result.warnings


def test_the_same_weight_change_twice_in_a_row_becomes_the_plan() -> None:
    result = target(
        session(10, planned(40, 8, 8), planned(40, 7, 7), planned(40, 6, 6)),
        *same((6, 3), planned(40, 9, 9), planned(40, 7, 8, at=37.5), planned(40, 6, 8, at=37.5)),
    )

    assert {s.weight_kg for s in result.sets} == {37.5}
    assert reasons(result) == ["plus_rep"]


def test_an_unusual_session_is_kept_out_of_the_progression() -> None:
    result = target(
        session(7, planned(40, 8, 8), planned(40, 7, 7), planned(40, 6, 6)),
        session(3, planned(40, 9, 6), planned(40, 7, 4), planned(40, 6, 3), unusual=True),
    )

    assert reasons(result) == ["hold"]
    assert plan(result) == [(40, 9), (40, 7), (40, 6)]


def test_a_target_missed_by_a_rep_is_repeated() -> None:
    result = target(
        session(7, planned(40, 8, 8), planned(40, 7, 7), planned(40, 6, 6)),
        session(3, planned(40, 9, 9), planned(40, 7, 6), planned(40, 6, 7)),
    )

    assert reasons(result) == ["hold"]
    assert plan(result) == [(40, 9), (40, 7), (40, 7)]  # what was missed again, what was beaten stays


def test_sessions_without_records_only_warn_and_a_decline_suggests_a_deload() -> None:  # scenario 12
    three = target(*same((9, 6, 3), lifted(40, 9), lifted(40, 7), lifted(40, 6)))
    five = target(*same((15, 12, 9, 6, 3), lifted(40, 9), lifted(40, 7), lifted(40, 6)))
    falling = target(
        session(9, lifted(40, 9), lifted(40, 8), lifted(40, 7)),
        session(6, lifted(40, 9), lifted(40, 7), lifted(40, 7)),
        session(3, lifted(40, 9), lifted(40, 7), lifted(40, 6)),
    )

    assert three.warnings == [] and reasons(three) == ["plus_rep"]
    assert five.warnings == ["stall"] and reasons(five) == ["plus_rep"] and five.suggestion is None
    assert "decline" in falling.warnings and reasons(falling) == ["plus_rep"]
    assert falling.suggestion is not None and falling.suggestion.kind == "deload"
    assert {s.weight_kg for s in falling.suggestion.sets} == {35}


def test_too_little_history_repeats_the_last_values() -> None:  # scenario 13
    new = target(session(3, lifted(40, 8), lifted(40, 7)))
    # The strategy changed since the sessions were planned: their roles don't fit, so nothing is built on them
    changed = target(*same((7, 3), planned(30, 8, 8), planned(30, 7, 7)), settings=TOP_BACKOFF)

    assert reasons(new) == ["no_data"] and plan(new) == [(40, 8), (40, 7)]
    assert "low_confidence" in new.warnings
    assert reasons(changed) == ["no_data", "no_data"] and "low_confidence" in changed.warnings


def test_after_a_break_every_working_set_comes_down_by_the_same_steps() -> None:
    result = target(*same((40, 30), lifted(60, 10, "warmup"), lifted(110, 2), lifted(90, 6), lifted(90, 5)))
    bodyweight = target(*same((40, 30), lifted(0, 10), lifted(0, 7)))

    assert reasons(result) == ["comeback"]
    assert result.days_since == 30
    assert plan(result) == [(60, 10), (100, 2), (80, 6), (80, 5)]
    assert plan(bodyweight) == [(0, 9), (0, 6)]


def test_without_a_load_reps_grow_on_the_weakest_set_past_the_range() -> None:
    result = target(*same((7, 3), lifted(0, 12), lifted(0, 12), lifted(0, 11)))

    assert plan(result) == [(0, 12), (0, 12), (0, 12)]
    assert priority(result) == [2]


def test_sets_are_added_only_when_the_exercise_opts_in() -> None:
    sessions = same((7, 3), lifted(40, 8), lifted(40, 7))
    opted_in = Settings(rep_min=6, rep_max=10, weight_step=2.5, sets_max=3)

    assert plan(target(*sessions)) == [(40, 9), (40, 7)]
    assert plan(target(*sessions, settings=opted_in)) == [(40, 8), (40, 7), (40, 7)]
    assert reasons(target(*sessions, settings=opted_in)) == ["add_set"]


def test_warm_ups_drop_sets_and_sets_added_by_hand_stay_out_of_the_progression() -> None:
    legacy = target(*same((7, 3), lifted(20, 10, "warmup"), lifted(40, 8), lifted(40, 7), lifted(30, 8, "drop")))
    # A planned session with a set added by hand (no role): it isn't carried into the next plan
    extra = target(
        session(7, planned(40, 8, 8), planned(40, 7, 7)),
        session(3, planned(40, 8, 8), planned(40, 7, 7), lifted(40, 6)),
    )

    assert plan(legacy) == [(20, 10), (40, 9), (40, 7), (30, 8)]
    assert [s.set_type for s in legacy.sets] == ["warmup", "normal", "normal", "drop"]
    assert plan(extra) == [(40, 9), (40, 7)]


def test_a_drop_names_an_earlier_exercise_of_the_same_group_without_lowering() -> None:  # scenario 10
    result = target(
        session(7, planned(30, 10, 10), planned(30, 8, 8)),
        session(3, planned(30, 10, 10), planned(30, 8, 5), fatigue_from="Chest Press"),
        settings=CABLE,
    )

    assert reasons(result) == ["check_drop"]
    assert result.fatigue_from == "Chest Press"


def test_no_target_without_a_session_with_reps() -> None:
    assert next_target([], DUMBBELL, DAY) is None
    assert next_target([session(3, lifted(None, None))], DUMBBELL, DAY) is None
    assert next_target([session(3, lifted(20, 10, "warmup"))], DUMBBELL, DAY) is None


def test_settings_default_by_equipment_and_can_be_overridden() -> None:
    assert settings_for(Exercise(name="x", muscle_group="chest", equipment="cable")) == Settings(8, 12, 5.0)
    assert settings_for(Exercise(name="x", muscle_group="chest", equipment="dumbbell")) == Settings(6, 10, 2.5)
    assert settings_for(Exercise(name="x", muscle_group="chest")) == Settings(8, 12, 2.5)
    custom = Exercise(
        name="x",
        muscle_group="chest",
        equipment="dumbbell",
        rep_min=12,
        weight_step=2,
        sets_max=4,
        target_rir=0,
        strategy="top_backoff",
    )
    # A minimum above the default maximum widens the range
    assert settings_for(custom) == Settings(12, 12, 2, sets_max=4, target_rir=0, strategy="top_backoff")


# --- API -------------------------------------------------------------------------------------------------------


def log(client: TestClient, days_ago: int, exercise_id: int, *sets: dict, order: int = 1) -> uuid.UUID:
    """A finished workout `days_ago` with the given sets of one exercise."""
    started = now_utc() - dt.timedelta(days=days_ago)
    workout_id = uuid.uuid4()
    put_workout(client, workout_id, started_at=started, ended_at=started + dt.timedelta(hours=1))
    for n, fields in enumerate(sets, start=1):
        put_set(client, workout_id, uuid.uuid4(), exercise_id, exercise_order=order, set_order=n, **fields)
    return workout_id


def test_last_performance_carries_the_target(client: TestClient, exercises: dict[str, int]) -> None:
    bench = exercises["Bench Press (Dumbbell)"]
    log(client, 5, bench, {"weight_kg": 40, "reps": 8}, {"weight_kg": 40, "reps": 7})
    log(
        client,
        2,
        bench,
        {"weight_kg": 40, "reps": 8, "planned_weight_kg": 40, "planned_reps": 8, "role": "straight"},
        {"weight_kg": 40, "reps": 7, "planned_weight_kg": 40, "planned_reps": 7, "role": "straight"},
    )

    result = client.get(f"/api/exercises/{bench}/last-performance").json()
    target_ = result["target"]

    assert target_["blocks"] == [{"role": "straight", "reason": "plus_rep", "weight_kg": 40}]
    assert [(s["weight_kg"], s["reps"], s["priority"]) for s in target_["sets"]] == [(40, 9, True), (40, 7, False)]
    assert (target_["rep_min"], target_["rep_max"], target_["weight_step"], target_["target_rir"]) == (6, 10, 2.5, 1)
    assert target_["sets_max"] is None and target_["warnings"] == [] and target_["suggestion"] is None
    assert result["sets"][0]["planned_reps"] == 8 and result["sets"][0]["role"] == "straight"
    assert client.get(f"/api/exercises/{exercises['Plank']}/last-performance").json()["target"] is None


def test_sets_keep_their_plan_rir_and_unusual_flag(client: TestClient, exercises: dict[str, int]) -> None:
    bench = exercises["Bench Press (Dumbbell)"]
    workout_id = log(
        client,
        1,
        bench,
        {"weight_kg": 37.5, "reps": 8, "planned_weight_kg": 40, "planned_reps": 8, "role": "straight", "rpe": 9},
        {"weight_kg": 37.5, "reps": 7, "planned_weight_kg": 40, "planned_reps": 7, "role": "straight", "unusual": True},
    )

    sets = client.get(f"/api/workouts/{workout_id}").json()["sets"]
    bad_role = {"exercise_id": bench, "exercise_order": 1, "set_order": 3, "role": "warmup"}

    assert [(s["planned_weight_kg"], s["planned_reps"], s["role"], s["rpe"], s["unusual"]) for s in sets] == [
        (40, 8, "straight", 9, False),
        (40, 7, "straight", None, True),
    ]
    assert client.put(f"/api/workouts/{workout_id}/sets/{uuid.uuid4()}", json=bad_role).status_code == 422


def test_a_drop_names_the_earlier_exercise_of_the_group_in_that_workout(
    client: TestClient, exercises: dict[str, int]
) -> None:  # scenario 10, through the database
    fly, press = exercises["Chest Fly (Dumbbell)"], exercises["Bench Press (Barbell)"]
    log(client, 6, fly, {"weight_kg": 20, "reps": 10}, {"weight_kg": 20, "reps": 8}, {"weight_kg": 20, "reps": 7})
    workout_id = log(client, 2, press, {"weight_kg": 100, "reps": 6})
    for n, reps in enumerate((10, 4, 4), start=1):
        put_set(client, workout_id, uuid.uuid4(), fly, exercise_order=2, set_order=n, weight_kg=20, reps=reps)

    target_ = client.get(f"/api/exercises/{fly}/last-performance").json()["target"]

    assert target_["blocks"][0]["reason"] == "check_drop"
    assert target_["fatigue_from"] == "Bench Press (Barbell)"


def test_new_settings_change_the_next_target_but_not_the_logged_sets(
    client: TestClient, exercises: dict[str, int]
) -> None:  # scenario 14
    bench = exercises["Bench Press (Dumbbell)"]
    workout_id = log(client, 5, bench, {"weight_kg": 40, "reps": 10}, {"weight_kg": 40, "reps": 8})
    log(client, 2, bench, {"weight_kg": 40, "reps": 10}, {"weight_kg": 40, "reps": 8})
    before = client.get(f"/api/workouts/{workout_id}").json()["sets"]
    assert client.get(f"/api/exercises/{bench}/last-performance").json()["target"]["blocks"][0]["reason"] == "weight_up"

    client.patch(f"/api/exercises/{bench}", json={"rep_min": 8, "rep_max": 12})

    after = client.get(f"/api/exercises/{bench}/last-performance").json()["target"]
    assert after["blocks"][0]["reason"] == "plus_rep"
    assert [(s["weight_kg"], s["reps"]) for s in after["sets"]] == [(40, 11), (40, 8)]
    assert client.get(f"/api/workouts/{workout_id}").json()["sets"] == before


def test_progression_settings_are_saved_per_exercise(client: TestClient, exercises: dict[str, int]) -> None:
    bench = exercises["Bench Press (Dumbbell)"]

    saved = client.patch(
        f"/api/exercises/{bench}",
        json={"rep_min": 8, "rep_max": 12, "weight_step": 2, "target_rir": 0, "strategy": "top_backoff"},
    ).json()
    assert (saved["rep_min"], saved["rep_max"], saved["weight_step"], saved["sets_max"]) == (8, 12, 2, None)
    assert (saved["target_rir"], saved["strategy"]) == (0, "top_backoff")

    reset = client.patch(f"/api/exercises/{bench}", json={"rep_min": None, "rep_max": None, "strategy": None}).json()
    assert (reset["rep_min"], reset["rep_max"], reset["weight_step"], reset["strategy"]) == (None, None, 2, None)

    for bad in ({"rep_min": 10, "rep_max": 8}, {"weight_step": 0}, {"target_rir": 4}, {"strategy": "pyramid"}):
        assert client.patch(f"/api/exercises/{bench}", json=bad).status_code == 422, bad
    created = client.post("/api/exercises", json={"name": "Landmine Press", "muscle_group": "shoulders", "sets_max": 4})
    assert created.json()["sets_max"] == 4
