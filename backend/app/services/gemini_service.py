"""Shared google-genai runner for the assistants (coach now, nutrition in Phase 5).

Uses the chat API with automatic function calling (the SDK's recommended path for AFC); prior turns come
from the database as text-only history.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from google import genai
from google.genai import types

from app.config import settings

Tier = Literal["fast", "smart"]
MAX_TOOL_CALLS_PER_TURN = 10


class AINotConfiguredError(RuntimeError):
    pass


@dataclass
class AssistantReply:
    reply: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{"name": ..., "args": {...}}]
    model: str | None = None


def get_client() -> genai.Client:
    """FastAPI dependency; tests override it with a fake client."""
    if not settings.gemini_api_key:
        raise AINotConfiguredError("Set GEMINI_API_KEY")
    return genai.Client(api_key=settings.gemini_api_key)


def tier_settings(tier: Tier) -> tuple[str, str | None]:
    """(model id, thinking level) for a tier; the smart tier falls back to the fast model."""
    fast = settings.gemini_model_fast
    model = fast if tier == "fast" else (settings.gemini_model_smart or fast)
    if not model:
        raise AINotConfiguredError("Set GEMINI_MODEL_FAST (and optionally GEMINI_MODEL_SMART)")
    level = settings.gemini_thinking_fast if tier == "fast" else settings.gemini_thinking_smart
    return model, (level or None)


def history_content(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


def run_assistant(
    client: genai.Client,
    *,
    system_instruction: str,
    tools: list[Any],
    history: list[types.Content],
    parts: list[types.Part],
    tier: Tier = "fast",
) -> AssistantReply:
    model, thinking_level = tier_settings(tier)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools,
        temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=MAX_TOOL_CALLS_PER_TURN),
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level.upper()) if thinking_level else None,
    )
    chat = client.chats.create(model=model, config=config, history=history)
    response = chat.send_message(parts)
    # History turns are text-only, so every function call in the AFC history belongs to this turn
    tool_calls = [
        {"name": part.function_call.name, "args": dict(part.function_call.args or {})}
        for content in (response.automatic_function_calling_history or [])
        for part in (content.parts or [])
        if part.function_call
    ]
    return AssistantReply(reply=(response.text or "").strip(), tool_calls=tool_calls, model=response.model_version)
