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
    description: str | None = None  # Strava description
    pace_sec_per_km: int | None = None
    pace: str | None = None  # "5:12" min/km
    rpe: int | None = None
    heat: bool = False
    # Stream metrics (null until the streams are fetched; see docs/SPEC.md §6.8)
    gap_sec_per_km: float | None = None
    ef_gap: float | None = None
    decoupling_pct: float | None = None
    pct_above_easy: float | None = None
    z4_minutes: float | None = None


class PlanDayRead(BaseModel):
    """A dated line of the day-by-day schedule in the plan ("Pá 16. Easy 5 km")."""

    model_config = ConfigDict(from_attributes=True)

    planned_date: dt.date
    text: str
    is_rest: bool
    km_min: float | None
    km_max: float | None


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
    days: list[PlanDayRead] = []  # empty when the plan has no day-by-day schedule for this week
    runs: list[ActivityRead] = []  # the week's actual runs, oldest first


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


class RunStat(BaseModel):
    """One run for the Běh → Grafy tab (E24): summary values plus its stream metrics when they exist."""

    id: int
    date: dt.date  # local day
    distance_km: float
    moving_s: int
    avg_hr: int | None
    heat: bool
    vdot: float | None  # Daniels estimate from distance and moving time; meaningful only for hard efforts
    pace_s_per_km: float | None
    gap_s_per_km: float | None
    hr_avg_steady: float | None
    ef_gap: float | None
    gap_at_easy_band_s_per_km: float | None
    pct_above_easy: float | None
    zone_seconds: dict[str, float] | None


class RunStats(BaseModel):
    lthr: int | None
    runs: list[RunStat]  # oldest first
