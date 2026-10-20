import datetime as dt
from enum import StrEnum

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class BucketCategory(StrEnum):
    travel = "travel"  # Cestování: countries and far regions
    expedition = "expedition"  # Výpravy: mountains, lakes, multi-day trips by car
    experience = "experience"  # Zážitky
    adrenaline = "adrenaline"  # Adrenalin
    sport = "sport"  # Sport & pohyb
    skill = "skill"  # Dovednosti
    food = "food"  # Jídlo & pití
    wellbeing = "wellbeing"  # Tělo & mysl


class BucketSeason(StrEnum):
    summer = "summer"
    winter = "winter"


class BucketAutoRule(StrEnum):
    """App data that completes an item by itself; evaluated live, never stored (like habit auto rules)."""

    marathon = "marathon"  # a run >= 42 km, or >= 40 km on a race day
    exercise = "exercise"  # a completed set of `auto_exercise_id`
    hike = "hike"  # a hike / walk with elevation gain >= threshold (default 1 000 m)
    continents = "continents"  # visited continents >= threshold (default 7)


class BucketItem(SQLModel, table=True):
    """A bucket-list item (docs/bucket-list-module-spec.md, E36)."""

    __tablename__ = "bucket_items"
    __table_args__ = (
        one_of("category", BucketCategory),
        one_of("season", BucketSeason),
        one_of("auto_rule", BucketAutoRule),
        CheckConstraint("rarity BETWEEN 1 AND 4", name="rarity_range"),
        CheckConstraint("cost IS NULL OR cost BETWEEN 1 AND 3", name="cost_range"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str
    category: str
    rarity: int = 1  # 1 Běžná, 2 Vzácná, 3 Epická, 4 Legendární
    note: str | None = None
    link: str | None = None
    travel_time: str | None = None  # free text from home, e.g. "3 h 15 min"
    season: str | None = None
    cost: int | None = None  # 1-3 (€ to €€€)
    planned_for: dt.date | None = None
    done_on: dt.date | None = None  # completed by hand (an auto rule can complete it without this)
    done_before_app: bool = False  # done before it was on the list in the app: no date, no XP
    memory: str | None = None
    rating: int | None = None
    year_goal: int | None = None  # starred as a goal for this calendar year
    auto_rule: str | None = None
    auto_exercise_id: int | None = Field(default=None, foreign_key="exercises.id", ondelete="SET NULL")
    auto_threshold: float | None = None
    country_codes: list[str] = Field(default_factory=list, sa_type=JSONB)  # ISO 3166-1 alpha-2, for the world map
    lat: float | None = None
    lon: float | None = None
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class BucketStep(SQLModel, table=True):
    """A milestone of a bigger item (Naučit se rusky: A1, A2, ...); each pays a little XP."""

    __tablename__ = "bucket_steps"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="bucket_items.id", ondelete="CASCADE", index=True)
    position: int = 0
    title: str
    done_on: dt.date | None = None


class VisitedCountry(SQLModel, table=True):
    """A country marked on the world map; countries of completed items count without a row."""

    __tablename__ = "visited_countries"

    code: str = Field(primary_key=True, max_length=2)
    visited_on: dt.date | None = None  # null = before the app (no date known)
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
