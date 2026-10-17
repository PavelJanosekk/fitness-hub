import datetime as dt
import uuid

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.gym import MuscleGroup, SetType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    muscle_group: MuscleGroup
    equipment: str | None = None


class ExerciseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    muscle_group: MuscleGroup | None = None
    equipment: str | None = None


class ExerciseRead(ORMModel):
    id: int
    name: str
    muscle_group: MuscleGroup
    equipment: str | None


class SetIn(BaseModel):
    exercise_id: int
    exercise_order: int = Field(ge=1)
    set_order: int = Field(ge=1)
    set_type: SetType = SetType.normal
    weight_kg: float | None = None
    reps: int | None = Field(default=None, ge=0)
    duration_s: int | None = Field(default=None, ge=0)
    distance_m: float | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)
    completed: bool = True
    completed_at: AwareDatetime | None = None  # defaults to "now" when a set is first completed
    notes: str | None = None


class NestedSetIn(SetIn):
    id: uuid.UUID


class SetRead(ORMModel):
    id: uuid.UUID
    workout_id: uuid.UUID
    exercise_id: int
    exercise_order: int
    set_order: int
    set_type: SetType
    weight_kg: float | None
    reps: int | None
    duration_s: int | None
    distance_m: float | None
    rpe: float | None
    completed: bool
    completed_at: dt.datetime | None
    notes: str | None
    updated_at: dt.datetime


class WorkoutIn(BaseModel):
    """Upsert body. On update only the fields present in the payload are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    notes: str | None = None
    sets: list[NestedSetIn] | None = None


class WorkoutRead(ORMModel):
    id: uuid.UUID
    name: str
    started_at: dt.datetime
    ended_at: dt.datetime | None
    ended_by: str | None
    source: str
    notes: str | None
    sets: list[SetRead] = []


class WorkoutSummary(BaseModel):
    id: uuid.UUID
    name: str
    started_at: dt.datetime
    ended_at: dt.datetime | None
    ended_by: str | None
    source: str
    duration_min: int | None
    set_count: int
    total_volume_kg: float


class LastPerformanceSet(ORMModel):
    set_order: int
    set_type: SetType
    weight_kg: float | None
    reps: int | None
    duration_s: int | None
    distance_m: float | None
    rpe: float | None


class LastPerformance(BaseModel):
    exercise_id: int
    workout_id: uuid.UUID | None = None
    workout_started_at: dt.datetime | None = None
    sets: list[LastPerformanceSet] = []


class TemplateExercise(BaseModel):
    exercise_id: int
    name: str
    set_count: int


class WorkoutTemplate(BaseModel):
    name: str
    last_workout_id: uuid.UUID
    last_started_at: dt.datetime
    exercises: list[TemplateExercise]
