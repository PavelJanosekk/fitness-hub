import datetime as dt
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.models.body import DailyMetricKind


class _Interval(BaseModel):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class StepSample(_Interval):
    count: float = Field(ge=0)


class SleepSession(_Interval):
    pass


class DailyValue(BaseModel):
    date: dt.date
    metric: DailyMetricKind
    value: float = Field(ge=0)


class HealthPush(BaseModel):
    """Complete data of one source for each listed day; it replaces what was stored for those days."""

    source: Literal["apple_health", "samsung_health"]
    days: list[dt.date] = Field(min_length=1, max_length=31)
    steps: list[StepSample] = Field(default_factory=list, max_length=20000)
    daily: list[DailyValue] = Field(default_factory=list, max_length=500)
    sleep_sessions: list[SleepSession] = Field(default_factory=list, max_length=500)


class DayMerge(BaseModel):
    date: dt.date
    steps: int | None
    steps_method: Literal["manual", "buckets", "max_daily", "single_source"] | None
    sleep_hours: float | None


class BucketRow(BaseModel):
    start: dt.datetime
    merged: float
    per_source: dict[str, float]


class StepsBreakdown(DayMerge):
    source_totals: dict[str, float]
    buckets: list[BucketRow]
