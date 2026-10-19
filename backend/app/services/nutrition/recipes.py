"""Recipe foods (C9, E30): per-100 g values = the ingredients' sum over the finished weight (`recipe_yield_g`).

A dish the smart lookup computed (`lookup.py`) becomes a `recipe` food when the user confirms it: its USDA
ingredients are stored as `recipe_components` (grams as in the recipe) and as its micro references (grams per
gram of the dish, E26), so micronutrients and the optional macros come from USDA like for any other reference.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, col, select

from app.models.nutrition import Food, FoodPortion, FoodSource, MicrosStatus, RecipeComponent
from app.services.nutrition.micro_refs import set_refs
from app.services.nutrition.nutrients import REQUIRED_MACROS

PORTION_LABEL = "porce"
YIELD_RANGE = (0.3, 3.0)  # finished weight / raw ingredient mass


@dataclass
class Part:
    """One ingredient line: grams as in the recipe and the USDA food behind it (None = nothing in USDA fits)."""

    name: str
    grams: float
    food: Food | None = None
    assumed: bool = False  # the recipe gives no amount: estimated


def finished_weight(parts: list[Part], estimate: float) -> float:
    """The estimated weight of the finished dish, kept within what cooking can do to the raw mass (meat loses
    water, pasta and rice soak it up); otherwise the raw mass."""
    total = sum(p.grams for p in parts)
    return estimate if YIELD_RANGE[0] * total <= estimate <= YIELD_RANGE[1] * total else total


def per_100g(parts: list[Part], yield_g: float) -> dict[str, float]:
    """kcal/P/C/F per 100 g of the finished dish. Unresolved ingredients add nothing (they are listed, not
    guessed)."""
    return {
        key: round(sum(getattr(p.food, key) * p.grams for p in parts if p.food) / yield_g, 2) for key in REQUIRED_MACROS
    }


def recipe_info(parts: list[Part], yield_g: float, portions: float, source_url: str | None) -> dict[str, Any]:
    """The recipe as a draft candidate carries it (the client sends it back on confirmation)."""
    return {
        "source_url": source_url,
        "yield_g": round(yield_g),
        "portion_g": round(yield_g / portions),
        "ingredients": [
            {
                "name": p.name,
                "grams": round(p.grams, 1),
                "food_id": p.food.id if p.food else None,
                "food_name": p.food.name if p.food else None,
                "assumed": p.assumed,
            }
            for p in parts
        ],
    }


def save_recipe(session: Session, name_cs: str, recipe: dict[str, Any]) -> Food:
    """Create the confirmed dish. The values are recomputed from the ingredient foods, never taken from the client;
    an ingredient id that isn't a USDA food counts as unresolved."""
    ids = [i["food_id"] for i in recipe["ingredients"] if i.get("food_id") is not None]
    foods = {
        f.id: f for f in session.exec(select(Food).where(col(Food.id).in_(ids), Food.source == FoodSource.usda)).all()
    }
    parts = [
        Part(i["name"], i["grams"], foods.get(i.get("food_id")), i.get("assumed", False)) for i in recipe["ingredients"]
    ]
    if not any(p.food for p in parts):
        raise ValueError("no ingredient resolves to a USDA food")
    yield_g = finished_weight(parts, float(recipe["yield_g"]))
    food = Food(
        name_cs=name_cs,
        source=FoodSource.recipe,
        recipe_yield_g=round(yield_g, 1),
        source_url=recipe.get("source_url"),
        **per_100g(parts, yield_g),
    )
    session.add(food)
    session.flush()
    grams: dict[int, float] = defaultdict(float)
    for part in parts:
        if part.food is not None and part.food.id is not None:
            grams[part.food.id] += part.grams
    for ingredient_id, amount in grams.items():
        component = RecipeComponent(recipe_food_id=food.id, ingredient_food_id=ingredient_id, amount_g=round(amount, 1))  # type: ignore[arg-type]
        session.add(component)
    set_refs(session, food, [(i, g / yield_g) for i, g in grams.items()], MicrosStatus.mapped)
    if portion_g := recipe.get("portion_g"):
        session.add(FoodPortion(food_id=food.id, label=PORTION_LABEL, grams=float(portion_g)))  # type: ignore[arg-type]
    session.flush()
    return food
