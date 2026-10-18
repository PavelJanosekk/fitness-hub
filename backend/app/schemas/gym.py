import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.models.gym import MuscleGroup, SetType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Stripped before the length check, so "  " is rejected instead of saved as an empty name
ExerciseName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ExerciseCreate(BaseModel):
    name: ExerciseName
    muscle_group: MuscleGroup
    equipment: str | None = None


class ExerciseUpdate(BaseModel):
    name: ExerciseName | None = None
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


class PersonalRecord(BaseModel):
    """A best the workout set for one exercise: heaviest weight, estimated 1RM, or most reps (bodyweight)."""

    exercise_id: int
    name: str
    kind: Literal["weight", "e1rm", "reps"]
    value: float
    reps: int | None = None  # reps of the record set (weight and e1rm)


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
    prs: list[PersonalRecord] = []


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


class TemplateSet(BaseModel):
    set_type: SetType = SetType.normal
    weight_kg: float | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)


class TemplateExerciseIn(BaseModel):
    exercise_id: int
    sets: list[TemplateSet] = Field(min_length=1, max_length=20)


class TemplateExercise(TemplateExerciseIn):
    name: str


class WorkoutTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exercises: list[TemplateExerciseIn] = Field(max_length=30)


class WorkoutTemplateRead(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    exercises: list[TemplateExercise]
