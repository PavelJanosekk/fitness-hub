import datetime as dt

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ActivityCreate(BaseModel):
    external_id: str | None = None
    source: str = "manual"
    start_time: AwareDatetime
    activity_type: str = "Run"
    distance_meters: float = Field(ge=0)
    duration_seconds: int = Field(gt=0)
    avg_hr: int | None = Field(default=None, gt=0, lt=260)
    max_hr: int | None = Field(default=None, gt=0, lt=260)
    calories: int | None = Field(default=None, ge=0)
    notes: str | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    source: str
    start_time: dt.datetime
    activity_type: str
    distance_meters: float
    duration_seconds: int
    avg_hr: int | None
    max_hr: int | None
    calories: int | None
    notes: str | None
    pace_sec_per_km: int | None = None
    pace: str | None = None  # "5:12" min/km


class PlanWeekRead(BaseModel):
    """A week of the synced plan next to what was actually run (Run page)."""

    week_start: dt.date
    week_end: dt.date
    block: str | None
    km_text: str | None
    km_min: float | None
    km_max: float | None
    long_run_text: str | None
    long_run_km_min: float | None
    long_run_km_max: float | None
    quality: str | None
    notes: str | None
    actual_km: float
    actual_runs: int
    longest_run_km: float | None


class PlanItemIn(BaseModel):
    id: int | None = None  # set to update an existing item
    planned_date: dt.date
    title: str = Field(min_length=1, max_length=200)
    target_distance_meters: float | None = Field(default=None, ge=0)
    target_pace_sec_per_km: int | None = Field(default=None, gt=0)
    description: str | None = None
    completed_activity_id: int | None = None


class PlanItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planned_date: dt.date
    title: str
    target_distance_meters: float | None
    target_pace_sec_per_km: int | None
    description: str | None
    completed_activity_id: int | None
    completed_activity: ActivityRead | None = None
