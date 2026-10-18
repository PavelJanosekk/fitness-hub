"""Nutrition routes (nutrition spec §5): the assistant (chat, voice), intake, the food database, barcode lookup,
profile and meal drafts."""

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)
from kaloricketabulky.sdk import KaloricketabulkyClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import settings
from app.database import SessionDep, engine
from app.models.nutrition import Food, FoodSource, MealLog, MealLogItem, MealType, NutritionProfile
from app.routers.ai_coach import ChatRequest, GeminiDep, audio_part, run_gemini
from app.schemas.nutrition import (
    AutofillRead,
    AutofillRequest,
    CandidateIn,
    DayIntake,
    FoodCreate,
    FoodRead,
    FoodUpdate,
    ItemUpsert,
    MealItemRead,
    MealRead,
    ProfileUpdate,
    QuickAdd,
    Totals,
)
from app.services.gemini_service import Tier
from app.services.nutrition import kt_import, mapper, off
from app.services.nutrition import quick_add as quick_add_meal
from app.services.nutrition.assistant import NutritionTurn, nutrition_turn
from app.services.nutrition.autofill import AutofillUnavailableError, autofill
from app.services.nutrition.foods import create_food, read_food, search_foods, update_food
from app.services.nutrition.meals import MealEntry, save_meal, upsert_item
from app.services.nutrition.nutrients import ALL as ALL_NUTRIENTS
from app.services.nutrition.nutrients import MICRO_KEYS
from app.services.nutrition.resolver import Candidate, MealItemInput, confirm_aliases, materialize
from app.services.nutrition.summary import DaySummary, day_meals, day_summary, read_item
from app.timeutils import now_utc, today

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


def get_http() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=15) as client:
        yield client


HttpDep = Annotated[httpx.Client, Depends(get_http)]


VOICE_INSTRUCTION = "Zpracuj tuto hlasovou nahrávku: zapiš snědené jídlo nástrojem a stručně potvrď, co je uložené."


class NutritionChatResponse(BaseModel):
    reply: str
    conversation_id: uuid.UUID
    tool_calls_made: list[str]
    drafts: list[dict[str, Any]]  # meal drafts for 1-tap confirmation (POST /drafts/confirm)
    saved_meals: list[dict[str, Any]]
    model: str | None


def _chat_response(turn: NutritionTurn) -> NutritionChatResponse:
    return NutritionChatResponse(
        reply=turn.reply,
        conversation_id=turn.conversation_id,
        tool_calls_made=turn.tool_calls_made,
        drafts=turn.drafts,
        saved_meals=turn.saved_meals,
        model=turn.model,
    )


class NutritionChatRequest(ChatRequest):
    date: dt.date | None = None  # the day open in the app: meals are logged to it unless the user names another


@router.post("/chat", response_model=NutritionChatResponse)
def chat(body: NutritionChatRequest, session: SessionDep, client: GeminiDep, http: HttpDep) -> NutritionChatResponse:
    """The nutrition assistant: log meals in Czech, ask about intake. Its own conversations (E2)."""
    turn = run_gemini(
        lambda: nutrition_turn(
            session,
            client,
            http,
            user_text=body.message,
            conversation_id=body.conversation_id,
            tier=body.model,
            view_date=body.date,
        )
    )
    return _chat_response(turn)


@router.post("/voice", response_model=NutritionChatResponse)
def voice(
    session: SessionDep,
    client: GeminiDep,
    http: HttpDep,
    audio: Annotated[UploadFile | None, File(description="Recording from MediaRecorder")] = None,
    text: Annotated[str | None, Form(max_length=4000)] = None,
    conversation_id: Annotated[uuid.UUID | None, Form()] = None,
    model: Annotated[Tier, Form()] = "fast",
    date: Annotated[dt.date | None, Form()] = None,
) -> NutritionChatResponse:
    """A dictated meal as audio or text; saved or returned as a draft (hybrid flow)."""
    if audio is None and not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send audio or text")
    extra_parts = [audio_part(audio)] if audio is not None else []
    user_text = f"{VOICE_INSTRUCTION}\n{text}" if text and audio is not None else (text or VOICE_INSTRUCTION)
    stored = f"🎤 [hlasová nahrávka]{' ' + text if text else ''}" if audio is not None else text
    turn = run_gemini(
        lambda: nutrition_turn(
            session,
            client,
            http,
            user_text=user_text,
            stored_text=stored,
            extra_parts=extra_parts,
            conversation_id=conversation_id,
            tier=model,
            view_date=date,
        )
    )
    return _chat_response(turn)


@router.post("/quick-add", response_model=MealRead)
def quick_add(body: QuickAdd, session: SessionDep) -> MealRead:
    """Idempotent: the client UUID identifies both the meal log and its single item."""
    meal, item = quick_add_meal(session, body)
    items = [read_item(item, None)]
    return MealRead(id=meal.id, logged_date=meal.logged_date, meal_type=meal.meal_type, notes=meal.notes, items=items)


@router.get("/day", response_model=DayIntake)
def get_day(session: SessionDep, date: dt.date | None = None) -> DayIntake:
    day = date or today()
    meals = day_meals(session, day)
    return DayIntake(date=day, meals=meals, totals=_totals([i for m in meals for i in m.items]))


@router.get("/summary", response_model=DaySummary)
def get_summary(session: SessionDep, date: dt.date | None = None) -> DaySummary:
    """Meals plus every tracked nutrient with its coverage and target (profile, else EU reference)."""
    return day_summary(session, date or today())


@router.put("/items/{item_id}", response_model=MealItemRead)
def put_item(item_id: uuid.UUID, body: ItemUpsert, session: SessionDep) -> MealItemRead:
    """Idempotent upsert by the client UUID: add a food with grams, or change an item's food/grams."""
    food = session.get(Food, body.food_id)
    if food is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown food")
    return read_item(upsert_item(session, item_id, body, food), food)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, session: SessionDep) -> Response:
    item = session.get(MealLogItem, item_id)
    if item is not None:
        meal_id = item.meal_log_id
        session.delete(item)
        session.flush()
        remaining = session.exec(select(MealLogItem.id).where(MealLogItem.meal_log_id == meal_id)).first()
        if remaining is None and (meal := session.get(MealLog, meal_id)) is not None:
            session.delete(meal)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class NutrientInfo(BaseModel):
    key: str
    label: str
    unit: str
    micro: bool


@router.get("/nutrients", response_model=list[NutrientInfo])
def list_nutrients() -> list[NutrientInfo]:
    """Every tracked nutrient in display order, for labelling per-food values."""
    return [NutrientInfo(key=n.key, label=n.label_cs, unit=n.unit, micro=n.key in MICRO_KEYS) for n in ALL_NUTRIENTS]


@router.get("/foods", response_model=list[FoodRead])
def list_foods(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    source: FoodSource | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FoodRead]:
    return search_foods(session, q, source.value if source else None, limit, offset)


@router.get("/foods/{food_id}", response_model=FoodRead)
def get_food(food_id: int, session: SessionDep) -> FoodRead:
    return read_food(session, _food(session, food_id), with_portions=True)


@router.post("/foods/autofill", response_model=AutofillRead)
def post_autofill(body: AutofillRequest, session: SessionDep, client: GeminiDep, http: HttpDep) -> AutofillRead:
    """Suggested values for a new food from its name (E26); nothing is saved."""
    try:
        return autofill(session, client, http, body.name_cs.strip(), (body.brand or "").strip() or None)
    except AutofillUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Autofill unavailable: {exc}") from None


@router.post("/foods", response_model=FoodRead, status_code=status.HTTP_201_CREATED)
def post_food(body: FoodCreate, session: SessionDep, background: BackgroundTasks) -> FoodRead:
    """Without `micro_refs` the food gets its micronutrient references in the background (E26)."""
    try:
        food = create_food(session, body)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A food with this barcode already exists") from None
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    if food.micros_status is None:
        background.add_task(mapper.map_in_background, [food.id])  # type: ignore[list-item]
    return read_food(session, food, with_portions=True)


@router.patch("/foods/{food_id}", response_model=FoodRead)
def patch_food(food_id: int, body: FoodUpdate, session: SessionDep) -> FoodRead:
    try:
        food = update_food(session, _food(session, food_id), body)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return read_food(session, food, with_portions=True)


@router.delete("/foods/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_food(food_id: int, session: SessionDep) -> Response:
    session.delete(_food(session, food_id))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "The food is used in logged meals") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/barcode/{ean}", response_model=FoodRead)
def barcode(ean: Annotated[str, Path(pattern=r"^[0-9]{6,14}$")], session: SessionDep, http: HttpDep) -> FoodRead:
    """Local food by EAN, else Open Food Facts (saved locally). 404 unknown; 422 when OFF lacks a required value,
    so the app can offer to complete it as a custom food."""
    if (food := session.exec(select(Food).where(Food.ean == ean)).first()) is not None:
        return read_food(session, food, with_portions=True)
    try:
        product = off.lookup_barcode(http, ean)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Open Food Facts unavailable: {exc}") from None
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown barcode")
    if not product.complete:
        detail = {"message": "Incomplete product", "name": product.name, "brand": product.brand, **product.values}
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)
    return read_food(session, off.save_product(session, product), with_portions=True)


@router.get("/profile", response_model=ProfileUpdate)
def get_profile(session: SessionDep) -> ProfileUpdate:
    profile = session.get(NutritionProfile, 1)
    return ProfileUpdate.model_validate(profile.model_dump() if profile else {})


@router.put("/profile", response_model=ProfileUpdate)
def put_profile(body: ProfileUpdate, session: SessionDep) -> ProfileUpdate:
    profile = session.get(NutritionProfile, 1) or NutritionProfile(id=1)
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    profile.updated_at = now_utc()
    session.add(profile)
    session.commit()
    return body


class DraftItem(BaseModel):
    input: MealItemInput
    candidate: CandidateIn
    amount_g: float = Field(gt=0, le=5000)


class MealDraftConfirm(BaseModel):
    """A meal draft the user confirmed, with the food chosen per item. The id is client-generated."""

    id: uuid.UUID
    date: dt.date | None = None
    meal_type: MealType = MealType.other
    raw_input: str | None = Field(default=None, max_length=4000)
    items: list[DraftItem] = Field(min_length=1, max_length=30)


@router.post("/drafts/confirm", response_model=MealRead)
def confirm_draft(body: MealDraftConfirm, session: SessionDep) -> MealRead:
    """Saves the meal and learns the mappings: both phrases of every item become confirmed aliases (E4, C6)."""
    day = body.date or today()
    if session.get(MealLog, body.id) is None:
        entries = []
        for item in body.items:
            candidate = Candidate(**item.candidate.model_dump())
            try:
                food = materialize(session, candidate, item.input)
            except (LookupError, ValueError) as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"Cannot use {candidate.ref}: {exc}"
                ) from None
            confirm_aliases(session, item.input, food)
            mapper.map_from_query(session, food, item.input.usda_query_en)  # a new OFF / web food: free mapping
            entries.append(MealEntry(item.input.user_phrase, food, item.amount_g))
        save_meal(
            session, meal_id=body.id, day=day, meal_type=body.meal_type, entries=entries, raw_input=body.raw_input
        )
    meal = session.get(MealLog, body.id)
    assert meal is not None
    return next(m for m in day_meals(session, meal.logged_date) if m.id == meal.id)


class KTImportRequest(BaseModel):
    date_from: dt.date
    date_to: dt.date | None = None  # default: yesterday (today is still being eaten)


class KTImportRead(BaseModel):
    configured: bool
    running: bool
    status: str
    range_from: dt.date | None
    range_to: dt.date | None
    next_day: dt.date | None
    days_done: int
    days_skipped: int
    items_imported: int
    foods_created: int
    weights_filled: int
    warnings: list[str]
    last_error: str | None


def _kt_read(session: SessionDep) -> KTImportRead:
    state = kt_import.get_state(session)
    configured = bool(settings.kaloricketabulky_email and settings.kaloricketabulky_password)
    return KTImportRead(
        configured=configured, running=kt_import.is_running(), **state.model_dump(exclude={"id", "updated_at"})
    )


@router.get("/import/kaloricke-tabulky", response_model=KTImportRead)
def kt_import_status(session: SessionDep) -> KTImportRead:
    return _kt_read(session)


@router.post("/import/kaloricke-tabulky", response_model=KTImportRead)
async def kt_import_start(body: KTImportRequest, session: SessionDep) -> KTImportRead:
    """Start (or resume, for the same range) the background import of KalorickéTabulky history."""
    if not (settings.kaloricketabulky_email and settings.kaloricketabulky_password):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Set KALORICKETABULKY_EMAIL and _PASSWORD in .env")
    if kt_import.is_running():
        raise HTTPException(status.HTTP_409_CONFLICT, "The import is already running")
    date_to = body.date_to or today() - dt.timedelta(days=1)
    if body.date_from > date_to or date_to >= today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Range must be in the past, from <= to")
    kt_import.prepare(session, body.date_from, date_to)
    start_kt_import()
    return _kt_read(session)


def start_kt_import() -> None:
    credentials = (settings.kaloricketabulky_email or "", settings.kaloricketabulky_password or "")
    kt_import.start_task(KaloricketabulkyClient(), lambda: Session(engine), credentials)


def _food(session: SessionDep, food_id: int) -> Food:
    food = session.get(Food, food_id)
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Food not found")
    return food


def _totals(items: list[MealItemRead]) -> Totals:
    def total(values: list[float | None]) -> float | None:
        known = [v for v in values if v is not None]
        return round(sum(known), 1) if known else None

    return Totals(
        kcal=round(sum(i.kcal for i in items), 1),
        protein_g=total([i.protein_g for i in items]),
        carbs_g=total([i.carbs_g for i in items]),
        fat_g=total([i.fat_g for i in items]),
    )
