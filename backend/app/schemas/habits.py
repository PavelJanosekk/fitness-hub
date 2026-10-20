import datetime as dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.habits import AutoRule, HabitFrequency, HabitLogMode, HabitSkill

HabitTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
AbilityName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class HabitCreate(BaseModel):
    title: HabitTitle
    frequency: HabitFrequency = HabitFrequency.daily
    weekly_target: int = Field(default=1, ge=1, le=7)
    skill: HabitSkill | None = None
    points: int = Field(default=1, ge=1, le=3)
    is_bonus: bool = False
    auto_rule: AutoRule | None = None
    auto_threshold: float | None = Field(default=None, gt=0)
    log_mode: HabitLogMode = HabitLogMode.check
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
    log_mode: HabitLogMode | None = None
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
    log_mode: HabitLogMode
    position: int
    start_date: dt.date
    archived_at: dt.datetime | None


class HabitEntry(BaseModel):
    note: str | None = None
    rating: int | None = None
    ability_id: int | None = None
    ability: str | None = None  # the dovednost's name


class BoardHabit(HabitRead):
    done: list[dt.date]  # ticked by hand
    auto: dict[dt.date, str]  # completed by the auto rule: day -> what did it ("Běh 18,2 km")
    entries: dict[dt.date, HabitEntry] = {}  # ticked days with a note, stars or a dovednost (E37)


class AbilityBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon: str | None


class Board(BaseModel):
    today: dt.date
    start: dt.date
    habits: list[BoardHabit]
    paused: list[dt.date] = []  # days that count for nothing (E22 pause)
    forgiven: list[dt.date] = []  # the forgiven missed day of each month
    abilities: list[AbilityBrief] = []  # every dovednost, most recently used first (for the entry sheet)


class DayState(BaseModel):
    """A tick, optionally with its entry. Entry fields left out keep what is stored; null clears them."""

    done: bool
    note: Note | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    ability: AbilityName | None = None  # a name: found ignoring case / diacritics, or created


class DayStateRead(BaseModel):
    habit_id: int
    date: dt.date
    done: bool
    entry: HabitEntry | None = None


class AbilityEntryRead(BaseModel):
    date: dt.date
    habit_id: int
    habit_title: str
    note: str | None
    rating: int | None


class AbilityRead(AbilityBrief):
    count: int
    first_on: dt.date | None
    last_on: dt.date | None
    level: int
    level_name: str
    next_level_at: int | None  # entries needed for the next level
    last_note: str | None


class AbilityDetail(AbilityRead):
    entries: list[AbilityEntryRead]  # newest first


class AbilityUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] | None = None
    icon: Annotated[str, StringConstraints(strip_whitespace=True, max_length=8)] | None = None


class AbilityMerge(BaseModel):
    into_id: int


class HabitOrder(BaseModel):
    ids: list[int]  # every habit id, in the new order
