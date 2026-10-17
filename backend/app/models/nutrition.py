import datetime as dt
import uuid
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class MealType(StrEnum):
    breakfast = "breakfast"
    morning_snack = "morning_snack"
    lunch = "lunch"
    afternoon_snack = "afternoon_snack"
    dinner = "dinner"
    second_dinner = "second_dinner"  # KalorickéTabulky "Druhá večeře"
    other = "other"


class MealLog(SQLModel, table=True):
    """The single home of intake data (docs/SPEC.md §5.7). Minimal now, extended in Phase 5."""

    __tablename__ = "meal_logs"
    __table_args__ = (one_of("meal_type", MealType),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    logged_date: dt.date = Field(index=True)
    meal_type: str = MealType.other
    raw_user_input: str | None = None
    notes: str | None = None
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class MealLogItem(SQLModel, table=True):
    __tablename__ = "meal_log_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    meal_log_id: uuid.UUID = Field(foreign_key="meal_logs.id", ondelete="CASCADE", index=True)
    label: str
    kcal: float
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
