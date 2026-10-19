"""Aggregates behind the Gym → Grafy tab (E23): training calendar, weekly volume, exercise progression."""

import datetime as dt
import itertools
from collections import defaultdict
from typing import Literal

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.gym import Exercise, Workout, WorkoutSet
from app.schemas.gym import (
    ExerciseProgression,
    GymStats,
    ProgressionSession,
    StatsDay,
    StatsExercise,
    StatsWeek,
)
from app.services.workouts import E1RM_MAX_REPS, WORKING_SET, _epley
from app.timeutils import local_date, today

CALENDAR_WEEKS = 53  # the heatmap: a full year ending with the current week

# Antagonist pairs for the balance radar: MUSCLES[i] faces MUSCLES[i + 4]
MUSCLES = ("chest", "front_delts", "biceps", "quads", "back", "rear_delts", "triceps", "hamstrings")

_REAR_DELTS = ("reverse fly", "rear delt", "face pull", "zadní ramen")
_FRONT_DELTS = ("press", "front raise", "arnold", "tlak", "předpažování")
_HAMSTRINGS = (
    "leg curl",
    "hamstring",
    "romanian",
    "rdl",
    "stiff",
    "good morning",
    "nordic",
    "deadlift",
    "zakopáv",
    "rumun",
    "mrtv",
)
_QUADS = (
    "squat",
    "leg press",
    "leg extension",
    "lunge",
    "hack",
    "split",
    "step up",
    "dřep",
    "předkopáv",
    "výpad",
    "legpress",
)
_BACK_EXCLUDED = ("shrug", "back extension", "hyperextension", "krčení")


def antagonist_muscle(name: str, muscle_group: str) -> str | None:
    """The muscle of an antagonist pair an exercise mainly trains, derived from its name and group.

    None for exercises outside the pairs (lateral raises, calves, shrugs, core) or not recognised; the
    response reports those sets so the radar can show its coverage.
    """
    n = name.lower()
    has = lambda words: any(w in n for w in words)  # noqa: E731
    match muscle_group:
        case "chest":
            return "chest"
        case "back":
            return None if has(_BACK_EXCLUDED) else "back"
        case "shoulders":
            if has(_REAR_DELTS):
                return "rear_delts"
            return "front_delts" if has(_FRONT_DELTS) else None
        case "biceps":
            return None if "wrist" in n else "biceps"
        case "triceps":
            return "triceps"
        case "legs":
            if has(_HAMSTRINGS):
                return "hamstrings"
            return "quads" if has(_QUADS) else None
    return None


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def gym_stats(session: Session, weeks: int, now: dt.datetime | None = None) -> GymStats:
    current_week = _monday(today(now))
    first_week = current_week - dt.timedelta(weeks=max(weeks, CALENDAR_WEEKS) - 1)
    # A day early in UTC, so the local Monday is fully covered; rows before it are dropped below
    since = dt.datetime.combine(first_week - dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)
    rows = session.exec(
        select(
            Workout.id, Workout.started_at, WorkoutSet.weight_kg, WorkoutSet.reps, Exercise.name, Exercise.muscle_group
        )
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .where(WORKING_SET, col(Workout.started_at) >= since)
    ).all()

    calendar_start = current_week - dt.timedelta(weeks=CALENDAR_WEEKS - 1)
    weeks_start = current_week - dt.timedelta(weeks=weeks - 1)
    days: dict[dt.date, dict] = defaultdict(lambda: {"workouts": set(), "sets": 0, "volume": 0.0})
    by_week: dict[dt.date, dict] = {
        weeks_start + dt.timedelta(weeks=i): {
            "workouts": set(),
            "sets": defaultdict(int),
            "volume": defaultdict(float),
            "muscles": defaultdict(int),
            "unclassified": 0,
        }
        for i in range(weeks)
    }
    for workout_id, started_at, weight, reps, name, group in rows:
        day = local_date(started_at)
        volume = (weight or 0.0) * (reps or 0)
        if day >= calendar_start:
            entry = days[day]
            entry["workouts"].add(workout_id)
            entry["sets"] += 1
            entry["volume"] += volume
        week = by_week.get(_monday(day))
        if week is None:
            continue
        week["workouts"].add(workout_id)
        week["sets"][group] += 1
        week["volume"][group] += volume
        if muscle := antagonist_muscle(name, group):
            week["muscles"][muscle] += 1
        elif group not in ("core", "cardio"):
            week["unclassified"] += 1

    return GymStats(
        days=[
            StatsDay(date=d, workouts=len(e["workouts"]), sets=e["sets"], volume_kg=round(e["volume"], 1))
            for d, e in sorted(days.items())
        ],
        weeks=[
            StatsWeek(
                week_start=start,
                workouts=len(w["workouts"]),
                sets=dict(w["sets"]),
                volume_kg={g: round(v, 1) for g, v in w["volume"].items()},
                muscles=dict(w["muscles"]),
                unclassified_sets=w["unclassified"],
            )
            for start, w in by_week.items()
        ],
        exercises=_exercise_list(session),
    )


def _exercise_list(session: Session) -> list[StatsExercise]:
    rows = session.exec(
        select(
            Exercise.id,
            Exercise.name,
            Exercise.muscle_group,
            func.count(func.distinct(Workout.id)),
            func.max(Workout.started_at),
        )
        .join(WorkoutSet, col(WorkoutSet.exercise_id) == Exercise.id)
        .join(Workout, col(Workout.id) == WorkoutSet.workout_id)
        .where(WORKING_SET)
        .group_by(col(Exercise.id))
        .order_by(func.count(func.distinct(Workout.id)).desc(), col(Exercise.name))
    ).all()
    return [
        StatsExercise(exercise_id=i, name=n, muscle_group=g, sessions=s, last_date=local_date(last))
        for i, n, g, s, last in rows
    ]


def exercise_progression(session: Session, exercise: Exercise) -> ExerciseProgression:
    """Per workout: heaviest set, best estimated 1RM (Epley, up to 12 reps), most reps, and which were records."""
    rows = session.exec(
        select(Workout.id, Workout.started_at, WorkoutSet.weight_kg, WorkoutSet.reps)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(WorkoutSet.exercise_id == exercise.id, WORKING_SET)
        .order_by(col(Workout.started_at), col(Workout.id))
    ).all()
    sessions: list[ProgressionSession] = []
    best: dict[str, float] = {}
    for (workout_id, started_at), group in itertools.groupby(rows, key=lambda r: (r[0], r[1])):
        sets = [(w, r) for _, _, w, r in group]
        loaded = [(w, r) for w, r in sets if w and w > 0 and r]
        top = max(loaded, default=None)
        e1rm = max(((_epley(w, r), w, r) for w, r in loaded if r <= E1RM_MAX_REPS), default=None)
        max_reps = max((r for _, r in sets if r), default=None)
        values: dict[Literal["weight", "e1rm", "reps"], float | None] = {
            "weight": top[0] if top else None,
            "e1rm": e1rm[0] if e1rm else None,
            "reps": max_reps if not loaded else None,  # reps only count as a record without a load
        }
        # A record needs an earlier session with the same measure, like the PR badges in the history
        pr = [k for k, v in values.items() if v is not None and k in best and v > best[k]]
        for k, v in values.items():
            if v is not None:
                best[k] = max(best.get(k, 0.0), v)
        sessions.append(
            ProgressionSession(
                workout_id=workout_id,
                date=local_date(started_at),
                sets=len(sets),
                volume_kg=round(sum((w or 0.0) * (r or 0) for w, r in sets), 1),
                max_weight=top[0] if top else None,
                max_weight_reps=top[1] if top else None,
                e1rm=round(e1rm[0], 1) if e1rm else None,
                e1rm_set=f"{e1rm[1]:g} × {e1rm[2]}" if e1rm else None,
                max_reps=max_reps,
                pr=pr,
            )
        )
    weighted = sum(1 for s in sessions if s.max_weight) * 2 >= len(sessions) > 0
    return ExerciseProgression(exercise_id=exercise.id, name=exercise.name, weighted=weighted, sessions=sessions)
