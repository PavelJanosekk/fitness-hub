import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.database import SessionDep
from app.models.gym import EndedBy, Exercise, MuscleGroup, Workout, WorkoutSet, WorkoutTemplate
from app.schemas.gym import (
    ExerciseCreate,
    ExerciseRead,
    ExerciseUpdate,
    LastPerformance,
    LastPerformanceSet,
    SetIn,
    SetRead,
    WorkoutIn,
    WorkoutRead,
    WorkoutSummary,
    WorkoutTemplateIn,
    WorkoutTemplateRead,
)
from app.services import workouts as svc
from app.services.strong_import import (
    DEFAULT_REMAP_RULES,
    ImportSummary,
    RemapRule,
    StrongImportError,
    import_strong_csv,
)
from app.timeutils import now_utc

router = APIRouter(prefix="/api", tags=["gym"])


# --- Exercises -------------------------------------------------------------------------------


@router.get("/exercises", response_model=list[ExerciseRead])
def list_exercises(session: SessionDep) -> list[Exercise]:
    return list(session.exec(select(Exercise).order_by(col(Exercise.name))).all())


@router.post("/exercises", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(body: ExerciseCreate, session: SessionDep) -> Exercise:
    exercise = Exercise(name=body.name.strip(), muscle_group=body.muscle_group, equipment=body.equipment)
    session.add(exercise)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Exercise with this name already exists") from None
    session.refresh(exercise)
    return exercise


@router.patch("/exercises/{exercise_id}", response_model=ExerciseRead)
def update_exercise(exercise_id: int, body: ExerciseUpdate, session: SessionDep) -> Exercise:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(exercise, field, value)
    session.add(exercise)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Exercise with this name already exists") from None
    session.refresh(exercise)
    return exercise


@router.get("/exercises/{exercise_id}/last-performance", response_model=LastPerformance)
def last_performance(exercise_id: int, session: SessionDep) -> LastPerformance:
    """Sets from the most recent finished workout containing this exercise (ghost values)."""
    if session.get(Exercise, exercise_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")
    workout = session.exec(
        select(Workout)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(WorkoutSet.exercise_id == exercise_id, col(WorkoutSet.completed), col(Workout.ended_at).is_not(None))
        .order_by(col(Workout.started_at).desc())
        .limit(1)
    ).first()
    if workout is None:
        return LastPerformance(exercise_id=exercise_id)
    sets = session.exec(
        select(WorkoutSet)
        .where(WorkoutSet.workout_id == workout.id, WorkoutSet.exercise_id == exercise_id, col(WorkoutSet.completed))
        .order_by(col(WorkoutSet.set_order))
    ).all()
    return LastPerformance(
        exercise_id=exercise_id,
        workout_id=workout.id,
        workout_started_at=workout.started_at,
        sets=[LastPerformanceSet.model_validate(s) for s in sets],
    )


# --- Workouts --------------------------------------------------------------------------------


@router.get("/workouts", response_model=list[WorkoutSummary])
def list_workouts(session: SessionDep, limit: int = Query(20, ge=1, le=200)) -> list[WorkoutSummary]:
    return svc.list_summaries(session, limit)


@router.get("/workouts/active", response_model=WorkoutRead | None)
def active_workout(session: SessionDep) -> WorkoutRead | None:
    svc.auto_finish_stale(session)
    workout = session.exec(
        select(Workout).where(col(Workout.ended_at).is_(None)).order_by(col(Workout.started_at).desc())
    ).first()
    return svc.read_workout(session, workout) if workout else None


@router.get("/workouts/templates", response_model=list[WorkoutTemplateRead])
def workout_templates(session: SessionDep) -> list[WorkoutTemplateRead]:
    return svc.list_templates(session)


@router.put("/workouts/templates/{template_id}", response_model=WorkoutTemplateRead)
def upsert_template(template_id: uuid.UUID, body: WorkoutTemplateIn, session: SessionDep) -> WorkoutTemplateRead:
    """Idempotent create-or-replace (client UUID); a new template goes to the end of the list."""
    unknown = {e.exercise_id for e in body.exercises} - set(
        session.exec(select(Exercise.id).where(col(Exercise.id).in_({e.exercise_id for e in body.exercises}))).all()
    )
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown exercise_id {sorted(unknown)}")
    template = session.get(WorkoutTemplate, template_id)
    if template is None:
        last = session.exec(select(func.max(WorkoutTemplate.position))).one()
        template = WorkoutTemplate(id=template_id, name="", position=(last + 1) if last is not None else 0)
    template.name = body.name.strip()
    template.exercises = [e.model_dump(mode="json") for e in body.exercises]
    template.updated_at = now_utc()
    session.add(template)
    session.commit()
    return svc.read_template(session, template)


@router.delete("/workouts/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: uuid.UUID, session: SessionDep) -> Response:
    template = session.get(WorkoutTemplate, template_id)
    if template is not None:
        session.delete(template)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workouts/{workout_id}", response_model=WorkoutRead)
def get_workout(workout_id: uuid.UUID, session: SessionDep) -> WorkoutRead:
    workout = session.get(Workout, workout_id)
    if workout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout not found")
    return svc.read_workout(session, workout)


@router.put("/workouts/{workout_id}", response_model=WorkoutRead)
def upsert_workout(workout_id: uuid.UUID, body: WorkoutIn, session: SessionDep) -> WorkoutRead:
    """Idempotent create-or-update (client UUID). On update only fields present in the body change."""
    fields = body.model_dump(exclude_unset=True, exclude={"sets"})
    workout = session.get(Workout, workout_id)
    if workout is None:
        if not body.name or not body.started_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "name and started_at are required to create")
        workout = Workout(id=workout_id, name=body.name, started_at=body.started_at)
    if "ended_at" in fields and fields["ended_at"] != workout.ended_at:
        workout.ended_by = EndedBy.user if fields["ended_at"] is not None else None
    for field, value in fields.items():
        setattr(workout, field, value)
    session.add(workout)
    for nested in body.sets or []:
        _apply_set(session, workout_id, nested.id, nested)
    session.commit()
    return svc.read_workout(session, workout)


@router.delete("/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: uuid.UUID, session: SessionDep) -> Response:
    workout = session.get(Workout, workout_id)
    if workout is not None:
        session.delete(workout)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/workouts/{workout_id}/sets/{set_id}", response_model=SetRead)
def upsert_set(workout_id: uuid.UUID, set_id: uuid.UUID, body: SetIn, session: SessionDep) -> WorkoutSet:
    if session.get(Workout, workout_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout not found")
    workout_set = _apply_set(session, workout_id, set_id, body)
    session.commit()
    session.refresh(workout_set)
    return workout_set


MAX_IMPORT_BYTES = 20 * 1024 * 1024


class RemapRuleIn(BaseModel):
    strong_name: str
    map_to: str
    muscle_group: MuscleGroup
    equipment: str | None = None
    marker_note: str | None = None
    all_workouts: bool = True


@router.post("/workouts/import-strong-csv", response_model=ImportSummary)
def import_strong(
    session: SessionDep,
    file: Annotated[UploadFile, File(description="CSV exported from the Strong app")],
    weight_unit: Annotated[Literal["kg", "lbs"], Form()] = "kg",
    exercise_map: Annotated[str | None, Form(description="JSON list of remap rules; replaces the defaults")] = None,
) -> ImportSummary:
    content = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    rules: tuple[RemapRule, ...] | list[RemapRule] = DEFAULT_REMAP_RULES
    if exercise_map:
        try:
            parsed = TypeAdapter(list[RemapRuleIn]).validate_python(json.loads(exercise_map))
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid exercise_map: {exc}") from None
        rules = [RemapRule(**rule.model_dump()) for rule in parsed]
    try:
        return import_strong_csv(session, content, weight_unit=weight_unit, rules=rules)
    except (StrongImportError, UnicodeDecodeError) as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.delete("/workouts/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set(set_id: uuid.UUID, session: SessionDep) -> Response:
    workout_set = session.get(WorkoutSet, set_id)
    if workout_set is not None:
        session.delete(workout_set)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _apply_set(session: Session, workout_id: uuid.UUID, set_id: uuid.UUID, body: SetIn) -> WorkoutSet:
    if session.get(Exercise, body.exercise_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown exercise_id {body.exercise_id}")
    workout_set = session.get(WorkoutSet, set_id)
    if workout_set is not None and workout_set.workout_id != workout_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Set belongs to another workout")
    data = body.model_dump(exclude={"id"})
    if not body.completed:
        data["completed_at"] = None
    elif data["completed_at"] is None:
        # Keep the original completion time on re-sends; stamp it the first time
        data["completed_at"] = workout_set.completed_at if workout_set and workout_set.completed_at else now_utc()
    if workout_set is None:
        workout_set = WorkoutSet(id=set_id, workout_id=workout_id, **data)
    else:
        for field, value in data.items():
            setattr(workout_set, field, value)
    workout_set.updated_at = now_utc()
    session.add(workout_set)
    return workout_set
