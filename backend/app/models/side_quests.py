import datetime as dt
from enum import StrEnum

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class SideQuestCategory(StrEnum):
    learn = "learn"  # Učení: how things work, history, ideas
    skill = "skill"  # Dovednosti: practical skills
    make = "make"  # Tvoření
    food = "food"  # Jídlo
    move = "move"  # Pohyb
    explore = "explore"  # Objevování: places, the town
    people = "people"  # Lidé
    self = "self"  # Sebepoznání: reflection, comfort zone
    home = "home"  # Domov
    trip = "trip"  # Výlet: nearby day trips


class SideQuestDuration(StrEnum):
    moment = "moment"  # Chvilka, up to an hour
    day = "day"  # 1 den
    weekend = "weekend"  # Víkend
    week = "week"  # Týden
    month = "month"  # Měsíc+


class SideQuest(SQLModel, table=True):
    """A side quest (docs/side-quests-module-spec.md, E45)."""

    __tablename__ = "side_quests"
    __table_args__ = (
        one_of("category", SideQuestCategory),
        one_of("duration", SideQuestDuration),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str
    category: str
    duration: str = SideQuestDuration.day
    note: str | None = None
    link: str | None = None
    travel_minutes: int | None = None  # one way by car from home (trips)
    distance_km: int | None = None
    active: bool = False  # "rozjeto": started, shown on top
    done_on: dt.date | None = None
    done_before_app: bool = False  # done before it was in the app: no date, no XP
    memory: str | None = None
    rating: int | None = None
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
