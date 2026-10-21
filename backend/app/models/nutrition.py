import datetime as dt
import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
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
    fueling = "fueling"  # during a run (gels, drinks): counts as intake, not against the day's target (E41)
    other = "other"


class FoodSource(StrEnum):
    usda = "usda"
    openfoodfacts = "openfoodfacts"
    kaloricke_tabulky = "kaloricke_tabulky"
    custom = "custom"
    web_estimate = "web_estimate"  # Gemini + web search, low confidence
    recipe = "recipe"  # values derived from recipe_components / recipe_yield_g


class MicrosStatus(StrEnum):
    """Where a food stands with micronutrient references (E26). Null = not tried yet (USDA foods never need it)."""

    mapped = "mapped"  # references set automatically (agent mapping file, Gemini mapper)
    unmatched = "unmatched"  # tried, nothing in USDA fits (e.g. shirataki)
    manual = "manual"  # the user edited the references: the mapper never touches it again


class Sex(StrEnum):
    male = "male"
    female = "female"


class Food(SQLModel, table=True):
    """A food or product, all values per 100 g (nutrition spec §2 + Amendments).

    Unknown ≠ 0: the optional macros stay null and `micronutrients` holds only the keys whose value is known
    (keys from app.services.nutrition.nutrients). Trigram indexes on the names live in migration 0007.
    """

    __tablename__ = "foods"
    __table_args__ = (
        one_of("source", FoodSource),
        one_of("micros_status", MicrosStatus),
        CheckConstraint("name_cs IS NOT NULL OR name_en IS NOT NULL", name="has_name"),
        CheckConstraint("kcal >= 0 AND protein_g >= 0 AND carbs_g >= 0 AND fat_g >= 0", name="macros_non_negative"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name_cs: str | None = None  # canonical Czech name; USDA foods get one when first used
    name_en: str | None = None
    brand: str | None = None
    category: str | None = None
    ean: str | None = Field(default=None, unique=True)
    source: str
    external_id: str | None = Field(default=None, unique=True)  # "usda:<fdc_id>", "off:<ean>", "kt:<guid>"
    is_raw: bool | None = None
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugar_g: float | None = None
    saturated_fat_g: float | None = None
    fiber_g: float | None = None
    salt_g: float | None = None
    micronutrients: dict[str, float] = Field(default_factory=dict, sa_type=JSONB)
    # Micros the food doesn't know itself come from its FoodMicroRef rows (E26)
    micros_status: str | None = None
    # A duplicate or irrelevant food (E28): still a micros reference, but out of the food list and Czech search
    hidden: bool = Field(default=False, sa_column_kwargs={"server_default": sa.false()})
    recipe_yield_g: float | None = None  # cooked weight of a recipe
    source_url: str | None = None  # the web recipe a looked-up dish was computed from (E30)
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)

    @property
    def name(self) -> str:
        return self.name_cs or self.name_en or ""


class FoodMicroRef(SQLModel, table=True):
    """A USDA food a food borrows micronutrients from (E26, generalizing C10): 92 % chicken ham → USDA chicken
    0.92; a home recipe → its ingredients. `grams_per_g` = grams of the reference in one gram of the food."""

    __tablename__ = "food_micro_refs"
    __table_args__ = (
        CheckConstraint("grams_per_g > 0 AND grams_per_g <= 5", name="grams_per_g_range"),
        CheckConstraint("food_id <> ref_food_id", name="not_self"),
    )

    food_id: int = Field(foreign_key="foods.id", ondelete="CASCADE", primary_key=True)
    ref_food_id: int = Field(foreign_key="foods.id", ondelete="CASCADE", primary_key=True, index=True)
    grams_per_g: float


class FoodAlias(SQLModel, table=True):
    """A normalized phrase that maps straight to a food. Only a confirmed alias may auto-save a meal (E4, C6)."""

    __tablename__ = "food_aliases"

    id: int | None = Field(default=None, primary_key=True)
    alias_normalized: str = Field(unique=True)
    food_id: int = Field(foreign_key="foods.id", ondelete="CASCADE", index=True)
    default_portion_g: float | None = None
    confirmed: bool = False
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class FoodPortion(SQLModel, table=True):
    """A named portion of a food: "1 rohlík = 43 g", USDA "1 cup = 152 g" (C9)."""

    __tablename__ = "food_portions"
    __table_args__ = (
        UniqueConstraint("food_id", "label"),
        CheckConstraint("grams > 0", name="grams_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)
    food_id: int = Field(foreign_key="foods.id", ondelete="CASCADE", index=True)
    label: str
    grams: float


class RecipeComponent(SQLModel, table=True):
    """Ingredient of a batch-cooked recipe; per-100 g values = sum of ingredients / recipe_yield_g (C9)."""

    __tablename__ = "recipe_components"
    __table_args__ = (CheckConstraint("amount_g > 0", name="amount_positive"),)

    recipe_food_id: int = Field(foreign_key="foods.id", ondelete="CASCADE", primary_key=True)
    ingredient_food_id: int = Field(foreign_key="foods.id", ondelete="RESTRICT", primary_key=True)
    amount_g: float


class NutritionProfile(SQLModel, table=True):
    """Single row (id = 1): who the targets are for and the targets themselves. Null = not set."""

    __tablename__ = "nutrition_profile"
    __table_args__ = (one_of("sex", Sex), CheckConstraint("id = 1", name="single_row"))

    id: int = Field(default=1, primary_key=True)
    sex: str | None = None
    birth_year: int | None = None
    height_cm: float | None = None
    kcal_target: float | None = None  # the base of the daily target; runs add to it (E41)
    protein_target_g: float | None = None
    fat_target_g: float | None = None  # carbs are the rest of the day's target
    maintenance_offset_kcal: float | None = None  # added to the base in maintenance mode; null = 500
    fiber_target_g: float | None = None
    base_proposal_handled_on: dt.date | None = None  # Monday whose base proposal was accepted or dismissed
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class MealSource(StrEnum):
    kaloricke_tabulky = "kaloricke_tabulky"  # imported; null = logged in this app


class MealLog(SQLModel, table=True):
    """The single home of intake data (docs/SPEC.md §5.7)."""

    __tablename__ = "meal_logs"
    __table_args__ = (one_of("meal_type", MealType), one_of("source", MealSource))

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    logged_date: dt.date = Field(index=True)
    meal_type: str = MealType.other
    source: str | None = None
    raw_user_input: str | None = None
    notes: str | None = None
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class MealLogItem(SQLModel, table=True):
    """Either a food + grams (nutrients computed live from `foods`, so fixing a food fixes its history; C8)
    or a quick-add item with manually entered values."""

    __tablename__ = "meal_log_items"
    __table_args__ = (
        CheckConstraint("(food_id IS NOT NULL AND amount_g IS NOT NULL) OR kcal IS NOT NULL", name="food_or_manual"),
        CheckConstraint("amount_g IS NULL OR amount_g > 0", name="amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    meal_log_id: uuid.UUID = Field(foreign_key="meal_logs.id", ondelete="CASCADE", index=True)
    label: str
    food_id: int | None = Field(default=None, foreign_key="foods.id", ondelete="RESTRICT", index=True)
    amount_g: float | None = None
    # Manual values (quick-add items only)
    kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    # The quick action that logged it (E42): the action is done for that day while its items exist
    quick_action_id: uuid.UUID | None = Field(default=None, foreign_key="quick_actions.id", ondelete="SET NULL")


class KTImportState(SQLModel, table=True):
    """Single row (id = 1): the resumable KalorickéTabulky import (Phase 5.5). `next_day` is the cursor."""

    __tablename__ = "kt_import_state"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: int = Field(default=1, primary_key=True)
    status: str = "idle"  # idle | running | done | error
    range_from: dt.date | None = None
    range_to: dt.date | None = None
    next_day: dt.date | None = None
    days_done: int = 0
    days_skipped: int = 0
    items_imported: int = 0
    foods_created: int = 0
    weights_filled: int = 0
    warnings: list[str] = Field(default_factory=list, sa_type=JSONB)
    last_error: str | None = None
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class QuickActionColor(StrEnum):
    """Accent palette names the frontend themes per theme (E42)."""

    emerald = "emerald"
    amber = "amber"
    red = "red"
    sky = "sky"
    violet = "violet"


class QuickAction(SQLModel, table=True):
    """A one-tap meal on Jídlo (E42): its foods go into `meal_type` of the open day. Offered while the local time
    is inside [start_minute, end_minute)."""

    __tablename__ = "quick_actions"
    __table_args__ = (
        one_of("meal_type", MealType),
        one_of("color", QuickActionColor),
        CheckConstraint("start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440", name="window"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # client-generated
    name: str
    emoji: str = "🍽️"
    color: str = QuickActionColor.emerald
    meal_type: str
    start_minute: int
    end_minute: int
    position: int = 0
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class QuickActionItem(SQLModel, table=True):
    """One food of a quick action; a food used here can't be deleted (RESTRICT, like logged items)."""

    __tablename__ = "quick_action_items"
    __table_args__ = (CheckConstraint("amount_g > 0", name="amount_positive"),)

    id: int | None = Field(default=None, primary_key=True)
    quick_action_id: uuid.UUID = Field(foreign_key="quick_actions.id", ondelete="CASCADE", index=True)
    food_id: int = Field(foreign_key="foods.id", ondelete="RESTRICT", index=True)
    amount_g: float
    position: int = 0
