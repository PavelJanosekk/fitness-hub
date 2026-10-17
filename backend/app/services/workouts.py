import datetime as dt
import itertools
import uuid
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.gym import EndedBy, Exercise, Workout, WorkoutSet, WorkoutTemplate
from app.schemas.gym import (
    PersonalRecord,
    SetRead,
    TemplateExercise,
    WorkoutRead,
    WorkoutSummary,
    WorkoutTemplateRead,
)
from app.timeutils import now_utc

AUTO_FINISH_IDLE = dt.timedelta(hours=2)
AUTO_FINISH_GRACE = dt.timedelta(minutes=2)  # the last set still took a moment after it was ticked off


def auto_finish_stale(session: Session, now: dt.datetime | None = None) -> int:
    """Close active workouts with no newly completed set for 2 h (docs/SPEC.md §6.3, E9)."""
    now = now or now_utc()
    last_completed = (
        select(WorkoutSet.workout_id, func.max(WorkoutSet.completed_at).label("last_at"))
        .group_by(col(WorkoutSet.workout_id))
        .subquery()
    )
    rows = session.exec(
        select(Workout, last_completed.c.last_at)
        .outerjoin(last_completed, last_completed.c.workout_id == Workout.id)
        .where(col(Workout.ended_at).is_(None))
    ).all()
    closed = 0
    for workout, last_at in rows:
        activity_at = last_at or workout.started_at
        if now - activity_at < AUTO_FINISH_IDLE:
            continue
        workout.ended_at = last_at + AUTO_FINISH_GRACE if last_at else workout.started_at
        workout.ended_by = EndedBy.auto_idle
        session.add(workout)
        closed += 1
    if closed:
        session.commit()
    return closed


def read_workout(session: Session, workout: Workout) -> WorkoutRead:
    sets = session.exec(
        select(WorkoutSet)
        .where(WorkoutSet.workout_id == workout.id)
        .order_by(col(WorkoutSet.exercise_order), col(WorkoutSet.set_order))
    ).all()
    return WorkoutRead.model_validate(workout).model_copy(update={"sets": [SetRead.model_validate(s) for s in sets]})


# Volume and set counts only include completed, non-warm-up sets
WORKING_SET = col(WorkoutSet.completed) & (col(WorkoutSet.set_type) != "warmup")


def list_summaries(session: Session, limit: int) -> list[WorkoutSummary]:
    working = WORKING_SET
    rows = session.exec(
        select(
            Workout,
            func.count(col(WorkoutSet.id)).filter(working),
            func.coalesce(func.sum(col(WorkoutSet.weight_kg) * col(WorkoutSet.reps)).filter(working), 0.0),
        )
        .outerjoin(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .group_by(col(Workout.id))
        .order_by(col(Workout.started_at).desc())
        .limit(limit)
    ).all()
    records = personal_records(session)
    return [
        WorkoutSummary(
            id=w.id,
            name=w.name,
            started_at=w.started_at,
            ended_at=w.ended_at,
            ended_by=w.ended_by,
            source=w.source,
            duration_min=round((w.ended_at - w.started_at).total_seconds() / 60) if w.ended_at else None,
            set_count=set_count,
            total_volume_kg=round(float(volume), 1),
            prs=records.get(w.id, []),
        )
        for w, set_count, volume in rows
    ]


def read_template(session: Session, template: WorkoutTemplate) -> WorkoutTemplateRead:
    ids = {e["exercise_id"] for e in template.exercises}
    names = dict(session.exec(select(Exercise.id, Exercise.name).where(col(Exercise.id).in_(ids))).all()) if ids else {}
    return WorkoutTemplateRead(
        id=template.id,
        name=template.name,
        position=template.position,
        exercises=[
            TemplateExercise(exercise_id=e["exercise_id"], name=names.get(e["exercise_id"], "?"), sets=e["sets"])
            for e in template.exercises
        ],
    )


def list_templates(session: Session) -> list[WorkoutTemplateRead]:
    templates = session.exec(select(WorkoutTemplate).order_by(col(WorkoutTemplate.position), col(WorkoutTemplate.name)))
    return [read_template(session, t) for t in templates]


E1RM_MAX_REPS = 12  # Epley gets unreliable for long sets


def _epley(weight: float, reps: int) -> float:
    return weight * (1 + reps / 30)


def personal_records(session: Session) -> dict[uuid.UUID, list[PersonalRecord]]:
    """Per workout, the exercises where it beat everything lifted in earlier workouts.

    A record needs an earlier workout with the same kind of set, so the first time an exercise is done is never one.
    Per exercise one record is reported: heaviest weight, else best estimated 1RM (more reps at a known weight), else
    most reps on a bodyweight exercise. Warm-ups don't count.
    """
    rows = session.exec(
        select(
            Workout.id,
            WorkoutSet.exercise_id,
            Exercise.name,
            WorkoutSet.weight_kg,
            WorkoutSet.reps,
        )
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .where(WORKING_SET, col(WorkoutSet.reps) >= 1)
        .order_by(col(Workout.started_at), col(Workout.id))
    ).all()
    best: dict[int, dict[str, float]] = {}  # exercise_id -> best weight / e1rm / reps from earlier workouts
    result: dict[uuid.UUID, list[PersonalRecord]] = {}
    for workout_id, group in itertools.groupby(rows, key=lambda r: r[0]):
        today: dict[int, dict[str, Any]] = {}
        for _, exercise_id, name, weight, reps in group:
            entry = today.setdefault(exercise_id, {"name": name, "weight": (0.0, 0), "e1rm": (0.0, 0), "reps": 0})
            if weight and weight > 0:
                entry["weight"] = max(entry["weight"], (weight, reps))
                if reps <= E1RM_MAX_REPS:
                    entry["e1rm"] = max(entry["e1rm"], (_epley(weight, reps), reps))
            else:
                entry["reps"] = max(entry["reps"], reps)
        for exercise_id, entry in today.items():
            before = best.get(exercise_id, {})
            record: PersonalRecord | None = None
            if entry["weight"][0] > before.get("weight", float("inf")):
                record = PersonalRecord(
                    exercise_id=exercise_id,
                    name=entry["name"],
                    kind="weight",
                    value=entry["weight"][0],
                    reps=entry["weight"][1],
                )
            elif entry["e1rm"][0] > before.get("e1rm", float("inf")):
                record = PersonalRecord(
                    exercise_id=exercise_id,
                    name=entry["name"],
                    kind="e1rm",
                    value=round(entry["e1rm"][0], 1),
                    reps=entry["e1rm"][1],
                )
            elif entry["reps"] > before.get("reps", float("inf")):
                record = PersonalRecord(exercise_id=exercise_id, name=entry["name"], kind="reps", value=entry["reps"])
            if record:
                result.setdefault(workout_id, []).append(record)
            merged = best.setdefault(exercise_id, {})
            for key, value in (("weight", entry["weight"][0]), ("e1rm", entry["e1rm"][0]), ("reps", entry["reps"])):
                if value > 0:
                    merged[key] = max(merged.get(key, 0.0), value)
    return result
