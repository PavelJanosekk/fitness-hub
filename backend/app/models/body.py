import datetime as dt
from enum import StrEnum

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class HealthSource(StrEnum):
    apple_health = "apple_health"
    samsung_health = "samsung_health"
    manual = "manual"


class HealthRecordKind(StrEnum):
    steps = "steps"
    sleep = "sleep"


class DailyMetricKind(StrEnum):
    steps_total = "steps_total"
    steps_untimed = "steps_untimed"  # steps of records too long to place in buckets (whole-day records)
    sleep_minutes = "sleep_minutes"
    resting_hr = "resting_hr"
    weight_kg = "weight_kg"


class DailyMetric(SQLModel, table=True):
    """One row per local day. `steps` and `sleep_hours` are merged values kept up to date by health_ingest."""

    __tablename__ = "daily_metrics"

    date: dt.date = Field(primary_key=True)
    weight_kg: float | None = None
    calories_out: int | None = None
    steps: int | None = None
    sleep_hours: float | None = None
    notes: str | None = None


class HealthSourceStatus(SQLModel, table=True):
    """When each webhook source last delivered data, so a broken Shortcut or forwarder gets noticed."""

    __tablename__ = "health_source_status"
    __table_args__ = (one_of("source", HealthSource),)

    source: str = Field(primary_key=True)
    last_received_at: dt.datetime = Field(sa_type=AwareDateTime)
    last_day: dt.date  # newest day in the last payload


class StepBucket(SQLModel, table=True):
    """Interval step data of one source, spread over 15-minute buckets."""

    __tablename__ = "step_buckets"
    __table_args__ = (one_of("source", HealthSource),)

    source: str = Field(primary_key=True)
    bucket_start: dt.datetime = Field(primary_key=True, sa_type=AwareDateTime)
    # Float: samples are split proportionally across buckets, rounding happens on the day total
    steps: float


class DailySourceMetric(SQLModel, table=True):
    """Per-source daily values (totals when a source has no intervals, sleep, resting HR, ...)."""

    __tablename__ = "daily_source_metrics"
    __table_args__ = (one_of("source", HealthSource), one_of("metric", DailyMetricKind))

    date: dt.date = Field(primary_key=True)
    source: str = Field(primary_key=True)
    metric: str = Field(primary_key=True)
    value: float
    # Ordering of incremental senders (Health Connect forwarder): the highest sequence wins per date
    sequence: int | None = None
    received_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class HealthRecord(SQLModel, table=True):
    """Raw records from incremental senders, keyed by their stable id; buckets are rebuilt from these."""

    __tablename__ = "health_records"
    __table_args__ = (
        one_of("source", HealthSource),
        one_of("kind", HealthRecordKind),
        Index("ix_health_records_source_kind_start", "source", "kind", "start"),
    )

    kind: str = Field(primary_key=True)
    uuid: str = Field(primary_key=True)  # Health Connect record id, or "bucket:<start>" for complete buckets
    source: str
    origin: str | None = None  # package name of the app that wrote the record (e.g. Samsung Health)
    start: dt.datetime = Field(sa_type=AwareDateTime)
    end: dt.datetime = Field(sa_type=AwareDateTime)
    value: float  # steps: count; sleep: seconds
    received_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
