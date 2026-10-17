import datetime as dt

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.gym import EndedBy, Exercise, Workout, WorkoutSet
from app.schemas.gym import SetRead, TemplateExercise, WorkoutRead, WorkoutSummary, WorkoutTemplate
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
        )
        for w, set_count, volume in rows
    ]


def list_templates(session: Session) -> list[WorkoutTemplate]:
    """The most recent workout of each distinct name, with its exercises in order."""
    latest = session.exec(
        select(Workout)
        .where(col(Workout.id).in_(select(WorkoutSet.workout_id)))
        .distinct(col(Workout.name))
        .order_by(col(Workout.name), col(Workout.started_at).desc())
    ).all()
    templates = []
    for workout in latest:
        exercises = session.exec(
            select(Exercise.id, Exercise.name, func.count(col(WorkoutSet.id)))
            .join(WorkoutSet, col(WorkoutSet.exercise_id) == Exercise.id)
            .where(WorkoutSet.workout_id == workout.id)
            .group_by(col(Exercise.id), col(Exercise.name))
            .order_by(func.min(WorkoutSet.exercise_order))
        ).all()
        templates.append(
            WorkoutTemplate(
                name=workout.name,
                last_workout_id=workout.id,
                last_started_at=workout.started_at,
                exercises=[TemplateExercise(exercise_id=i, name=n, set_count=c) for i, n, c in exercises],
            )
        )
    return sorted(templates, key=lambda t: t.last_started_at, reverse=True)
