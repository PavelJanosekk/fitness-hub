import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.nutrition import MealType


class QuickAdd(BaseModel):
    id: uuid.UUID  # client-generated; used for both the meal log and its single item
    date: dt.date | None = None  # defaults to today in APP_TZ
    meal_type: MealType = MealType.other
    label: str = Field(default="Rychlý zápis", min_length=1, max_length=120)
    kcal: float = Field(ge=0, le=20000)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)


class MealItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None


class MealRead(BaseModel):
    id: uuid.UUID
    logged_date: dt.date
    meal_type: MealType
    notes: str | None
    items: list[MealItemRead]


class Totals(BaseModel):
    kcal: float = 0
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class DayIntake(BaseModel):
    date: dt.date
    meals: list[MealRead]
    totals: Totals
