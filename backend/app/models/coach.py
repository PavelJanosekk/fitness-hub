"""Running knowledge synced from the user's RunningCoach GitHub repo (decision E11; the repo is the source)."""

import datetime as dt
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime


class CoachDocument(SQLModel, table=True):
    __tablename__ = "coach_documents"

    path: str = Field(primary_key=True)  # e.g. "04_timeline_plan.md"
    sha: str  # git blob sha: unchanged files are not downloaded again
    content: str = Field(sa_type=Text)
    fetched_at: dt.datetime = Field(sa_type=AwareDateTime)


class TrainingWeek(SQLModel, table=True):
    """One row of the weekly plan tables in 04_timeline_plan.md (replaced on every sync)."""

    __tablename__ = "training_weeks"

    week_start: dt.date = Field(primary_key=True)
    week_end: dt.date
    block: str | None = None
    km_text: str | None = None
    km_min: float | None = None
    km_max: float | None = None
    long_run_text: str | None = None
    long_run_km_min: float | None = None
    long_run_km_max: float | None = None
    quality: str | None = None
    notes: str | None = None


class Race(SQLModel, table=True):
    __tablename__ = "races"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    date: dt.date = Field(index=True)
    distance_km: float | None = None
    is_goal_race: bool = False  # the target race; others are tune-ups
    goal: str | None = None


class AthleteProfile(SQLModel, table=True):
    """Single row (id = 1): physiology parsed from the knowledge base, plus the last sync status."""

    __tablename__ = "athlete_profile"

    id: int = Field(default=1, primary_key=True)
    lthr: int | None = None
    max_hr: int | None = None
    kb_updated: dt.date | None = None  # "Aktualizováno" date in 00_INDEX.md
    last_synced_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
    last_sync_error: str | None = None
    sync_warnings: list[str] | None = Field(default=None, sa_type=JSONB)
    extra: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
