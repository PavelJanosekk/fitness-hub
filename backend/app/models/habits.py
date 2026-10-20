import datetime as dt
from enum import StrEnum

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class HabitFrequency(StrEnum):
    daily = "daily"
    weekly = "weekly"


class HabitSkill(StrEnum):
    """Life area of a habit: its colour now, the RPG skill that earns its XP later (E20)."""

    body = "body"
    nutrition = "nutrition"
    home = "home"
    discipline = "discipline"
    mind = "mind"


class AutoRule(StrEnum):
    """Data the app already has that completes a habit by itself; evaluated live, never stored."""

    gym_workout = "gym_workout"  # a workout with at least one completed set
    activity = "activity"  # a run, ride, swim, ... (walks excluded)
    gym_or_activity = "gym_or_activity"
    steps = "steps"  # merged daily steps >= threshold
    sleep = "sleep"  # sleep hours >= threshold
    weight_logged = "weight_logged"
    protein = "protein"  # protein >= threshold, else >= the nutrition profile target


class HabitLogMode(StrEnum):
    """What ticking a habit asks for (E37, docs/habit-journal-module-spec.md)."""

    check = "check"  # a plain tick
    note = "note"  # a note and an optional dovednost
    review = "review"  # stars, a note and an optional dovednost


class Habit(SQLModel, table=True):
    """A daily or weekly routine item (docs/habits-module-spec.md)."""

    __tablename__ = "habits"
    __table_args__ = (
        one_of("frequency", HabitFrequency),
        one_of("skill", HabitSkill),
        one_of("auto_rule", AutoRule),
        one_of("log_mode", HabitLogMode),
        CheckConstraint("points BETWEEN 1 AND 3", name="points_range"),
        CheckConstraint("weekly_target BETWEEN 1 AND 7", name="weekly_target_range"),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str
    frequency: str = HabitFrequency.daily
    weekly_target: int = 1  # weekly habits: days per ISO week that complete it
    skill: str | None = None
    points: int = 1
    is_bonus: bool = False  # adds points but is left out of the day's maximum and percentage
    auto_rule: str | None = None
    auto_threshold: float | None = None  # steps / sleep hours / protein grams; null = the rule's default
    log_mode: str = HabitLogMode.check
    position: int = 0
    start_date: dt.date  # days (weeks) before it are not counted as missed
    archived_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class Ability(SQLModel, table=True):
    """A dovednost the hero picked up, named in a habit entry (E37); counts and dates come from the entries."""

    __tablename__ = "abilities"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    key: str = Field(unique=True)  # the name without case, diacritics and extra spaces (services/abilities.py)
    icon: str | None = None  # an emoji
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class HabitLog(SQLModel, table=True):
    """A day the habit was ticked by hand, with the entry of a note / review habit. Weekly habits get one row per
    day they were done."""

    __tablename__ = "habit_logs"
    __table_args__ = (CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),)

    habit_id: int = Field(foreign_key="habits.id", ondelete="CASCADE", primary_key=True)
    date: dt.date = Field(primary_key=True)
    note: str | None = None
    rating: int | None = None
    ability_id: int | None = Field(default=None, foreign_key="abilities.id", ondelete="SET NULL", index=True)
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
