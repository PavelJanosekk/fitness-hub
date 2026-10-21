import datetime as dt
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.side_quests import SideQuestCategory, SideQuestDuration

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class SideQuestCreate(BaseModel):
    title: Title
    category: SideQuestCategory
    duration: SideQuestDuration = SideQuestDuration.day
    note: Text | None = None
    link: Text | None = None
    travel_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    distance_km: int | None = Field(default=None, ge=0, le=5000)


class SideQuestUpdate(BaseModel):
    """Only the fields sent change; an explicit null clears an optional field."""

    title: Title | None = None
    category: SideQuestCategory | None = None
    duration: SideQuestDuration | None = None
    note: Text | None = None
    link: Text | None = None
    travel_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    distance_km: int | None = Field(default=None, ge=0, le=5000)
    active: bool | None = None
    done_on: dt.date | None = None
    done_before_app: bool | None = None
    memory: Text | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


class SideQuestRead(BaseModel):
    id: int
    title: str
    category: SideQuestCategory
    duration: SideQuestDuration
    note: str | None
    link: str | None
    travel_minutes: int | None
    distance_km: int | None
    active: bool
    done_on: dt.date | None
    done_before_app: bool
    memory: str | None
    rating: int | None
    created_at: dt.datetime
    done: bool
    xp: int  # paid when done, else what completing it today would pay


class DurationInfo(BaseModel):
    key: SideQuestDuration
    name: str
    xp: int


class CategoryInfo(BaseModel):
    key: SideQuestCategory
    name: str
    skill: str


class WeekQuest(BaseModel):
    """This week's "1 side quest" (E45): `active` false before it starts (SIDE_QUEST_FROM)."""

    week_start: dt.date
    active: bool
    done: int
    xp: int
    titles: list[str]  # completed this week


class SideQuestBoard(BaseModel):
    today: dt.date
    items: list[SideQuestRead]
    durations: list[DurationInfo]
    categories: list[CategoryInfo]
    week: WeekQuest
    xp_total: int
