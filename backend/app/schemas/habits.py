import datetime as dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.habits import AutoRule, HabitFrequency, HabitSkill

HabitTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class HabitCreate(BaseModel):
    title: HabitTitle
    frequency: HabitFrequency = HabitFrequency.daily
    weekly_target: int = Field(default=1, ge=1, le=7)
    skill: HabitSkill | None = None
    points: int = Field(default=1, ge=1, le=3)
    is_bonus: bool = False
    auto_rule: AutoRule | None = None
    auto_threshold: float | None = Field(default=None, gt=0)
    start_date: dt.date | None = None  # defaults to today


class HabitUpdate(BaseModel):
    title: HabitTitle | None = None
    frequency: HabitFrequency | None = None
    weekly_target: int | None = Field(default=None, ge=1, le=7)
    skill: HabitSkill | None = None
    points: int | None = Field(default=None, ge=1, le=3)
    is_bonus: bool | None = None
    auto_rule: AutoRule | None = None
    auto_threshold: float | None = Field(default=None, gt=0)
    start_date: dt.date | None = None
    archived: bool | None = None  # true archives (history stays), false restores


class HabitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    frequency: HabitFrequency
    weekly_target: int
    skill: HabitSkill | None
    points: int
    is_bonus: bool
    auto_rule: AutoRule | None
    auto_threshold: float | None
    position: int
    start_date: dt.date
    archived_at: dt.datetime | None


class BoardHabit(HabitRead):
    done: list[dt.date]  # ticked by hand
    auto: dict[dt.date, str]  # completed by the auto rule: day -> what did it ("Běh 18,2 km")


class Board(BaseModel):
    today: dt.date
    start: dt.date
    habits: list[BoardHabit]


class DayState(BaseModel):
    done: bool


class DayStateRead(DayState):
    habit_id: int
    date: dt.date


class HabitOrder(BaseModel):
    ids: list[int]  # every habit id, in the new order
