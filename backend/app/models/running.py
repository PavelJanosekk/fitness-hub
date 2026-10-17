import datetime as dt

from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime


class Activity(SQLModel, table=True):
    """Runs and other cardio. Strava is the only automatic source (docs/SPEC.md §6.4)."""

    __tablename__ = "activities"

    id: int | None = Field(default=None, primary_key=True)
    external_id: str | None = Field(default=None, unique=True, index=True)  # e.g. "strava:1234567890"
    source: str = "manual"
    start_time: dt.datetime = Field(sa_type=AwareDateTime, index=True)
    activity_type: str  # Run, Walk, Ride, ...
    distance_meters: float
    duration_seconds: int  # moving time
    avg_hr: int | None = None
    max_hr: int | None = None
    calories: int | None = None
    notes: str | None = None


class TrainingPlanItem(SQLModel, table=True):
    __tablename__ = "training_plan_items"

    id: int | None = Field(default=None, primary_key=True)
    planned_date: dt.date = Field(index=True)
    title: str
    target_distance_meters: float | None = None
    target_pace_sec_per_km: int | None = None
    description: str | None = None
    completed_activity_id: int | None = Field(default=None, foreign_key="activities.id", ondelete="SET NULL")
