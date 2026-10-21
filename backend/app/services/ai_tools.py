"""Coach tools exposed to Gemini automatic function calling (docs/SPEC.md §7).

Each tool is a closure over a ToolContext; signatures and docstrings are what Gemini sees, so they are
precise and typed (Pydantic models for structured arguments). Return values are compact dicts: they go
back into the model's context, so null fields are dropped.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.bucket import BucketItem
from app.models.coach import Race
from app.models.gym import Exercise, MuscleGroup, Workout, WorkoutSet, WorkoutSource
from app.models.habits import Habit, HabitFrequency, HabitLog
from app.models.running import Activity, ActivityMetrics, TrainingPlanItem
from app.models.side_quests import SideQuest
from app.schemas.body import MetricUpsert
from app.schemas.nutrition import QuickAdd
from app.services import abilities as abilities_svc
from app.services import bucket as bucket_svc
from app.services import habits as habit_svc
from app.services import side_quests as side_svc
from app.services.coach_kb import plan_weeks, read_document
from app.services.exercises import resolve_exercise
from app.services.metrics import daily_series, upsert_daily_metric
from app.services.nutrition import quick_add
from app.services.run_analysis import RUN_TYPES, current_lthr, is_heat
from app.services.run_metrics import Zones, format_pace
from app.timeutils import day_bounds, local_date, now_utc, today

CZECH_WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle")
# Runs with more Z4-Z5 time are quality sessions, not comparable easy/long runs
QUALITY_Z45_SECONDS = 8 * 60
DESCRIPTION_CHARS = 240
# A dictated weight this far from the last session is more likely a misheard number than a PR
PLAUSIBLE_RATIO = (0.5, 1.3)
MAX_PLAUSIBLE_REPS = 50


class SetInput(BaseModel):
    """One dictated set."""

    weight_kg: float | None = Field(default=None, description="Load in kg; 0 for bodyweight, added load otherwise")
    reps: int | None = Field(default=None, description="Repetitions")
    rpe: float | None = Field(default=None, description="Rate of perceived exertion 1-10, only if said")
    set_type: Literal["normal", "warmup", "drop", "failure"] = "normal"
    duration_s: int | None = Field(default=None, description="For timed sets such as a plank, in seconds")


@dataclass
class ToolContext:
    session: Session
    workout_id: uuid.UUID | None = None  # set when dictating inside a specific active workout
    now: dt.datetime = field(default_factory=now_utc)
    drafts: list[dict[str, Any]] = field(default_factory=list)  # awaiting 1-tap confirmation in the UI
    saved_sets: list[dict[str, Any]] = field(default_factory=list)


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None}


def _e1rm(weight: float | None, reps: int | None) -> float | None:
    if not weight or not reps:
        return None
    return round(weight * (1 + reps / 30), 1)


def exercise_catalog(session: Session) -> str:
    """'Name [group]' lines for the system prompt, so the model can use exact exercise names."""
    exercises = session.exec(select(Exercise).order_by(col(Exercise.name))).all()
    return "\n".join(f"- {e.name} [{e.muscle_group}]" for e in exercises)


LOG_MODE_LABELS = {"note": ", s poznámkou a dovedností", "review": ", s hodnocením 1-5, poznámkou a dovedností"}


def habit_catalog(session: Session) -> str:
    """'Title [frequency]' lines of the active habits for the system prompt, so the model uses exact titles."""
    habits = session.exec(
        select(Habit).where(col(Habit.archived_at).is_(None)).order_by(col(Habit.position), col(Habit.id))
    ).all()
    lines = []
    for h in habits:
        kind = "denně" if h.frequency == HabitFrequency.daily else f"týdně {h.weekly_target}×"
        extra = ", bonus" if h.is_bonus else ""
        auto = ", plní se i automaticky z dat" if h.auto_rule else ""
        mode = LOG_MODE_LABELS.get(h.log_mode, "")
        lines.append(f"- {h.title} [{kind}{extra}{auto}{mode}]")
    return "\n".join(lines)


def bucket_catalog(session: Session) -> str:
    """Open bucket-list titles for the system prompt (one compact line), so the model uses exact titles."""
    titles = session.exec(
        select(BucketItem.title)
        .where(col(BucketItem.done_on).is_(None), col(BucketItem.done_before_app).is_(False))
        .order_by(col(BucketItem.id))
    ).all()
    return "; ".join(titles)


def build_coach_tools(ctx: ToolContext) -> list[Callable[..., dict[str, Any]]]:
    session = ctx.session

    def get_body_metrics_summary(days: int = 30) -> dict[str, Any]:
        """Daily body metrics for the last `days` days: weight with 7-day average, intake (kcal and macros
        from logged meals), steps and sleep, plus averages. Days without data are omitted.

        Args:
            days: Window length in days (1-365).
        """
        days = max(1, min(days, 365))
        end = today(ctx.now)
        series = daily_series(session, end - dt.timedelta(days=days - 1), end)
        rows = [
            _compact(
                {
                    "date": d.date.isoformat(),
                    "weight_kg": d.weight_kg,
                    "weight_7d_avg": d.weight_7d_avg,
                    "kcal": d.calories_in,
                    "protein_g": d.protein_g,
                    "carbs_g": d.carbs_g,
                    "fat_g": d.fat_g,
                    "steps": d.steps,
                    "sleep_h": d.sleep_hours,
                }
            )
            for d in series
        ]

        def avg(values: list[float | None]) -> float | None:
            known = [v for v in values if v is not None]
            return round(fmean(known), 1) if known else None

        return {
            "days": [r for r in rows if len(r) > 1],
            "averages": _compact(
                {
                    "kcal_on_logged_days": avg([d.calories_in for d in series]),
                    "protein_g_on_logged_days": avg([d.protein_g for d in series]),
                    "steps": avg([d.steps for d in series]),
                    "sleep_h": avg([d.sleep_hours for d in series]),
                    "weight_7d_avg_start": next((d.weight_7d_avg for d in series if d.weight_7d_avg), None),
                    "weight_7d_avg_end": next((d.weight_7d_avg for d in reversed(series) if d.weight_7d_avg), None),
                }
            ),
            "days_with_logged_intake": sum(1 for d in series if d.calories_in is not None),
        }

    def get_muscle_group_volume(days: int = 30) -> dict[str, Any]:
        """Completed working sets (no warm-ups) and tonnage (kg x reps) per muscle group over the last `days`
        days, to spot neglected muscle groups.

        Args:
            days: Window length in days (1-365).
        """
        days = max(1, min(days, 365))
        since = ctx.now - dt.timedelta(days=days)
        rows = session.exec(
            select(
                Exercise.muscle_group,
                func.count(col(WorkoutSet.id)),
                func.coalesce(func.sum(col(WorkoutSet.weight_kg) * col(WorkoutSet.reps)), 0.0),
                func.count(func.distinct(Workout.id)),
            )
            .join(WorkoutSet, col(WorkoutSet.exercise_id) == Exercise.id)
            .join(Workout, col(Workout.id) == WorkoutSet.workout_id)
            .where(col(Workout.started_at) >= since, col(WorkoutSet.completed), WorkoutSet.set_type != "warmup")
            .group_by(col(Exercise.muscle_group))
        ).all()
        groups = {g: {"sets": s, "tonnage_kg": round(float(t)), "workouts": w} for g, s, t, w in rows}
        workouts = session.exec(select(func.count()).select_from(Workout).where(col(Workout.started_at) >= since)).one()
        return {
            "window_days": days,
            "workouts": workouts,
            "by_muscle_group": groups,
            "untrained": [g.value for g in MuscleGroup if g.value not in groups and g != MuscleGroup.cardio],
        }

    def get_exercise_progression(exercise_name: str, weeks: int = 8) -> dict[str, Any]:
        """Per-session top set and estimated 1RM (weight x (1 + reps/30)) of one exercise over the last
        `weeks` weeks, to detect progress or plateaus.

        Args:
            exercise_name: Exercise name; use the exact name from the exercise list when possible.
            weeks: Window length in weeks (1-104).
        """
        match = resolve_exercise(session, exercise_name)
        exercise = match.exact or (match.candidates[0][0] if match.candidates else None)
        if exercise is None:
            return {"error": f"Unknown exercise {exercise_name!r}"}
        since = ctx.now - dt.timedelta(weeks=max(1, min(weeks, 104)))
        rows = session.exec(
            select(Workout.started_at, WorkoutSet.weight_kg, WorkoutSet.reps)
            .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
            .where(
                WorkoutSet.exercise_id == exercise.id,
                col(WorkoutSet.completed),
                WorkoutSet.set_type != "warmup",
                col(Workout.started_at) >= since,
            )
            .order_by(col(Workout.started_at))
        ).all()
        sessions: dict[dt.date, list[tuple[float | None, int | None]]] = defaultdict(list)
        for started_at, weight, reps in rows:
            sessions[local_date(started_at)].append((weight, reps))
        history = []
        for day, sets in sessions.items():
            top_weight, top_reps = max(sets, key=lambda s: (s[0] or 0, s[1] or 0))
            history.append(
                _compact(
                    {
                        "date": day.isoformat(),
                        "top_set": f"{top_weight or 0:g} kg x {top_reps}",
                        "e1rm": max((e for w, r in sets if (e := _e1rm(w, r))), default=None),
                        "sets": len(sets),
                    }
                )
            )
        result: dict[str, Any] = {"exercise": exercise.name, "sessions": history}
        if not match.exact:
            result["note"] = f"Closest match for {exercise_name!r}"
        return result

    def get_running_and_marathon_context(days: int = 21) -> dict[str, Any]:
        """Recent runs with per-second stream metrics (GAP, EF, decoupling, % time above easy, Z4 minutes),
        RPE and the Strava description (fueling log, pain notes), weekly mileage, HR zones from the current
        LTHR, upcoming races, the weekly plan, and recent leg workouts, to judge training and fatigue.

        Args:
            days: Look-back window in days (1-120).
        """
        days = max(1, min(days, 120))
        since = ctx.now - dt.timedelta(days=days)
        runs = session.exec(
            select(Activity, ActivityMetrics)
            .outerjoin(ActivityMetrics, col(ActivityMetrics.activity_id) == Activity.id)
            .where(col(Activity.activity_type).in_(RUN_TYPES), col(Activity.start_time) >= since)
            .order_by(col(Activity.start_time))
        ).all()
        weekly: dict[str, float] = defaultdict(float)
        run_rows = []
        for run, metrics in runs:
            local = local_date(run.start_time)
            weekly[f"{local.isocalendar().year}-W{local.isocalendar().week:02d}"] += run.distance_meters / 1000
            pace = run.duration_seconds / (run.distance_meters / 1000) if run.distance_meters else None
            row = {
                "date": local.isoformat(),
                "km": round(run.distance_meters / 1000, 2),
                "pace": f"{int(pace // 60)}:{int(pace % 60):02d}/km" if pace else None,
                "avg_hr": run.avg_hr,
                "name": run.notes,
                "heat": True if is_heat(run) else None,
                "rpe": run.rpe,
                "description": (run.description or "")[:DESCRIPTION_CHARS] or None,
            }
            if metrics is not None:
                zones = metrics.zone_seconds or {}
                row |= {
                    "gap": format_pace(metrics.gap_s_per_km),
                    "pace_first10min": format_pace(metrics.pace_first10_s_per_km),
                    "hr_steady": metrics.hr_avg_steady,
                    "ef_gap": metrics.ef_gap,
                    "decoupling_pct": metrics.decoupling_pct,
                    "pct_above_easy": metrics.pct_above_easy,
                    "z4_min": round(zones["z4"] / 60, 1) if "z4" in zones else None,
                    "gap_at_easy_band": format_pace(metrics.gap_at_easy_band_s_per_km),
                }
            else:
                row["metrics"] = "pending (streams not fetched yet)"
            run_rows.append(_compact(row))
        start = today(ctx.now)
        plan = session.exec(
            select(TrainingPlanItem)
            .where(col(TrainingPlanItem.planned_date).between(start, start + dt.timedelta(days=14)))
            .order_by(col(TrainingPlanItem.planned_date))
        ).all()
        legs = session.exec(
            select(Workout.started_at, Workout.name, func.count(col(WorkoutSet.id)))
            .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
            .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
            .where(Exercise.muscle_group == MuscleGroup.legs, col(Workout.started_at) >= since)
            .group_by(col(Workout.id))
            .order_by(col(Workout.started_at))
        ).all()
        upcoming_races = session.exec(
            select(Race).where(Race.date >= start, ~col(Race.hidden)).order_by(col(Race.date))
        ).all()
        lthr = current_lthr(session)
        return {
            "hr_zones": {"lthr": lthr, **Zones(lthr).bounds()} if lthr else None,
            "races": [
                _compact(
                    {"name": r.name, "date": r.date.isoformat(), "days_to_go": (r.date - start).days, "goal": r.goal}
                )
                for r in upcoming_races
            ],
            "plan_weeks": [
                _compact(
                    {
                        "week": f"{w.week_start.isoformat()}..{w.week_end.isoformat()}",
                        "block": w.block,
                        "km": w.km_text,
                        "long_run": w.long_run_text,
                        "quality": w.quality,
                        "notes": w.notes,
                    }
                )
                for w in plan_weeks(session, start - dt.timedelta(days=7), start + dt.timedelta(days=21))
            ],
            "runs": run_rows,
            "weekly_km": {week: round(km, 1) for week, km in weekly.items()},
            "plan_next_14_days": [
                _compact(
                    {
                        "date": p.planned_date.isoformat(),
                        "title": p.title,
                        "km": round(p.target_distance_meters / 1000, 1) if p.target_distance_meters else None,
                        "done": p.completed_activity_id is not None,
                    }
                )
                for p in plan
            ],
            "leg_workouts": [{"date": local_date(s).isoformat(), "name": n, "leg_sets": c} for s, n, c in legs],
        }

    def get_efficiency_trend(weeks: int = 16) -> dict[str, Any]:
        """Aerobic efficiency over time compared at EQUAL heart rate and grade: grade-adjusted pace while HR
        was in the easy band (143-150 at LTHR 172) and EF, per month and per run. Only easy and long runs:
        heat runs and quality sessions (over 8 min in Z4-Z5) are excluded.

        Args:
            weeks: Look-back window in weeks (1-104).
        """
        since = ctx.now - dt.timedelta(weeks=max(1, min(weeks, 104)))
        rows = session.exec(
            select(Activity, ActivityMetrics)
            .join(ActivityMetrics, col(ActivityMetrics.activity_id) == Activity.id)
            .where(col(Activity.activity_type).in_(RUN_TYPES), col(Activity.start_time) >= since)
            .order_by(col(Activity.start_time))
        ).all()
        comparable, excluded = [], {"heat": 0, "quality": 0, "no_easy_band": 0}
        for run, metrics in rows:
            zones = metrics.zone_seconds or {}
            if is_heat(run):
                excluded["heat"] += 1
            elif zones.get("z4", 0) + zones.get("z5", 0) > QUALITY_Z45_SECONDS:
                excluded["quality"] += 1
            elif metrics.gap_at_easy_band_s_per_km is None:
                excluded["no_easy_band"] += 1
            else:
                comparable.append((run, metrics))
        by_month: dict[str, list[ActivityMetrics]] = defaultdict(list)
        for run, metrics in comparable:
            by_month[local_date(run.start_time).strftime("%Y-%m")].append(metrics)

        def median(values: list[float]) -> float | None:
            ordered = sorted(values)
            return ordered[len(ordered) // 2] if ordered else None

        lthr = current_lthr(session)
        return {
            "easy_band_hr": "{}-{}".format(*Zones(lthr).easy_band) if lthr else None,
            "months": {
                month: _compact(
                    {
                        "runs": len(ms),
                        "gap_at_easy_band": format_pace(median([m.gap_at_easy_band_s_per_km or 0 for m in ms])),
                        "ef_gap": median([m.ef_gap for m in ms if m.ef_gap]),
                    }
                )
                for month, ms in by_month.items()
            },
            "runs": [
                _compact(
                    {
                        "date": local_date(run.start_time).isoformat(),
                        "km": round(run.distance_meters / 1000, 2),
                        "gap_at_easy_band": format_pace(m.gap_at_easy_band_s_per_km),
                        "ef_gap": m.ef_gap,
                        "decoupling_pct": m.decoupling_pct,
                    }
                )
                for run, m in comparable
            ],
            "excluded": excluded,
        }

    def read_knowledge_base(document: str) -> dict[str, Any]:
        """Full text of one document of the athlete's running knowledge base (synced from GitHub), e.g.
        "04" for the timeline plan, "05" methodology, "06" workouts library, "07" nutrition, "08" recovery,
        "09" strength/gym, "10" gear, "12" open questions, "03" training log.

        Args:
            document: File name or its numeric prefix, e.g. "07" or "07_nutrition.md".
        """
        doc = read_document(session, document)
        if doc is None:
            return {"error": f"No single document matches {document!r}"}
        return {"document": doc.path, "content": doc.content}

    def log_workout_sets_from_ai(
        exercise_name: str, sets: list[SetInput], workout_id: str | None = None
    ) -> dict[str, Any]:
        """Log dictated sets of ONE exercise into the active workout (one is created when none is active).
        Saved directly when the exercise name matches exactly and the numbers are plausible; otherwise it
        returns status "needs_confirmation" and the user confirms in the app with one tap.

        Args:
            exercise_name: Exact exercise name from the exercise list whenever possible.
            sets: The sets in the order they were done.
            workout_id: Only if the user named a specific workout; normally omit.
        """
        if not sets:
            return {"error": "No sets given"}
        match = resolve_exercise(session, exercise_name)
        exercise = match.exact
        previous = _last_weights(session, exercise.id) if exercise else []
        reason = None
        if exercise is None:
            reason = "exercise_uncertain" if match.candidates else "exercise_unknown"
        elif _implausible(sets, previous):
            reason = "implausible_numbers"

        target = _target_workout(session, ctx, workout_id)
        if reason is not None:
            draft = {
                "kind": "workout_sets",
                "reason": reason,
                "input_exercise_name": exercise_name,
                "candidates": [{"exercise_id": e.id, "name": e.name, "similarity": s} for e, s in match.candidates],
                "workout_id": str(target.id) if target else None,
                "sets": [s.model_dump(exclude_none=True) for s in sets],
                "last_session_weights": previous,
            }
            ctx.drafts.append(draft)
            return {
                "status": "needs_confirmation",
                "reason": reason,
                "candidates": [e.name for e, _ in match.candidates],
                "message": "Not saved; the user confirms it in the app.",
            }

        assert exercise is not None
        saved = save_sets(session, exercise, sets, target, ctx.now)
        ctx.saved_sets.append(saved)
        return {"status": "saved", **saved}

    def log_daily_metric_from_ai(
        weight_kg: float | None = None, steps: int | None = None, sleep_hours: float | None = None
    ) -> dict[str, Any]:
        """Record today's body weight, steps or sleep as told by the user (manual values override devices).

        Args:
            weight_kg: Body weight in kg.
            steps: Step count for today.
            sleep_hours: Hours slept last night.
        """
        if weight_kg is None and steps is None and sleep_hours is None:
            return {"error": "Nothing to record"}
        metric = upsert_daily_metric(
            session, MetricUpsert(date=today(ctx.now), weight_kg=weight_kg, steps=steps, sleep_hours=sleep_hours)
        )
        return {"status": "saved", **_compact(metric.model_dump(mode="json"))}

    def log_quick_intake_from_ai(
        kcal: float, protein_g: float | None = None, carbs_g: float | None = None, fat_g: float | None = None
    ) -> dict[str, Any]:
        """Quick-add calories (and optional macros) eaten today, when the user gives totals rather than foods.

        Args:
            kcal: Energy in kcal.
            protein_g: Protein in grams.
            carbs_g: Carbohydrates in grams.
            fat_g: Fat in grams.
        """
        body = QuickAdd(
            id=uuid.uuid4(), date=today(ctx.now), kcal=kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g
        )
        meal, item = quick_add(session, body)
        return {"status": "saved", "date": meal.logged_date.isoformat(), "kcal": item.kcal}

    def get_calendar(start_date: str | None = None, days: int = 14) -> dict[str, Any]:
        """Dates with their Czech weekday and Monday-Sunday week, starting at `start_date` (default today).
        Use it instead of computing weekdays or date offsets yourself.

        Args:
            start_date: First date as YYYY-MM-DD; omit for today.
            days: Number of days to list (1-120).
        """
        try:
            start = dt.date.fromisoformat(start_date) if start_date else today(ctx.now)
        except ValueError:
            return {"error": f"Invalid date {start_date!r}, use YYYY-MM-DD"}
        rows = []
        for offset in range(max(1, min(days, 120))):
            day = start + dt.timedelta(days=offset)
            monday = day - dt.timedelta(days=day.weekday())
            rows.append(
                {
                    "date": day.isoformat(),
                    "weekday": CZECH_WEEKDAYS[day.weekday()],
                    "week": f"{monday.isoformat()}..{(monday + dt.timedelta(days=6)).isoformat()}",
                }
            )
        return {"today": today(ctx.now).isoformat(), "days": rows}

    def get_habit_summary(days: int = 30) -> dict[str, Any]:
        """The user's daily and weekly routine (habit tracker): per habit the completion rate over the last
        `days` days, current and best streak (days for daily habits, weeks for weekly ones) and the last day done;
        plus the daily routine's average, perfect days, weekday pattern and the streak of weeks at >= 60 %.
        Use it for questions about discipline, consistency and routines.

        Args:
            days: Window for rates and averages (7-365).
        """
        on = today(ctx.now)
        days = max(7, min(days, 365))
        start = on - dt.timedelta(days=days - 1)
        board = habit_svc.load_board(session, end=on, archived=False)
        if not board:
            return {"habits": [], "message": "The user has no habits set up."}
        rows = []
        for item in board:
            habit = item.habit
            done, scheduled = habit_svc.completion(item, start, on)
            last = max((d for d in item.done if d <= on), default=None)
            row = {
                "title": habit.title,
                "frequency": habit.frequency,
                "weekly_target": habit.weekly_target if habit.frequency == HabitFrequency.weekly else None,
                "bonus": habit.is_bonus or None,
                "auto": habit.auto_rule,
                "rate_pct": round(done / scheduled * 100) if scheduled else None,
                "done": done,
                "scheduled": scheduled,
                "current_streak": habit_svc.current_streak(item, on),
                "best_streak": habit_svc.best_streak(item, on),
                "last_done": last.isoformat() if last else None,
            }
            if habit.frequency == HabitFrequency.weekly:
                row["done_this_week"] = habit_svc.week_count(item.done, habit_svc.week_start(on))
            else:
                row["done_today"] = on in item.done
            rows.append(_compact(row))

        day_pcts: list[tuple[dt.date, float]] = []
        for offset in range(days):
            day = start + dt.timedelta(days=offset)
            done, scheduled = habit_svc.routine_day(board, day)
            if scheduled and day < on:  # today is still open
                day_pcts.append((day, done / scheduled * 100))
        by_weekday: dict[int, list[float]] = defaultdict(list)
        for day, pct in day_pcts:
            by_weekday[day.weekday()].append(pct)
        return {
            "today": on.isoformat(),
            "window_days": days,
            "habits": rows,
            "daily_routine": _compact(
                {
                    "avg_pct": round(fmean(p for _, p in day_pcts)) if day_pcts else None,
                    "perfect_days": sum(1 for _, p in day_pcts if p >= 100),
                    "days_counted": len(day_pcts),
                    "by_weekday_pct": {CZECH_WEEKDAYS[w]: round(fmean(v)) for w, v in sorted(by_weekday.items())},
                    "week_streak": habit_svc.routine_week_streak(board, on),
                    "week_streak_threshold_pct": habit_svc.ROUTINE_WEEK_PCT,
                }
            ),
        }

    def set_habits_done(
        habit_titles: list[str],
        done: bool = True,
        date: str | None = None,
        note: str | None = None,
        rating: int | None = None,
        ability: str | None = None,
        ability_is_new: bool = False,
    ) -> dict[str, Any]:
        """Tick (or untick) habits of the user's routine, e.g. "ustlal jsem a vzal kreatin". Only exact titles
        are saved; anything else is returned with candidates and NOT saved, so ask the user which one they meant.
        Habits marked "s poznámkou" / "s hodnocením" take an entry: what the user did (note), stars and the
        dovednost (skill) it was, e.g. "zkusil jsem lezení, super, 5 hvězd" -> note, rating=5, ability="Lezení".

        Args:
            habit_titles: Exact habit titles from the routine list. Only one title when note / rating / ability
                is given.
            done: True ticks, False unticks (for a weekly habit it unticks the whole week).
            date: Day as YYYY-MM-DD; omit for today. For a weekly habit any day of that week.
            note: Short Czech note of what the user did or tried.
            rating: Stars 1-5, only when the user rated it.
            ability: The dovednost, a short noun ("Lezení", "Keramika"). A name like an existing one but not the
                same is not saved: the candidates come back, ask the user.
            ability_is_new: True only after the user confirmed that a similar-looking name is a new dovednost.
        """
        try:
            day = dt.date.fromisoformat(date) if date else today(ctx.now)
        except ValueError:
            return {"error": f"Invalid date {date!r}, use YYYY-MM-DD"}
        if day > today(ctx.now):
            return {"error": "Cannot tick a future day"}
        content: dict[str, Any] = {}
        if note is not None or rating is not None or ability is not None:
            if len(habit_titles) != 1 or not done:
                return {"error": "note / rating / ability need exactly one habit title and done=True"}
            if rating is not None and not 1 <= rating <= 5:
                return {"error": "rating must be 1-5"}
            if note is not None:
                content["note"] = note[:2000]
            if rating is not None:
                content["rating"] = rating
        ability_candidates: list[str] = []
        if ability and ability.strip():
            match, ability_candidates = abilities_svc.resolve(session, ability)
            if match is not None:
                content["ability"] = match.name
            elif not ability_candidates or ability_is_new:
                ability_candidates = []
                content["ability"] = ability.strip()[: abilities_svc.MAX_NAME]
        saved, unmatched = [], []
        for title in habit_titles:
            habit, candidates = habit_svc.resolve_habit(session, title)
            if habit is None:
                unmatched.append({"input": title, "candidates": [h.title for h, _ in candidates]})
                continue
            if not done and habit.frequency == HabitFrequency.weekly:
                monday = habit_svc.week_start(day)
                for log in session.exec(
                    select(HabitLog).where(
                        HabitLog.habit_id == habit.id,
                        col(HabitLog.date).between(monday, monday + dt.timedelta(days=6)),
                    )
                ):
                    session.delete(log)
                session.commit()
            else:
                if done and day < habit.start_date:
                    habit.start_date = day
                    session.add(habit)
                habit_svc.set_day(session, habit, day, done, content)
            saved.append(habit.title)
        result: dict[str, Any] = {"date": day.isoformat(), "done": done, "saved": saved}
        if saved and content:
            result["entry_saved"] = content
        if ability_candidates:
            result["ability_not_saved"] = {"input": ability, "similar": ability_candidates}
            result["ability_message"] = "The dovednost was not saved: ask if it is one of `similar` or a new one."
        if unmatched:
            result["not_saved"] = unmatched
            result["message"] = "Titles in not_saved did not match exactly and were not saved."
        return result

    def get_rpg_status() -> dict[str, Any]:
        """The user's RPG layer (gamified training): level, title, XP this week and today, the weekly streak
        multiplier, debuffs (tired, cursed habits), this week's quests with progress, the marathon boss, skills
        (rusting ones flagged) and every XP change of the last 7 days with its reason. Use it for the weekly RPG
        summary ("game master") and for questions about XP, level, penalties, quests or the boss."""
        from app.services import rpg
        from app.services.boss import marathon_boss

        on = today(ctx.now)
        ledger = rpg.build_ledger(session, on)
        level = rpg.level_of(ledger.total)
        week_start = on - dt.timedelta(days=on.weekday())
        recent = [
            {"date": e.date.isoformat(), "xp": e.amount, "reason": e.text}
            for e in ledger.entries
            if e.date > on - dt.timedelta(days=7) and (e.amount != 0 or e.kind in {"forgiven", "curse", "tired"})
        ]
        boss = marathon_boss(session, on)
        return _compact(
            {
                "today": on.isoformat(),
                "level": level,
                "title": rpg.title_of(level),
                "xp_total": ledger.total,
                "xp_to_next_level": rpg.level_start(level + 1) - ledger.total,
                "xp_this_week": sum(e.amount for e in ledger.entries if e.date >= week_start),
                "multiplier": ledger.multiplier,
                "finished_weeks_in_a_row": ledger.week_streak,
                "tired": ledger.tired or None,
                "cursed_habits": ledger.cursed or None,
                "quests": [
                    {
                        "title": q.title,
                        "progress": q.progress,
                        "target": q.target,
                        "unit": q.unit,
                        "xp": q.xp,
                        "done": q.done_on is not None,
                    }
                    for q in ledger.quests
                ],
                "boss": boss
                and {
                    "name": boss.name,
                    "hp": boss.hp,
                    "max_hp": boss.max_hp,
                    "days_left": boss.days_left,
                    "status": boss.status,
                },
                "skills": [
                    {"name": rpg.SKILL_NAMES[key], "level": rpg.skill_level_of(state.xp), "idle_days": state.idle_days}
                    for key, state in ledger.skills.items()
                ],
                "xp_changes_last_7_days": recent,
            }
        )

    def get_abilities(entries_per_ability: int = 3) -> dict[str, Any]:
        """The user's Dovednosti: abilities the hero picked up through the routine ("Vyzkoušet jednu novou věc",
        "Učit se novou dovednost"), each with how many times, first / last day, level and the latest notes and
        stars. Use it for questions like "co nového jsem letos zkusil?" or to suggest what to try next.

        Args:
            entries_per_ability: How many of the latest entries to return per dovednost (0-10).
        """
        keep = max(0, min(entries_per_ability, 10))
        rows = []
        for state in abilities_svc.load(session, today(ctx.now)):
            _, level_name = abilities_svc.level_of(state.count)
            latest = [
                _compact({"date": e.date.isoformat(), "habit": e.habit_title, "note": e.note, "rating": e.rating})
                for e in reversed(state.entries[-keep:] if keep else [])
            ]
            rows.append(
                _compact(
                    {
                        "name": state.ability.name,
                        "times": state.count,
                        "first": state.first_on.isoformat() if state.first_on else None,
                        "last": state.last_on.isoformat() if state.last_on else None,
                        "level": level_name if state.count else None,
                        "latest": latest or None,
                    }
                )
            )
        return {"today": today(ctx.now).isoformat(), "abilities": rows}

    def get_bucket_list(category: str | None = None, status: str = "open") -> dict[str, Any]:
        """The user's bucket list (lifelong things to experience): items with category, rarity and the XP they pay,
        planned date, year goal, season, cost, travel time, steps and auto-completion progress; plus totals, the
        year quest, visited countries and continents. Use it to suggest what to do (e.g. a trip that fits the
        training plan, nothing risky in race week) and for questions about the bucket list.

        Args:
            category: One of travel, expedition, experience, adrenaline, sport, skill, food, wellbeing; omit for all.
            status: "open", "done" or "all".
        """
        on = today(ctx.now)
        state = bucket_svc.load(session, on)
        rows = []
        for s in state.items:
            item = s.item
            if (
                (category and item.category != category)
                or (status == "open" and s.done)
                or (status == "done" and not s.done)
            ):
                continue
            rows.append(
                _compact(
                    {
                        "title": item.title,
                        "category": bucket_svc.CATEGORY_NAMES.get(item.category, item.category),
                        "rarity": bucket_svc.RARITIES[item.rarity][0],
                        "xp": s.xp if s.done else bucket_svc.RARITIES[item.rarity][1],
                        "done_on": s.done_on.isoformat() if s.done_on else None,
                        "done_before_app": s.source == "before" or None,
                        "auto": s.auto_label if s.source == "auto" else s.auto_progress,
                        "planned_for": item.planned_for.isoformat() if item.planned_for and not s.done else None,
                        "year_goal": item.year_goal == on.year or None,
                        "season": item.season,
                        "cost": "€" * item.cost if item.cost else None,
                        "travel_time": item.travel_time,
                        "steps": f"{sum(1 for st in s.steps if st.done_on)}/{len(s.steps)}" if s.steps else None,
                        "memory": item.memory,
                    }
                )
            )
        done, reached = bucket_svc.year_progress(state, on.year)
        return {
            "today": on.isoformat(),
            "items": rows,
            "done_total": sum(1 for s in state.items if s.done),
            "items_total": len(state.items),
            "year_quest": {
                "done": done,
                "target": bucket_svc.YEAR_QUEST_ITEMS,
                "reached_on": reached and reached.isoformat(),
            },
            "countries": [c.code for c in state.countries],
            "continents": sorted(state.continents),
        }

    def complete_bucket_items(titles: list[str], date: str | None = None, memory: str | None = None) -> dict[str, Any]:
        """Mark bucket-list items as done, e.g. "dneska jsem skočil bungee". Only exact titles are saved; anything
        else comes back with candidates and is NOT saved, so ask the user which one they meant. The app announces a
        completed item to the user itself.

        Args:
            titles: Exact item titles from the bucket list.
            date: Day as YYYY-MM-DD; omit for today.
            memory: Optional short note in the user's words (where, with whom, how it was).
        """
        try:
            day = dt.date.fromisoformat(date) if date else today(ctx.now)
        except ValueError:
            return {"error": f"Invalid date {date!r}, use YYYY-MM-DD"}
        if day > today(ctx.now):
            return {"error": "Cannot complete a future day"}
        saved, unmatched = [], []
        for title in titles:
            item, candidates = bucket_svc.resolve(session, title)
            if item is None:
                unmatched.append({"input": title, "candidates": [i.title for i, _ in candidates]})
                continue
            item.done_on, item.done_before_app = day, False
            if memory and not item.memory:
                item.memory = memory
            session.add(item)
            saved.append(item.title)
        session.commit()
        result: dict[str, Any] = {"date": day.isoformat(), "saved": saved}
        if unmatched:
            result["not_saved"] = unmatched
            result["message"] = "Titles in not_saved did not match exactly and were not saved."
        return result

    def get_side_quests(
        category: str | None = None, duration: str | None = None, status: str = "open"
    ) -> dict[str, Any]:
        """The user's side quests: smaller projects and adventures ("learn X", "make Y", nearby day trips) with
        category, duration, the XP they pay, drive time for trips and whether they are started ("rozjeto"); plus this
        week's quest (complete one side quest a week). Use it to suggest a side quest that fits the week (a trip on a
        rest day or after a long run, a short one on a busy week) and for questions about side quests.

        Args:
            category: One of learn, skill, make, food, move, explore, people, self, home, trip; omit for all.
            duration: One of moment (up to an hour), day, weekend, week, month; omit for all.
            status: "open", "active" (started), "done" or "all".
        """
        on = today(ctx.now)
        states = side_svc.load(session, on)
        rows = []
        for s in states:
            quest = s.quest
            if (
                (category and quest.category != category)
                or (duration and quest.duration != duration)
                or (status == "open" and s.done)
                or (status == "active" and (s.done or not quest.active))
                or (status == "done" and not s.done)
            ):
                continue
            rows.append(
                _compact(
                    {
                        "title": quest.title,
                        "category": side_svc.CATEGORIES[quest.category][0],
                        "duration": side_svc.DURATIONS[quest.duration][0],
                        "xp": s.xp if s.done else side_svc.full_xp(quest),
                        "active": quest.active or None,
                        "drive_min": quest.travel_minutes,
                        "km": quest.distance_km,
                        "done_on": quest.done_on.isoformat() if quest.done_on else None,
                        "done_before_app": quest.done_before_app or None,
                        "note": quest.note,
                        "memory": quest.memory,
                    }
                )
            )
        monday = on - dt.timedelta(days=on.weekday())
        week = [s.quest.title for s in states if s.xp and s.quest.done_on and s.quest.done_on >= monday]
        return {
            "today": on.isoformat(),
            "items": rows,
            "done_total": sum(1 for s in states if s.done),
            "items_total": len(states),
            "this_week_done": week,
        }

    def complete_side_quests(titles: list[str], date: str | None = None, memory: str | None = None) -> dict[str, Any]:
        """Mark side quests as done, e.g. "byl jsem v Macoše". Exact titles (accents and case don't matter) are
        saved; anything else comes back with candidates and is NOT saved, so ask the user which one they meant (call
        get_side_quests to see the titles).

        Args:
            titles: Side quest titles.
            date: Day as YYYY-MM-DD; omit for today.
            memory: Optional short note in the user's words (how it was).
        """
        try:
            day = dt.date.fromisoformat(date) if date else today(ctx.now)
        except ValueError:
            return {"error": f"Invalid date {date!r}, use YYYY-MM-DD"}
        if day > today(ctx.now):
            return {"error": "Cannot complete a future day"}
        saved, unmatched = [], []
        for title in titles:
            quest, candidates = bucket_svc.resolve_title(session, SideQuest, title)
            if quest is None:
                unmatched.append({"input": title, "candidates": [q.title for q, _ in candidates]})
                continue
            quest.done_on, quest.done_before_app, quest.active = day, False, False
            if memory and not quest.memory:
                quest.memory = memory
            session.add(quest)
            saved.append(quest.title)
        session.commit()
        result: dict[str, Any] = {"date": day.isoformat(), "saved": saved}
        if unmatched:
            result["not_saved"] = unmatched
            result["message"] = "Titles in not_saved did not match exactly and were not saved."
        return result

    return [
        get_calendar,
        get_body_metrics_summary,
        get_muscle_group_volume,
        get_exercise_progression,
        get_running_and_marathon_context,
        get_efficiency_trend,
        read_knowledge_base,
        log_workout_sets_from_ai,
        log_daily_metric_from_ai,
        log_quick_intake_from_ai,
        get_habit_summary,
        set_habits_done,
        get_rpg_status,
        get_abilities,
        get_bucket_list,
        complete_bucket_items,
        get_side_quests,
        complete_side_quests,
    ]


def save_sets(
    session: Session, exercise: Exercise, sets: list[SetInput], target: Workout | None, now: dt.datetime
) -> dict[str, Any]:
    """Append completed sets of one exercise to a workout (a new "Trénink" when none is given)."""
    assert exercise.id is not None
    if target is None:
        target = Workout(name="Trénink", started_at=now, source=WorkoutSource.ai)
        session.add(target)
        session.flush()
    order, next_set = _position(session, target.id, exercise.id)
    for offset, s in enumerate(sets):
        session.add(
            WorkoutSet(
                workout_id=target.id,
                exercise_id=exercise.id,
                exercise_order=order,
                set_order=next_set + offset,
                set_type=s.set_type,
                weight_kg=s.weight_kg,
                reps=s.reps,
                rpe=s.rpe,
                duration_s=s.duration_s,
                completed=True,
                completed_at=now,
            )
        )
    session.commit()
    return {"workout_id": str(target.id), "exercise": exercise.name, "sets_saved": len(sets)}


def target_workout(session: Session, now: dt.datetime, workout_id: str | None) -> Workout | None:
    """The named workout, else today's open workout, else None."""
    return _target_workout(session, ToolContext(session=session, now=now), workout_id)


def _last_weights(session: Session, exercise_id: int | None) -> list[float]:
    latest = session.exec(
        select(Workout.id)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(WorkoutSet.exercise_id == exercise_id, col(Workout.ended_at).is_not(None))
        .order_by(col(Workout.started_at).desc())
        .limit(1)
    ).first()
    if latest is None:
        return []
    weights = session.exec(
        select(WorkoutSet.weight_kg).where(WorkoutSet.workout_id == latest, WorkoutSet.exercise_id == exercise_id)
    ).all()
    return [w for w in weights if w is not None]


def _implausible(sets: list[SetInput], previous_weights: list[float]) -> bool:
    if any(s.reps is not None and s.reps > MAX_PLAUSIBLE_REPS for s in sets):
        return True
    reference = max(previous_weights, default=0)
    if reference <= 0:
        return False  # no history (or bodyweight only): nothing to compare against
    low, high = PLAUSIBLE_RATIO
    return any(s.weight_kg and not (low * reference <= s.weight_kg <= high * reference) for s in sets)


def _target_workout(session: Session, ctx: ToolContext, workout_id: str | None) -> Workout | None:
    for candidate in (workout_id, ctx.workout_id):
        if candidate:
            try:
                workout = session.get(Workout, uuid.UUID(str(candidate)))
            except ValueError:
                workout = None
            if workout is not None:
                return workout
    lo, _ = day_bounds(today(ctx.now))
    return session.exec(
        select(Workout)
        .where(col(Workout.ended_at).is_(None), col(Workout.started_at) >= lo - dt.timedelta(hours=6))
        .order_by(col(Workout.started_at).desc())
    ).first()


def _position(session: Session, workout_id: uuid.UUID, exercise_id: int) -> tuple[int, int]:
    """(exercise_order, next set_order) for adding sets of an exercise to a workout."""
    existing = session.exec(
        select(func.min(WorkoutSet.exercise_order), func.max(WorkoutSet.set_order)).where(
            WorkoutSet.workout_id == workout_id, WorkoutSet.exercise_id == exercise_id
        )
    ).one()
    if existing[0] is not None:
        return existing[0], existing[1] + 1
    last_order = session.exec(
        select(func.max(WorkoutSet.exercise_order)).where(WorkoutSet.workout_id == workout_id)
    ).one()
    return (last_order or 0) + 1, 1
