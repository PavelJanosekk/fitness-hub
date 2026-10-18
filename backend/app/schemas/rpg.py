import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class NextTitle(BaseModel):
    level: int
    title: str


class Skill(BaseModel):
    key: str
    name: str
    source: str  # where its XP comes from, for the UI
    xp: int
    level: int
    level_start_xp: int
    next_level_xp: int
    idle_days: int  # unpaused days without XP (0 for a skill never trained)
    rusting: bool  # idle >= 14 days
    losing: bool  # idle >= 21 days: loses XP every week


class Character(BaseModel):
    level: int
    title: str
    next_title: NextTitle | None
    xp_total: int
    level_start_xp: int  # total XP where the current level begins
    next_level_xp: int  # total XP where the next level begins
    today_xp: int  # net XP of today (gains so far; today has no penalties yet)
    week_xp: int  # net XP since Monday
    multiplier: float  # routine-week streak multiplier in effect this week
    week_streak: int  # finished qualifying weeks in a row
    forgiven_this_month: dt.date | None  # the month's forgiven day, once used
    paused: bool
    skills: list[Skill] = []


class XpEntryRead(BaseModel):
    amount: int
    kind: str
    text: str


class XpDay(BaseModel):
    date: dt.date
    total: int  # net XP of the day
    entries: list[XpEntryRead]


class PauseIn(BaseModel):
    start_date: dt.date
    end_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=200)


class PauseUpdate(BaseModel):
    end_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=200)


class PauseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_date: dt.date
    end_date: dt.date | None
    note: str | None
