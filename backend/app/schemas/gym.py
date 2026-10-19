import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.gym import MuscleGroup, SetType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Stripped before the length check, so "  " is rejected instead of saved as an empty name
ExerciseName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ProgressionSettings(BaseModel):
    """Per-exercise settings of the overload targets (E33); null = the default for the equipment."""

    rep_min: int | None = Field(default=None, ge=1, le=50)
    rep_max: int | None = Field(default=None, ge=1, le=50)
    weight_step: float | None = Field(default=None, gt=0, le=50)
    sets_max: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def _range_in_order(self) -> Self:
        if self.rep_min is not None and self.rep_max is not None and self.rep_max < self.rep_min:
            raise ValueError("rep_max must not be below rep_min")
        return self


class ExerciseCreate(ProgressionSettings):
    name: ExerciseName
    muscle_group: MuscleGroup
    equipment: str | None = None


class ExerciseUpdate(ProgressionSettings):
    name: ExerciseName | None = None
    muscle_group: MuscleGroup | None = None
    equipment: str | None = None


class ExerciseRead(ORMModel):
    id: int
    name: str
    muscle_group: MuscleGroup
    equipment: str | None
    rep_min: int | None
    rep_max: int | None
    weight_step: float | None
    sets_max: int | None


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
    # Editing a finished workout sends its whole set list: sets missing from `sets` are deleted
    replace_sets: bool = False


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


class TargetSet(BaseModel):
    set_type: SetType
    weight_kg: float | None
    reps: int | None
    changed: bool = False  # the set this session's step added or changed


class ProgressionTarget(BaseModel):
    """What to lift next time to keep progressing (E33): the last session's sets with one step applied."""

    # comeback / deload: lighter after a break or a stall; lighter: below the rep range; weight: + step at the top of
    # the range; sets: one more set; reps: +1 rep on the weakest set
    kind: Literal["comeback", "deload", "lighter", "weight", "sets", "reps"]
    weight_kg: float  # the working weight of the target (0 = no load)
    sets: list[TargetSet]  # every planned set in order, warm-ups and other weights as last time
    stalled_sessions: int  # sessions in a row at the last working weight without beating its best
    days_since: int  # since the last session
    rep_min: int
    rep_max: int
    weight_step: float
    sets_max: int


class LastPerformance(BaseModel):
    exercise_id: int
    workout_id: uuid.UUID | None = None
    workout_started_at: dt.datetime | None = None
    sets: list[LastPerformanceSet] = []
    target: ProgressionTarget | None = None


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


# --- Stats (Gym → Grafy) -----------------------------------------------------------------------


class StatsDay(BaseModel):
    date: dt.date
    workouts: int
    sets: int
    volume_kg: float


class StatsWeek(BaseModel):
    week_start: dt.date  # Monday
    workouts: int
    sets: dict[str, int]  # muscle group -> working sets
    volume_kg: dict[str, float]  # muscle group -> kg x reps
    muscles: dict[str, int]  # antagonist muscle (services/gym_stats.MUSCLES) -> working sets
    unclassified_sets: int  # working sets no antagonist muscle was derived for


class StatsExercise(BaseModel):
    exercise_id: int
    name: str
    muscle_group: str
    sessions: int
    last_date: dt.date


class GymStats(BaseModel):
    days: list[StatsDay]  # only days with a workout, oldest first
    weeks: list[StatsWeek]  # every week of the window, oldest first, the current one last
    exercises: list[StatsExercise]  # most sessions first


class ProgressionSession(BaseModel):
    workout_id: uuid.UUID
    date: dt.date
    sets: int
    volume_kg: float
    max_weight: float | None  # heaviest working set (> 0 kg)
    max_weight_reps: int | None
    e1rm: float | None  # best Epley estimate over sets up to 12 reps
    e1rm_set: str | None  # the set behind it, e.g. "80 × 5"  # noqa: RUF003
    max_reps: int | None  # most reps in one set
    pr: list[Literal["weight", "e1rm", "reps"]] = []  # beat every earlier session


class ExerciseProgression(BaseModel):
    exercise_id: int
    name: str
    weighted: bool  # most sessions used a load; otherwise reps are the measure (bodyweight)
    sessions: list[ProgressionSession]
