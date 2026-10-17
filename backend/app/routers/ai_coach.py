import datetime as dt
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.database import SessionDep
from app.models.chat import ChatConversation, ChatMessage
from app.models.gym import Exercise
from app.services import gemini_service
from app.services.ai_tools import SetInput, save_sets, target_workout
from app.services.audio import AudioError, prepare_audio
from app.services.coach import CoachTurn, coach_turn
from app.services.gemini_service import AINotConfiguredError, Tier
from app.timeutils import now_utc

router = APIRouter(prefix="/api/ai", tags=["ai"])

VOICE_INSTRUCTION = (
    "Zpracuj tuto hlasovou nahrávku z tréninku: zapiš odcvičené série nástrojem a stručně potvrď, "
    "co je uložené a co čeká na potvrzení."
)


def gemini_client() -> genai.Client:
    try:
        return gemini_service.get_client()
    except AINotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None


GeminiDep = Annotated[genai.Client, Depends(gemini_client)]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    model: Tier = "fast"
    conversation_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: uuid.UUID
    tool_calls_made: list[str]
    drafts: list[dict[str, Any]]
    saved_sets: list[dict[str, Any]]
    model: str | None


class MessageRead(BaseModel):
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None
    created_at: dt.datetime


class ConversationRead(BaseModel):
    id: uuid.UUID
    assistant: str
    messages: list[MessageRead]


def run_gemini[T](run: Callable[[], T]) -> T:
    """Run an assistant turn, mapping configuration and Gemini errors to HTTP statuses (shared by both assistants)."""
    try:
        return run()
    except AINotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except genai_errors.ClientError as exc:
        if exc.code == 429:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Gemini quota exceeded, try again later") from None
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Gemini rejected the request: {exc.message}") from None
    except genai_errors.APIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Gemini error: {exc.message}") from None


def audio_part(audio: UploadFile) -> types.Part:
    """A browser recording as a Gemini part (transcoded when Gemini can't read the format)."""
    try:
        data, mime_type = prepare_audio(audio.file.read(), audio.content_type)
    except AudioError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def _respond(run: Callable[[], CoachTurn]) -> ChatResponse:
    turn = run_gemini(run)
    return ChatResponse(
        reply=turn.reply,
        conversation_id=turn.conversation_id,
        tool_calls_made=turn.tool_calls_made,
        drafts=turn.drafts,
        saved_sets=turn.saved_sets,
        model=turn.model,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, session: SessionDep, client: GeminiDep) -> ChatResponse:
    return _respond(
        lambda: coach_turn(
            session, client, user_text=body.message, conversation_id=body.conversation_id, tier=body.model
        )
    )


@router.post("/voice-workout", response_model=ChatResponse)
def voice_workout(
    session: SessionDep,
    client: GeminiDep,
    audio: Annotated[UploadFile | None, File(description="Recording from MediaRecorder")] = None,
    text: Annotated[str | None, Form(max_length=4000)] = None,
    workout_id: Annotated[uuid.UUID | None, Form()] = None,
    conversation_id: Annotated[uuid.UUID | None, Form()] = None,
    model: Annotated[Tier, Form()] = "fast",
) -> ChatResponse:
    """Dictated sets as audio (Czech/English) or text; sets are saved or returned as drafts (hybrid flow)."""
    if audio is None and not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send audio or text")
    extra_parts = [audio_part(audio)] if audio is not None else []
    user_text = f"{VOICE_INSTRUCTION}\n{text}" if text and audio is not None else (text or VOICE_INSTRUCTION)
    stored = f"🎤 [hlasová nahrávka]{' ' + text if text else ''}" if audio is not None else text
    return _respond(
        lambda: coach_turn(
            session,
            client,
            user_text=user_text,
            stored_text=stored,
            extra_parts=extra_parts,
            conversation_id=conversation_id,
            workout_id=workout_id,
            tier=model,
        )
    )


class DraftConfirm(BaseModel):
    """A dictated-sets draft the user confirmed in the app, with the exercise they picked."""

    exercise_id: int
    sets: list[SetInput] = Field(min_length=1, max_length=20)
    workout_id: uuid.UUID | None = None


@router.post("/drafts/confirm")
def confirm_draft(body: DraftConfirm, session: SessionDep) -> dict[str, Any]:
    exercise = session.get(Exercise, body.exercise_id)
    if exercise is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown exercise")
    now = now_utc()
    target = target_workout(session, now, str(body.workout_id) if body.workout_id else None)
    return save_sets(session, exercise, body.sets, target, now)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: uuid.UUID, session: SessionDep) -> ConversationRead:
    conversation = session.get(ChatConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(col(ChatMessage.id))
    ).all()
    return ConversationRead(
        id=conversation.id,
        assistant=conversation.assistant,
        messages=[
            MessageRead(role=m.role, content=m.content, tool_calls=m.tool_calls, created_at=m.created_at)
            for m in messages
        ],
    )
