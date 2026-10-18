import datetime as dt

from pydantic import BaseModel, Field


class MetricUpsert(BaseModel):
    """Partial upsert: only non-null fields overwrite the stored day."""

    date: dt.date | None = None  # defaults to today in APP_TZ
    weight_kg: float | None = Field(default=None, gt=0, lt=400)
    calories_out: int | None = Field(default=None, ge=0)
    steps: int | None = Field(default=None, ge=0)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    notes: str | None = None


class WeekStats(BaseModel):
    week_start: dt.date  # Monday
    run_km: float
    runs: int
    gym_workouts: int
    gym_sets: dict[str, int]  # completed working sets per muscle group


class MetricDay(BaseModel):
    date: dt.date
    weight_kg: float | None = None
    weight_7d_avg: float | None = None
    calories_in: float | None = None  # from meal logs; null = nothing logged that day
    calories_in_7d_avg: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    calories_out: int | None = None
    steps: int | None = None
    sleep_hours: float | None = None
    notes: str | None = None


class EnergyItem(BaseModel):
    """One training session of the day and its net cost (on top of the base)."""

    source: str  # gym | strava | activity
    activity_type: str  # Strava sport type; gym workouts are "WeightTraining"
    name: str | None = None
    minutes: int
    distance_km: float | None = None
    method: str  # device: the watch's calories via Strava; estimate: MET or running cost x weight
    kcal: int | None = None


class EnergyDay(BaseModel):
    """Estimated expenditure of a day (services/energy.py). Null parts are unknown, listed in `missing`."""

    date: dt.date
    weight_kg: float | None = None
    bmr_kcal: int | None = None
    base_kcal: int | None = None  # BMR + digestion and everyday movement other than steps
    steps: int | None = None
    steps_counted: int | None = None  # minus steps taken during runs and walks, which the activity counts
    steps_kcal: int | None = None
    exercise_kcal: int | None = None
    active_kcal: int | None = None  # steps + training, the headline number; null without any weight
    total_kcal: int | None = None  # base + active; null without a profile (sex, birth year, height) or any weight
    missing: list[str] = []  # weight | profile | steps
    items: list[EnergyItem] = []
