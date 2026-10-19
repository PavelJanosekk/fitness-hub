import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class MuscleGroup(StrEnum):
    chest = "chest"
    back = "back"
    legs = "legs"
    shoulders = "shoulders"
    biceps = "biceps"
    triceps = "triceps"
    core = "core"
    full_body = "full_body"
    cardio = "cardio"


class SetType(StrEnum):
    normal = "normal"
    warmup = "warmup"
    drop = "drop"
    failure = "failure"


class WorkoutSource(StrEnum):
    manual = "manual"
    ai = "ai"
    strong_import = "strong_import"


class EndedBy(StrEnum):
    user = "user"
    auto_idle = "auto_idle"
    import_estimate = "import_estimate"


class Exercise(SQLModel, table=True):
    __tablename__ = "exercises"
    __table_args__ = (one_of("muscle_group", MuscleGroup),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    muscle_group: str
    equipment: str | None = None


class Workout(SQLModel, table=True):
    __tablename__ = "workouts"
    __table_args__ = (
        one_of("source", WorkoutSource),
        one_of("ended_by", EndedBy),
        # Re-importing the same Strong export must not duplicate workouts
        Index(
            "uq_workouts_strong_import",
            "started_at",
            "name",
            unique=True,
            postgresql_where=text("source = 'strong_import'"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # client-generated when created in the app
    name: str
    started_at: dt.datetime = Field(sa_type=AwareDateTime, index=True)
    ended_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
    ended_by: str | None = None
    source: str = WorkoutSource.manual
    notes: str | None = None


class WorkoutSet(SQLModel, table=True):
    __tablename__ = "workout_sets"
    __table_args__ = (
        one_of("set_type", SetType),
        CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name="rpe_range"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # client-generated when created in the app
    workout_id: uuid.UUID = Field(foreign_key="workouts.id", ondelete="CASCADE", index=True)
    exercise_id: int = Field(foreign_key="exercises.id", index=True)
    exercise_order: int  # position of the exercise within the workout (1-based)
    set_order: int  # position of the set within its exercise (1-based)
    set_type: str = SetType.normal
    weight_kg: float | None = None  # 0 = bodyweight; on bodyweight exercises a positive value is added load
    reps: int | None = None
    duration_s: int | None = None
    distance_m: float | None = None
    rpe: float | None = None
    completed: bool = True
    completed_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
    notes: str | None = None
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class WorkoutTemplate(SQLModel, table=True):
    """A saved workout plan the user manages by hand (E18); "Start from template" pre-fills a workout from it."""

    __tablename__ = "workout_templates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # client-generated when created in the app
    name: str
    position: int = 0
    # Ordered: [{"exercise_id": 1, "sets": [{"set_type": "normal", "weight_kg": 80.0, "reps": 8}, ...]}, ...]
    exercises: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
