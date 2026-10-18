import datetime as dt

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime
from app.timeutils import now_utc


class RpgPause(SQLModel, table=True):
    """Illness / holiday (E22): no XP and no penalties on paused days; streaks and the week % step over them."""

    __tablename__ = "rpg_pauses"
    __table_args__ = (CheckConstraint("end_date IS NULL OR end_date >= start_date", name="dates_ordered"),)

    id: int | None = Field(default=None, primary_key=True)
    start_date: dt.date
    end_date: dt.date | None = None  # null = still paused
    note: str | None = None
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
