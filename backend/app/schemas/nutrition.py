import datetime as dt
import uuid
from typing import Literal

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
    """Food items carry food_id + amount_g and nutrients computed from the food; quick-add items their own."""

    id: uuid.UUID
    label: str
    food_id: int | None = None
    food_name: str | None = None
    food_source: str | None = None
    amount_g: float | None = None
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


class PortionRead(BaseModel):
    label: str
    grams: float


class FoodValues(BaseModel):
    """Per-100 g values of a food; unknown values stay null (never 0)."""

    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    sugar_g: float | None = Field(default=None, ge=0, le=100)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=100)
    fiber_g: float | None = Field(default=None, ge=0, le=100)
    salt_g: float | None = Field(default=None, ge=0, le=100)
    micronutrients: dict[str, float] = Field(default_factory=dict)


class MicroRefIn(BaseModel):
    """A USDA food the food borrows unknown values from (E26): grams of it per gram of the food."""

    ref_food_id: int
    grams_per_g: float = Field(gt=0, le=5)


class MicroRefRead(MicroRefIn):
    name: str


class RecipeComponentRead(BaseModel):
    food_id: int
    name: str
    amount_g: float


class FoodCreate(FoodValues):
    name_cs: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=120)
    ean: str | None = Field(default=None, pattern=r"^[0-9]{6,14}$")
    portions: list[PortionRead] = Field(default_factory=list)
    # From /foods/autofill; None = map in the background (E26)
    micro_refs: list[MicroRefIn] | None = Field(default=None, max_length=20)


class FoodUpdate(BaseModel):
    """Only the given fields change; micronutrients, when given, replace the whole set."""

    name_cs: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = None
    brand: str | None = None
    kcal: float | None = Field(default=None, ge=0, le=900)
    protein_g: float | None = Field(default=None, ge=0, le=100)
    carbs_g: float | None = Field(default=None, ge=0, le=100)
    fat_g: float | None = Field(default=None, ge=0, le=100)
    sugar_g: float | None = Field(default=None, ge=0, le=100)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=100)
    fiber_g: float | None = Field(default=None, ge=0, le=100)
    salt_g: float | None = Field(default=None, ge=0, le=100)
    micronutrients: dict[str, float] | None = None
    hidden: bool | None = None  # E28: out of the list and Czech search, still a micros reference
    # Replaces the references; the food becomes `manual` and the mapper leaves it alone (E26)
    micro_refs: list[MicroRefIn] | None = Field(default=None, max_length=20)


class FoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_cs: str | None
    name_en: str | None
    brand: str | None
    category: str | None
    ean: str | None
    source: str
    is_raw: bool | None
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugar_g: float | None
    saturated_fat_g: float | None
    fiber_g: float | None
    salt_g: float | None
    micronutrients: dict[str, float]
    portions: list[PortionRead] = Field(default_factory=list)
    use_count: int = 0
    micros_status: str | None = None
    hidden: bool = False
    micro_refs: list[MicroRefRead] = Field(default_factory=list)
    # Per-100 g values the food doesn't know itself, from its references (optional macros and micros)
    borrowed: dict[str, float] = Field(default_factory=dict)
    # Recipes (C9, E30): ingredients in recipe grams, the finished weight, the web recipe it was computed from
    recipe_components: list[RecipeComponentRead] = Field(default_factory=list)
    recipe_yield_g: float | None = None
    source_url: str | None = None


class AutofillRequest(BaseModel):
    name_cs: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=120)


class AutofillRead(BaseModel):
    """Suggested values for a new food: label data from OFF, a USDA food, or an AI estimate (E26)."""

    name_cs: str
    brand: str | None
    source: Literal["openfoodfacts", "usda", "estimate"]
    source_label: str | None  # the OFF product or USDA food the values come from
    values: dict[str, float | None]  # kcal, protein_g, ... per 100 g
    micronutrients: dict[str, float]
    micro_refs: list[MicroRefRead]


class ItemUpsert(BaseModel):
    """A food item added or edited by hand (food database, barcode, inline gram edit)."""

    food_id: int
    amount_g: float = Field(gt=0, le=5000)
    meal_type: MealType = MealType.other
    date: dt.date | None = None  # defaults to today in APP_TZ
    label: str | None = Field(default=None, max_length=200)


class RecipeIngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    grams: float = Field(gt=0, le=5000)
    food_id: int | None = None  # the USDA food; null = nothing fits (adds nothing)
    food_name: str | None = None
    assumed: bool = False


class RecipeIn(BaseModel):
    """A computed recipe (E30); the server recomputes its values from the ingredient foods on confirmation."""

    source_url: str | None = Field(default=None, max_length=2000)
    yield_g: float = Field(gt=0, le=20000)
    portion_g: float | None = Field(default=None, gt=0, le=5000)
    ingredients: list[RecipeIngredientIn] = Field(min_length=1, max_length=60)


class CandidateIn(BaseModel):
    """A draft candidate as the server sent it (ref: "food:<id>", "off:<ean>", "web" or "recipe")."""

    ref: str = Field(pattern=r"^(food:[0-9]+|off:[0-9]{6,14}|web|recipe)$")
    name: str = Field(min_length=1, max_length=200)
    source: str
    brand: str | None = None
    per_100g: dict[str, float | None]
    micronutrients: dict[str, float] = Field(default_factory=dict)
    grounded: bool | None = None
    recipe: RecipeIn | None = None


class ProfileUpdate(BaseModel):
    sex: Literal["male", "female"] | None = None
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    height_cm: float | None = Field(default=None, gt=50, lt=260)
    kcal_target: float | None = Field(default=None, gt=0, lt=10000)
    kcal_target_training_day: float | None = Field(default=None, gt=0, lt=10000)
    protein_target_g: float | None = Field(default=None, ge=0, lt=1000)
    carbs_target_g: float | None = Field(default=None, ge=0, lt=2000)
    fat_target_g: float | None = Field(default=None, ge=0, lt=1000)
    fiber_target_g: float | None = Field(default=None, ge=0, lt=200)
