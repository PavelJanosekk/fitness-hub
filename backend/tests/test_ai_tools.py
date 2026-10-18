import datetime as dt
import uuid

import pytest
from sqlmodel import Session, col, select

from app.models.body import DailyMetric
from app.models.gym import Workout, WorkoutSet
from app.models.running import Activity
from app.services.ai_tools import SetInput, ToolContext, build_coach_tools

NOW = dt.datetime(2026, 10, 17, 9, 0, tzinfo=dt.UTC)  # Saturday 11:00 in Prague


@pytest.fixture
def tools(session: Session, exercises: dict[str, int]) -> tuple[ToolContext, dict]:
    ctx = ToolContext(session=session, now=NOW)
    return ctx, {fn.__name__: fn for fn in build_coach_tools(ctx)}


def finished_workout(session: Session, exercise_id: int, weight: float, reps: int, days_ago: int) -> Workout:
    started = NOW - dt.timedelta(days=days_ago)
    workout = Workout(name="Chest tri", started_at=started, ended_at=started + dt.timedelta(hours=1), ended_by="user")
    session.add(workout)
    session.flush()
    session.add(
        WorkoutSet(
            workout_id=workout.id, exercise_id=exercise_id, exercise_order=1, set_order=1, weight_kg=weight, reps=reps
        )
    )
    session.commit()
    return workout


def test_calendar_gives_czech_weekdays_and_monday_weeks(tools) -> None:
    _, t = tools

    result = t["get_calendar"]("2026-10-17", 3)

    assert [(d["date"], d["weekday"]) for d in result["days"]] == [
        ("2026-10-17", "sobota"),
        ("2026-10-18", "neděle"),
        ("2026-10-19", "pondělí"),
    ]
    assert result["days"][2]["week"] == "2026-10-19..2026-10-25"


def test_exact_exercise_is_saved_into_a_new_ai_workout(tools, session: Session) -> None:
    ctx, t = tools

    result = t["log_workout_sets_from_ai"](
        "bench press (barbell)", [SetInput(weight_kg=80, reps=10), SetInput(weight_kg=85, reps=8, rpe=8)]
    )

    assert result["status"] == "saved"
    workout = session.get(Workout, uuid.UUID(result["workout_id"]))
    assert (workout.name, workout.source, workout.ended_at) == ("Trénink", "ai", None)
    sets = session.exec(select(WorkoutSet).order_by(col(WorkoutSet.set_order))).all()
    assert [(s.set_order, s.weight_kg, s.reps, s.rpe) for s in sets] == [(1, 80, 10, None), (2, 85, 8, 8)]
    assert ctx.saved_sets[0]["sets_saved"] == 2


def test_more_sets_continue_the_order_and_new_exercises_go_last(tools, session: Session) -> None:
    _, t = tools
    first = t["log_workout_sets_from_ai"]("Bench Press (Barbell)", [SetInput(weight_kg=80, reps=10)])
    t["log_workout_sets_from_ai"]("Chest Dip", [SetInput(weight_kg=0, reps=12)])

    t["log_workout_sets_from_ai"]("Bench Press (Barbell)", [SetInput(weight_kg=80, reps=9)])

    sets = session.exec(select(WorkoutSet).where(WorkoutSet.workout_id == uuid.UUID(first["workout_id"]))).all()
    assert sorted((s.exercise_order, s.set_order) for s in sets) == [(1, 1), (1, 2), (2, 1)]


def test_uncertain_exercise_becomes_a_draft(tools, session: Session) -> None:
    ctx, t = tools

    result = t["log_workout_sets_from_ai"]("benč pres", [SetInput(weight_kg=80, reps=10)])

    assert result["status"] == "needs_confirmation"
    assert "Bench Press (Barbell)" in result["candidates"]
    assert ctx.drafts[0]["reason"] == "exercise_uncertain"
    assert session.exec(select(WorkoutSet)).all() == []


def test_implausible_weight_versus_last_session_becomes_a_draft(
    tools, session: Session, exercises: dict[str, int]
) -> None:
    ctx, t = tools
    finished_workout(session, exercises["Bench Press (Barbell)"], 100, 5, days_ago=3)

    result = t["log_workout_sets_from_ai"]("Bench Press (Barbell)", [SetInput(weight_kg=180, reps=5)])

    assert result["status"] == "needs_confirmation"
    assert ctx.drafts[0]["reason"] == "implausible_numbers"
    assert ctx.drafts[0]["last_session_weights"] == [100]


def test_progression_reports_top_set_and_e1rm(tools, session: Session, exercises: dict[str, int]) -> None:
    _, t = tools
    finished_workout(session, exercises["Squat (Barbell)"], 100, 5, days_ago=14)
    finished_workout(session, exercises["Squat (Barbell)"], 105, 5, days_ago=7)

    result = t["get_exercise_progression"]("squat", weeks=4)

    assert result["exercise"] == "Squat (Barbell)"
    assert [(s["top_set"], s["e1rm"]) for s in result["sessions"]] == [("100 kg x 5", 116.7), ("105 kg x 5", 122.5)]


def test_muscle_group_volume_lists_untrained_groups(tools, session: Session, exercises: dict[str, int]) -> None:
    _, t = tools
    finished_workout(session, exercises["Bench Press (Barbell)"], 100, 5, days_ago=2)

    result = t["get_muscle_group_volume"](30)

    assert result["by_muscle_group"]["chest"] == {"sets": 1, "tonnage_kg": 500, "workouts": 1}
    assert "legs" in result["untrained"]


def test_daily_metric_and_quick_intake(tools, session: Session) -> None:
    _, t = tools

    t["log_daily_metric_from_ai"](weight_kg=84.6)
    t["log_quick_intake_from_ai"](kcal=650, protein_g=40)

    summary = t["get_body_metrics_summary"](7)
    assert session.get(DailyMetric, dt.date(2026, 10, 17)).weight_kg == 84.6
    assert summary["days"][-1] == {
        "date": "2026-10-17",
        "weight_kg": 84.6,
        "weight_7d_avg": 84.6,
        "kcal": 650.0,
        "protein_g": 40.0,
    }


def test_running_context_has_runs_weekly_km_and_leg_days(tools, session: Session, exercises: dict[str, int]) -> None:
    _, t = tools
    session.add(
        Activity(
            external_id="strava:1",
            source="strava",
            start_time=NOW - dt.timedelta(days=2),
            activity_type="Run",
            distance_meters=10000,
            duration_seconds=3600,
            avg_hr=148,
            notes="Easy",
        )
    )
    session.commit()
    finished_workout(session, exercises["Squat (Barbell)"], 100, 5, days_ago=1)

    result = t["get_running_and_marathon_context"](21)

    assert result["runs"] == [
        {
            "date": "2026-10-15",
            "km": 10.0,
            "pace": "6:00/km",
            "avg_hr": 148,
            "name": "Easy",
            "metrics": "pending (streams not fetched yet)",
        }
    ]
    assert result["weekly_km"] == {"2026-W42": 10.0}
    assert result["leg_workouts"][0]["leg_sets"] == 1


def test_call_recording_keeps_what_the_sdk_declares_and_converts(session: Session) -> None:
    """The fallback runner wraps every tool; AFC must still see the same declaration and pydantic-typed args."""
    from google.genai import _extra_utils, types

    from app.services.gemini_service import _recording_calls
    from app.services.nutrition.assistant import NutritionContext, build_nutrition_tools
    from app.services.nutrition.resolver import TopScoreChooser

    raw = [
        *build_coach_tools(ToolContext(session=session, now=NOW)),
        *build_nutrition_tools(NutritionContext(session=session, http=None, chooser_factory=TopScoreChooser)),
    ]
    called: list[str] = []
    wrapped = _recording_calls(raw, called)

    def declare(fn):
        return types.FunctionDeclaration.from_callable_with_api_option(callable=fn, api_option="GEMINI_API")

    assert [declare(fn) for fn in wrapped] == [declare(fn) for fn in raw]
    log_sets = next(fn for fn in wrapped if fn.__name__ == "log_workout_sets_from_ai")
    converted = _extra_utils.convert_argument_from_function(
        {"exercise_name": "x", "sets": [{"weight_kg": 80, "reps": 5}]}, log_sets
    )
    assert isinstance(converted["sets"][0], SetInput)
    wrapped[0]()
    assert called == [raw[0].__name__]
