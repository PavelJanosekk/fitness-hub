"""Doplnit automaticky (E26): values for a food the user is creating, from its name (and brand).

One Gemini lite call reads the name: is it a branded product (→ OFF search query) or a basic food (→ USDA query),
plus a per-100 g estimate and the components for micronutrient references (as in `mapper.py`). Label data wins:
an OFF product, else a close USDA match, else the estimate. The user reviews everything in the form before saving.
"""

from typing import Any

import httpx
from google.genai import types
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models.nutrition import Food
from app.schemas.nutrition import AutofillRead, MicroRefRead
from app.services.gemini_service import lite_model
from app.services.nutrition import off
from app.services.nutrition.mapper import Component, resolve_components
from app.services.nutrition.nutrients import MACROS
from app.services.nutrition.resolver import search_usda

USDA_MIN_SCORE = 0.9  # stricter than the mapper: these become the food's own macros

AUTOFILL_PROMPT = """Uživatel zakládá potravinu "{name}"{brand}. Vyplň:
- name_cs: kanonický český název v 1. pádě (bez značky).
- is_branded: true, když jde o konkrétní balený výrobek; pak brand_search_query pro vyhledání v Open Food Facts
  (značka + název výrobku).
- usda_query_en: anglický popis ve stylu USDA SR Legacy pro základní potravinu nebo nejbližší obecný ekvivalent
  ("Yogurt, Greek, plain, nonfat").
- estimate: odhad hodnot na 100 g z typického složení (neznámé hodnoty null).
- components: z jakých potravin USDA se skládá, pro odhad vitamínů a minerálů (usda_query_en + grams_per_100g;
  jednoduchá potravina = jedna složka 100 g; sladidla a podobné bez obdoby = prázdný seznam)."""


class Estimate(BaseModel):
    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    sugar_g: float | None = Field(default=None, ge=0, le=100)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=100)
    fiber_g: float | None = Field(default=None, ge=0, le=100)
    salt_g: float | None = Field(default=None, ge=0, le=100)


class AutofillAnswer(BaseModel):
    name_cs: str = Field(min_length=1, max_length=200)
    is_branded: bool = False
    brand_search_query: str | None = None
    usda_query_en: str | None = None
    estimate: Estimate | None = None
    components: list[Component] = Field(default_factory=list)


class AutofillUnavailableError(RuntimeError):
    pass


def _macros(food: Food) -> dict[str, float | None]:
    return {n.key: getattr(food, n.key) for n in MACROS}


def autofill(session: Session, client: Any, http: httpx.Client | None, name: str, brand: str | None) -> AutofillRead:
    try:
        response = client.models.generate_content(
            model=lite_model(),
            contents=AUTOFILL_PROMPT.format(name=name, brand=f" (značka {brand})" if brand else ""),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=AutofillAnswer, temperature=0
            ),
        )
    except Exception as exc:  # quota, network, model errors
        raise AutofillUnavailableError(str(exc)) from exc
    answer = response.parsed
    if not isinstance(answer, AutofillAnswer):
        raise AutofillUnavailableError("no answer")

    refs = [
        MicroRefRead(ref_food_id=ref_id, name=ref.name, grams_per_g=grams)
        for ref_id, grams in resolve_components(session, answer.components)
        if (ref := session.get(Food, ref_id)) is not None
    ]
    result = {"name_cs": name, "brand": brand, "micro_refs": refs, "micronutrients": {}}

    if answer.is_branded and answer.brand_search_query and http is not None:
        try:
            products = off.search(http, answer.brand_search_query, limit=5)
        except httpx.HTTPError:
            products = []  # OFF down: fall through to USDA / the estimate
        if products:
            p = products[0]
            label = f"{p.name} ({p.brand})" if p.brand else p.name
            values = {n.key: p.values.get(n.key) for n in MACROS}
            result["micronutrients"] = p.micronutrients
            return AutofillRead(**result, source="openfoodfacts", source_label=label, values=values)
    if not answer.is_branded and answer.usda_query_en:
        hits = search_usda(session, answer.usda_query_en, limit=1)
        if hits and hits[0][1] >= USDA_MIN_SCORE:
            usda = hits[0][0]
            # The food is that USDA food, so it is its own exact reference
            result["micro_refs"] = [MicroRefRead(ref_food_id=usda.id, name=usda.name, grams_per_g=1)]  # type: ignore[arg-type]
            return AutofillRead(**result, source="usda", source_label=usda.name_en, values=_macros(usda))
    if answer.estimate is None:
        raise AutofillUnavailableError("no estimate")
    return AutofillRead(**result, source="estimate", source_label=None, values=answer.estimate.model_dump())
