"""The nutrition assistant (decision E2): its own prompt, tools and conversations on the shared Gemini runner.

Meals are logged with the hybrid flow (E4): `log_meal_from_items` saves directly only when every item resolves
through a confirmed mapping; otherwise the meal comes back as a draft the user confirms with one tap.
"""

import datetime as dt
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.config import settings
from app.models.chat import Assistant
from app.models.nutrition import Food, FoodSource, MealLog, MealLogItem, MealType
from app.services.conversations import get_conversation, load_history, store_turn
from app.services.gemini_service import Tier, lite_model, run_assistant
from app.services.nutrition.meals import MealEntry, save_meal
from app.services.nutrition.nutrients import MACROS
from app.services.nutrition.resolver import (
    Candidate,
    MealItemInput,
    Resolution,
    TopScoreChooser,
    resolve_items,
)
from app.services.nutrition.summary import day_summary
from app.timeutils import local_date, now_utc

KNOWN_FOODS = 150
CZECH_WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle")

NUTRITION_ROLE = """Jsi nutriční asistent uživatele (vlastní kalorické tabulky). Odpovídáš česky, stručně a věcně.

Zapisování jídla:
- Když uživatel popíše, co snědl (text nebo přepis hlasu, často s překlepy: "britský maso" = "krůtí maso"),
  zapiš to nástrojem log_meal_from_items: jedno volání na jedno jídlo, každá potravina jako zvláštní položka.
- user_phrase = slova uživatele pro potravinu, bez množství ("kuřecích stehen", ne "200g kuřecích stehen").
  canonical_name_cs = kanonický český název v 1. pádě i se stavem
  (syrové/vařené/pečené), bez obchodu a zbytečností. amount_g = snědené množství v gramech.
- Množství převeď na gramy. U známých potravin ze seznamu níže použij jejich typickou porci. Jinak:
  1 lžíce oleje/sádla 13 g, 1 lžička 5 g, 1 kelímek jogurtu/skyru 140 g, 1 vejce M 50 g (bez skořápky),
  1 rohlík 43 g, 1 krajíc chleba 60 g, 1 hrnek tekutiny 250 g.
- Základní suroviny (is_branded=false): zahoď značku i obchod ("kuřecí z Alberta" → "Kuřecí prsa, syrová")
  a vyplň usda_query_en ve stylu USDA ("Chicken, breast, meat only, raw"); raw/cooked podle toho,
  jak to uživatel vážil.
- Balené výrobky (is_branded=true): ponech značku, vyplň brand_search_query (např. "Milko skyr bílý")
  a usda_query_en jako obecnou náhradu.
- Odpovídá-li položka potravině ze seznamu známých potravin, vyplň její food_id.
- meal_type urči z kontextu a denní doby; date vynech, jde-li o dnešek.
- Když nástroj vrátí "needs_confirmation", nic se neuložilo: stručně řekni, co navrhuješ, a uživatel to
  v aplikaci potvrdí jedním ťuknutím.

Dotazy:
- Na otázky o příjmu, makrech, vitamínech a minerálech VŽDY nejdřív zavolej get_daily_nutrition_summary.
- coverage je podíl kalorií dne z potravin, které danou hodnotu znají. Pod ~0,7 jsou data neúplná: řekni to
  a nevykládej to jako nedostatek.
- Nutriční hodnoty si nevymýšlej, čísla ber jen z nástrojů."""

CHOOSER_PROMPT = """Pro každou položku jídla vyber kandidáta z databáze, který nejlépe odpovídá tomu,
co uživatel snědl: druh potraviny, stav (syrové/vařené/pečené), díl a tučnost. Když žádný neodpovídá,
dej choice null. confidence 0–1 vyjadřuje, jak jistě kandidát odpovídá.

"""

ESTIMATE_PROMPT = """{task} nutriční hodnoty na 100 g pro potravinu: "{name}" (uživatel řekl: "{phrase}").
{sources}Odpověz POUZE jedním JSON objektem:
{{"name": "...", "brand": null, "kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "sugar_g": null,
"saturated_fat_g": null, "fiber_g": null, "salt_g": null, "source_url": "..."}}
Neznámé hodnoty dej null. Když hodnoty spolehlivě neznáš, odpověz {{}}."""
GROUNDED = {
    "task": "Najdi na webu",
    "sources": "Přednostně kaloricketabulky.cz, kosik.cz, rohlik.cz nebo web výrobce. ",
}
# Search grounding isn't in the free tier (checked 2026-10-17: 429 on gemini-3.5-flash-lite), so without it the
# model estimates from what it knows; the candidate is flagged grounded=False and shown as an AI estimate
UNGROUNDED = {"task": "Odhadni z typického složení a běžných receptur", "sources": ""}


class Pick(BaseModel):
    item: int = Field(description="Item number")
    choice: int | None = Field(description="Candidate number, or null when none fits")
    confidence: float = Field(ge=0, le=1)


class GeminiChooser:
    """Picks candidates in one structured call per meal; a Gemini failure falls back to the top score."""

    def __init__(self, client: genai.Client):
        self.client = client
        self.model = lite_model()  # its own free-tier quota (E15)

    def choose(self, resolutions: list[Resolution]) -> list[tuple[int | None, float | None]]:
        lines = []
        for i, r in enumerate(resolutions):
            query = f"; USDA dotaz: {r.item.usda_query_en}" if r.item.usda_query_en else ""
            lines.append(
                f'Položka {i}: "{r.item.user_phrase}" = {r.item.canonical_name_cs}, {r.item.amount_g:g} g{query}'
            )
            for j, c in enumerate(r.candidates):
                v = c.per_100g
                brand = f" [{c.brand}]" if c.brand else ""
                lines.append(
                    f"  {j}: {c.name}{brand} ({c.source}): {v.get('kcal')} kcal, B {v.get('protein_g')} g, "
                    f"S {v.get('carbs_g')} g, T {v.get('fat_g')} g na 100 g"
                )
        fallback = TopScoreChooser().choose(resolutions)
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=CHOOSER_PROMPT + "\n".join(lines),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=list[Pick],
                    temperature=0,
                ),
            )
        except Exception:  # quota, network, model errors: the draft still shows the best-scored candidate
            return fallback
        picks = {p.item: p for p in (response.parsed or []) if isinstance(p, Pick)}
        out = []
        for i, r in enumerate(resolutions):
            pick = picks.get(i)
            if pick is None or (pick.choice is not None and not 0 <= pick.choice < len(r.candidates)):
                out.append(fallback[i])
            else:
                out.append((pick.choice, pick.confidence))
        return out

    def estimate(self, item: MealItemInput) -> Candidate | None:
        """Per-100 g estimate in its own call (search grounding isn't combined with function tools, C5): from the
        web when grounding is available, else from the model's knowledge."""
        for grounded, wording in ((True, GROUNDED), (False, UNGROUNDED)):
            search = [types.Tool(google_search=types.GoogleSearch())] if grounded else None
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=ESTIMATE_PROMPT.format(name=item.canonical_name_cs, phrase=item.user_phrase, **wording),
                    config=types.GenerateContentConfig(tools=search, temperature=0),
                )
            except Exception:
                continue
            if (candidate := parse_estimate(response.text or "", item)) is not None:
                candidate.grounded = grounded
                return candidate
        return None


def parse_estimate(text: str, item: MealItemInput) -> Candidate | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return None
    per_100g: dict[str, float | None] = {}
    for nutrient in MACROS:
        value = data.get(nutrient.key)
        per_100g[nutrient.key] = float(value) if isinstance(value, int | float) and value >= 0 else None
    if any(per_100g[k] is None for k in ("kcal", "protein_g", "carbs_g", "fat_g")):
        return None
    name = str(data.get("name") or item.canonical_name_cs)[:200]
    brand = data.get("brand") if isinstance(data.get("brand"), str) else None
    return Candidate("web", name, FoodSource.web_estimate, per_100g, brand, 0.3)


@dataclass
class NutritionContext:
    session: Session
    http: httpx.Client | None
    chooser_factory: Callable[[], Any]
    now: dt.datetime = field(default_factory=now_utc)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    saved_meals: list[dict[str, Any]] = field(default_factory=list)


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None}


def _kcal(candidate: Candidate | None, grams: float) -> float | None:
    kcal = candidate.per_100g.get("kcal") if candidate else None
    return round(kcal * grams / 100, 1) if kcal is not None else None


def build_nutrition_tools(ctx: NutritionContext) -> list[Callable[..., dict[str, Any]]]:
    session = ctx.session

    # meal_type is a plain str: the SDK's argument conversion can't isinstance-check a top-level Literal
    def log_meal_from_items(meal_type: str, items: list[MealItemInput], date: str | None = None) -> dict[str, Any]:
        """Log ONE meal the user ate. Saved directly when every food is already known and confirmed;
        otherwise returns status "needs_confirmation" and the user confirms the proposed foods in the app.

        Args:
            meal_type: One of breakfast, morning_snack, lunch, afternoon_snack, dinner, second_dinner, other.
            items: Every food of the meal with its amount in grams.
            date: YYYY-MM-DD only when it wasn't today.
        """
        if meal_type not in MealType.__members__:
            return {"error": f"meal_type must be one of {', '.join(MealType.__members__)}"}
        if not items:
            return {"error": "No items"}
        try:
            day = dt.date.fromisoformat(date) if date else local_date(ctx.now)
        except ValueError:
            return {"error": "date must be YYYY-MM-DD"}
        resolutions = resolve_items(session, ctx.http, items, ctx.chooser_factory())
        if all(r.confirmed for r in resolutions):
            entries = [MealEntry(r.item.user_phrase, r.food, r.item.amount_g) for r in resolutions if r.food]
            meal = save_meal(session, meal_id=uuid.uuid4(), day=day, meal_type=meal_type, entries=entries)
            summary = [
                {"food": e.food.name, "grams": e.amount_g, "kcal": round(e.food.kcal * e.amount_g / 100, 1)}
                for e in entries
            ]
            saved = {"meal_id": str(meal.id), "date": day.isoformat(), "meal_type": meal_type, "items": summary}
            ctx.saved_meals.append(saved)
            return {"status": "saved", **saved, "total_kcal": round(sum(i["kcal"] for i in summary), 1)}

        ctx.drafts.append(
            {
                "kind": "meal",
                "date": day.isoformat(),
                "meal_type": meal_type,
                "items": [
                    {
                        "input": r.item.model_dump(),
                        "amount_g": r.item.amount_g,
                        "confirmed": r.confirmed,
                        "confidence": r.confidence,
                        "chosen": r.chosen.to_dict() if r.chosen else None,
                        "candidates": [c.to_dict() for c in (r.candidates or ([r.chosen] if r.chosen else []))],
                    }
                    for r in resolutions
                ],
            }
        )
        return {
            "status": "needs_confirmation",
            "items": [
                _compact(
                    {
                        "phrase": r.item.user_phrase,
                        "proposed": r.chosen.name if r.chosen else None,
                        "source": r.chosen.source if r.chosen else None,
                        "grams": r.item.amount_g,
                        "kcal": _kcal(r.chosen, r.item.amount_g),
                        "confidence": r.confidence,
                        "known": r.confirmed or None,
                    }
                )
                for r in resolutions
            ],
            "message": "Not saved yet; the user confirms or swaps the foods in the app.",
        }

    def get_daily_nutrition_summary(date: str | None = None) -> dict[str, Any]:
        """Intake of one day: meals, macros and micronutrients with targets, % of target and coverage
        (share of the day's kcal from foods that know the value; below ~0.7 the total is incomplete).

        Args:
            date: YYYY-MM-DD; today when omitted.
        """
        try:
            day = dt.date.fromisoformat(date) if date else local_date(ctx.now)
        except ValueError:
            return {"error": "date must be YYYY-MM-DD"}
        summary = day_summary(session, day)
        return {
            "date": day.isoformat(),
            "training_day": summary.training_day,
            "nutrients": [
                _compact(
                    {
                        "name": n.label,
                        "amount": round(n.amount, 2) if n.amount is not None else None,
                        "unit": n.unit,
                        "target": n.target,
                        "percent": n.percent,
                        "coverage": n.coverage,
                    }
                )
                for n in summary.nutrients
                if n.amount is not None
            ],
            "meals": [
                {
                    "meal_type": m.meal_type,
                    "items": [
                        _compact({"name": i.food_name or i.label, "grams": i.amount_g, "kcal": i.kcal}) for i in m.items
                    ],
                }
                for m in summary.meals
            ],
        }

    return [log_meal_from_items, get_daily_nutrition_summary]


def known_foods(session: Session, limit: int = KNOWN_FOODS) -> str:
    """The user's most eaten foods with a typical portion (C7), so the model can pass food_id directly."""
    typical = func.percentile_cont(0.5).within_group(col(MealLogItem.amount_g))
    rows = session.exec(
        select(Food, func.count(), typical)
        .join(MealLogItem, col(MealLogItem.food_id) == Food.id)
        .group_by(col(Food.id))
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return "\n".join(f"{food.id} | {food.name} | {round(grams or 0)} g" for food, _, grams in rows)


def nutrition_system_instruction(session: Session, now: dt.datetime) -> str:
    today = local_date(now)
    sections = [
        NUTRITION_ROLE,
        f"Dnes je {CZECH_WEEKDAYS[today.weekday()]} {today.day}.{today.month}.{today.year}, "
        f"{now.astimezone(settings.tz).strftime('%H:%M')} místního času.",
    ]
    if foods := known_foods(session):
        sections.append("Známé potraviny (food_id | název | typická porce):\n" + foods)
    return "\n\n".join(sections)


@dataclass
class NutritionTurn:
    reply: str
    conversation_id: uuid.UUID
    tool_calls_made: list[str]
    drafts: list[dict[str, Any]]
    saved_meals: list[dict[str, Any]]
    model: str | None = None


def nutrition_turn(
    session: Session,
    client: genai.Client,
    http: httpx.Client | None,
    *,
    user_text: str,
    stored_text: str | None = None,
    extra_parts: list[types.Part] | None = None,
    conversation_id: uuid.UUID | None = None,
    tier: Tier = "fast",
) -> NutritionTurn:
    conversation = get_conversation(session, conversation_id, Assistant.nutrition)
    history = load_history(session, conversation)
    now = now_utc()
    ctx = NutritionContext(session=session, http=http, chooser_factory=lambda: GeminiChooser(client), now=now)
    result = run_assistant(
        client,
        system_instruction=nutrition_system_instruction(session, now),
        tools=build_nutrition_tools(ctx),
        history=history,
        parts=[*(extra_parts or []), types.Part.from_text(text=user_text)],
        tier=tier,
        fast_model=settings.gemini_model_nutrition,
    )
    stored = stored_text or user_text
    for draft in ctx.drafts:
        draft["raw_input"] = stored
    for saved in ctx.saved_meals:
        if (meal := session.get(MealLog, uuid.UUID(saved["meal_id"]))) is not None:
            meal.raw_user_input = stored
            session.add(meal)
    store_turn(session, conversation, stored, result)
    return NutritionTurn(
        reply=result.reply,
        conversation_id=conversation.id,
        tool_calls_made=[call["name"] for call in result.tool_calls],
        drafts=ctx.drafts,
        saved_meals=ctx.saved_meals,
        model=result.model,
    )
