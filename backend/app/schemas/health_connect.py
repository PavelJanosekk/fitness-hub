"""The subset of the Life Dashboard Companion webhook payload we use (unknown fields are ignored).

Reference: https://github.com/owen282000/life-dashboard-companion-app/blob/main/docs/webhook.md
"""

import datetime as dt

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HCSteps(_Lenient):
    # A raw record ...
    uuid: str | None = None
    source: str | None = None  # package name of the writing app
    count: float | None = None
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    # ... or a bucket, when "Data Resolution" is set for steps
    bucket_start: AwareDatetime | None = None
    bucket_end: AwareDatetime | None = None
    total: float | None = None
    complete: bool | None = None


class HCSleep(_Lenient):
    uuid: str | None = None
    source: str | None = None
    session_end_time: AwareDatetime
    duration_seconds: int = Field(ge=0)


class HCDailyTotal(_Lenient):
    date: dt.date
    steps: float | None = None


class HCDeleted(_Lenient):
    type: str
    uuid: str


class HCPayload(_Lenient):
    source: str  # health_connect | healthkit_ios | screen_time
    sequence: int | None = None
    test: bool = False
    backfill: bool = False
    steps: list[HCSteps] = Field(default_factory=list)
    sleep: list[HCSleep] = Field(default_factory=list)
    daily_totals: list[HCDailyTotal] = Field(default_factory=list)
    deleted_records: list[HCDeleted] = Field(default_factory=list)
