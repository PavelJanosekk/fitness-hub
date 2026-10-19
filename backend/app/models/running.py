import datetime as dt
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
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
    elapsed_seconds: int | None = None  # including pauses
    elevation_gain_m: float | None = None  # Strava total_elevation_gain
    avg_cadence: float | None = None  # steps per minute (Strava reports runs per leg; stored doubled)
    avg_hr: int | None = None
    max_hr: int | None = None
    calories: int | None = None
    notes: str | None = None  # Strava activity name ("heat" in it marks a hot-weather run)
    description: str | None = Field(default=None, sa_type=Text)  # Strava description: fueling log, pain 0-10
    rpe: int | None = None  # Strava "perceived exertion" 1-10


class ActivityStream(SQLModel, table=True):
    """Raw per-second Strava streams of a run, kept so metrics can be recomputed (e.g. after an LTHR retest)."""

    __tablename__ = "activity_streams"

    activity_id: int = Field(primary_key=True, foreign_key="activities.id", ondelete="CASCADE")
    data: dict[str, Any] = Field(sa_type=JSONB(none_as_null=True))
    keys: str | None = None  # the stream keys requested; refetched when STREAM_KEYS gains new ones
    fetched_at: dt.datetime = Field(sa_type=AwareDateTime)


class ActivityMetrics(SQLModel, table=True):
    """Stream-derived metrics of a run (port of RunningCoach scripts/metrics.py)."""

    __tablename__ = "activity_metrics"

    activity_id: int = Field(primary_key=True, foreign_key="activities.id", ondelete="CASCADE")
    computed_at: dt.datetime = Field(sa_type=AwareDateTime)
    lthr: int | None  # the LTHR the zones were computed with (None: zone fields empty)
    moving_seconds: int
    has_heartrate: bool
    pace_s_per_km: float | None = None
    gap_s_per_km: float | None = None  # grade-adjusted (Minetti)
    pace_first10_s_per_km: float | None = None
    hr_avg_steady: float | None = None  # after the first 10 minutes
    ef_gap: float | None = None  # GAP metres per minute per heartbeat
    decoupling_pct: float | None = None  # GAP/HR first vs second half of the steady part
    gap_at_easy_band_s_per_km: float | None = None  # GAP while HR was in the easy comparison band (143-150)
    zone_seconds: dict[str, float] | None = Field(default=None, sa_type=JSONB(none_as_null=True))
    pct_above_easy: float | None = None  # share of moving time above Z2
    pct_above_steady: float | None = None  # share of moving time in Z4-Z5


class TrainingPlanItem(SQLModel, table=True):
    __tablename__ = "training_plan_items"

    id: int | None = Field(default=None, primary_key=True)
    planned_date: dt.date = Field(index=True)
    title: str
    target_distance_meters: float | None = None
    target_pace_sec_per_km: int | None = None
    description: str | None = None
    completed_activity_id: int | None = Field(default=None, foreign_key="activities.id", ondelete="SET NULL")
