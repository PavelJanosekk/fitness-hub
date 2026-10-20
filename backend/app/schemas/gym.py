import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.gym import MuscleGroup, ProgressionStrategy, SetRole, SetType


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
    target_rir: int | None = Field(default=None, ge=0, le=3)
    strategy: ProgressionStrategy | None = None

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
    target_rir: int | None
    strategy: ProgressionStrategy | None


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
    # The target the set was planned with and its role (E35); `unusual` keeps the exercise's session in this workout
    # out of the progression
    planned_weight_kg: float | None = None
    planned_reps: int | None = Field(default=None, ge=0)
    role: SetRole | None = None
    unusual: bool = False


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
    planned_weight_kg: float | None
    planned_reps: int | None
    role: SetRole | None
    unusual: bool
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
    planned_weight_kg: float | None
    planned_reps: int | None
    role: SetRole | None


class TargetSet(BaseModel):
    set_type: SetType
    weight_kg: float | None
    reps: int | None
    role: SetRole | None  # None: outside the progression (warm-up, drop set, a set at another weight)
    changed: bool = False  # differs from the last comparable session
    priority: bool = False  # the set this session's step pushes (+1 rep, or the added set)


TargetReason = Literal[
    "plus_rep",  # +1 rep on the priority set
    "weight_up",  # the block met the conditions for more weight
    "return_up",  # ... to a weight it has lifted before
    "add_set",  # opt-in volume progression (sets_max)
    "hold",  # the last target was missed by a rep: repeat it
    "check_drop",  # a set fell well short: repeat the target, look at the context
    "lower",  # a drop twice in a row: one weight step lighter
    "comeback",  # a break of more than COMEBACK_DAYS: ~10 % lighter
    "no_data",  # no comparable session: repeat the last known values
]
TargetWarning = Literal[
    "stall",  # several sessions at one weight without a better total
    "decline",  # the block total fell several sessions in a row
    "big_jump",  # the first set at the new weight is expected below the rep range
    "low_confidence",  # fewer than 2 comparable sessions, or the strategy changed since
    "last_not_comparable",  # the last session was unusual or not lifted as planned: the target ignores it
]


class TargetBlock(BaseModel):
    role: SetRole
    reason: TargetReason
    weight_kg: float  # the block's target weight (0 = no load)


class TargetSuggestion(BaseModel):
    """An easier variant for the current workout only (E35): the plan stays as it is."""

    kind: Literal["deload", "lighter"]
    sets: list[TargetSet]


class ProgressionTarget(BaseModel):
    """What to lift next time to keep progressing (E35): the last comparable session with one step per block."""

    strategy: ProgressionStrategy
    sets: list[TargetSet]  # every planned set in order; warm-ups and other sets as last time
    blocks: list[TargetBlock]  # straight: one; top_backoff: top, then back-off
    warnings: list[TargetWarning] = []
    suggestion: TargetSuggestion | None = None
    fatigue_from: str | None = None  # on a drop: an earlier exercise of the same muscle group in that workout
    stalled_sessions: int  # sessions in a row at the first block's weight without beating its best total
    days_since: int  # since the last session of the exercise
    rep_min: int
    rep_max: int
    weight_step: float
    sets_max: int | None
    target_rir: int


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
