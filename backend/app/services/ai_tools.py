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

from app.models.coach import Race
from app.models.gym import Exercise, MuscleGroup, Workout, WorkoutSet, WorkoutSource
from app.models.running import Activity, ActivityMetrics, TrainingPlanItem
from app.schemas.body import MetricUpsert
from app.schemas.nutrition import QuickAdd
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
        upcoming_races = session.exec(select(Race).where(Race.date >= start).order_by(col(Race.date))).all()
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

        assert exercise is not None and exercise.id is not None
        if target is None:
            target = Workout(name="Trénink", started_at=ctx.now, source=WorkoutSource.ai)
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
                    completed_at=ctx.now,
                )
            )
        session.commit()
        saved = {"workout_id": str(target.id), "exercise": exercise.name, "sets_saved": len(sets)}
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
    ]


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
