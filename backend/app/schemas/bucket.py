import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.bucket import BucketAutoRule, BucketCategory, BucketSeason

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
CountryCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{2}$")]


class BucketItemCreate(BaseModel):
    title: Title
    category: BucketCategory
    rarity: int = Field(default=1, ge=1, le=4)
    note: Text | None = None
    link: Text | None = None
    travel_time: Text | None = None
    season: BucketSeason | None = None
    cost: int | None = Field(default=None, ge=1, le=3)
    planned_for: dt.date | None = None
    year_goal: int | None = Field(default=None, ge=2000, le=2100)
    auto_rule: BucketAutoRule | None = None
    auto_exercise_id: int | None = None
    auto_threshold: float | None = Field(default=None, ge=0)
    country_codes: list[CountryCode] = []
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    steps: list[Title] = []


class BucketItemUpdate(BaseModel):
    """Only the fields sent change; an explicit null clears an optional field."""

    title: Title | None = None
    category: BucketCategory | None = None
    rarity: int | None = Field(default=None, ge=1, le=4)
    note: Text | None = None
    link: Text | None = None
    travel_time: Text | None = None
    season: BucketSeason | None = None
    cost: int | None = Field(default=None, ge=1, le=3)
    planned_for: dt.date | None = None
    done_on: dt.date | None = None
    done_before_app: bool | None = None
    memory: Text | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    year_goal: int | None = Field(default=None, ge=2000, le=2100)
    auto_rule: BucketAutoRule | None = None
    auto_exercise_id: int | None = None
    auto_threshold: float | None = Field(default=None, ge=0)
    country_codes: list[CountryCode] | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class StepCreate(BaseModel):
    title: Title


class StepUpdate(BaseModel):
    title: Title | None = None
    done_on: dt.date | None = None


class StepRead(BaseModel):
    id: int
    position: int
    title: str
    done_on: dt.date | None


class BucketItemRead(BaseModel):
    id: int
    title: str
    category: BucketCategory
    rarity: int
    note: str | None
    link: str | None
    travel_time: str | None
    season: BucketSeason | None
    cost: int | None
    planned_for: dt.date | None
    done_on: dt.date | None  # set by hand
    done_before_app: bool
    memory: str | None
    rating: int | None
    year_goal: int | None
    auto_rule: BucketAutoRule | None
    auto_exercise_id: int | None
    auto_exercise_name: str | None
    auto_threshold: float | None
    country_codes: list[str]
    lat: float | None
    lon: float | None
    created_at: dt.datetime
    steps: list[StepRead]
    # Derived
    done: bool
    completed_on: dt.date | None  # effective day (manual or auto); null when open or done before the app
    source: str | None  # manual | auto | before
    auto_label: str | None
    auto_progress: str | None
    xp: int  # what completing it paid (or will pay, while open)
    goal_xp: int


class CountryRead(BaseModel):
    code: str
    continent: str | None
    visited_on: dt.date | None
    on_map: bool
    items: list[str]


class CountryState(BaseModel):
    visited: bool
    visited_on: dt.date | None = None  # default today


class Rarity(BaseModel):
    level: int
    name: str
    xp: int


class YearQuest(BaseModel):
    year: int
    done: int
    target: int
    xp: int
    reached_on: dt.date | None


class BucketBoard(BaseModel):
    today: dt.date
    items: list[BucketItemRead]
    countries: list[CountryRead]
    continents: dict[str, dt.date | None]  # visited continent -> first day (null = before the app)
    continent_names: dict[str, str]
    country_continents: dict[str, str]  # every known ISO code -> continent (for the add-country list)
    rarities: list[Rarity]
    categories: dict[str, str]
    year_quest: YearQuest
    xp_total: int  # everything the bucket list has paid
    step_xp: int
    year_goal_share: float
