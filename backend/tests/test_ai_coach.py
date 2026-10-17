"""Coach chat and voice routes against a fake Gemini client that runs the real tools (no network)."""

import subprocess
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from google.genai import types

from app.config import settings
from app.main import app
from app.routers.ai_coach import gemini_client
from app.services.ai_tools import SetInput


class FakeChat:
    """Mimics google-genai chat AFC: tools run inside send_message and every round lands in the chat history
    (the response itself carries no function-call history)."""

    def __init__(self, client: "FakeGemini", config: types.GenerateContentConfig, history: list[types.Content]):
        self.client, self.tools = client, {fn.__name__: fn for fn in config.tools or []}
        self.history = list(history)

    def get_history(self, curated: bool = False) -> list[types.Content]:
        return self.history

    def send_message(self, parts: list[types.Part]) -> SimpleNamespace:
        self.client.sent.append(parts)
        if self.client.error:
            raise self.client.error
        self.history.append(types.Content(role="user", parts=parts))
        for name, kwargs in self.client.calls:  # what automatic function calling would do
            result = self.tools[name](**kwargs)
            self.client.results.append(result)
            self.history.append(types.Content(role="model", parts=[types.Part.from_function_call(name=name, args={})]))
            self.history.append(
                types.Content(role="user", parts=[types.Part.from_function_response(name=name, response=result)])
            )
        self.history.append(types.Content(role="model", parts=[types.Part.from_text(text=self.client.reply)]))
        return SimpleNamespace(text=self.client.reply, model_version="fake-1")


class FakeGemini:
    def __init__(self, reply: str = "Hotovo.", calls: list[tuple[str, dict[str, Any]]] | None = None):
        self.reply, self.calls, self.error = reply, calls or [], None
        self.created: list[dict[str, Any]] = []
        self.sent: list[list[types.Part]] = []
        self.results: list[Any] = []
        self.chats = SimpleNamespace(create=self._create)

    def _create(self, model: str, config: types.GenerateContentConfig, history: list[types.Content]) -> FakeChat:
        self.created.append({"model": model, "config": config, "history": history})
        return FakeChat(self, config, history)


@pytest.fixture(autouse=True)
def models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gemini_model_fast", "fast-model")
    monkeypatch.setattr(settings, "gemini_model_smart", None)


@pytest.fixture
def fake(exercises: dict[str, int]) -> Callable[..., FakeGemini]:
    def make(**kwargs) -> FakeGemini:
        client = FakeGemini(**kwargs)
        app.dependency_overrides[gemini_client] = lambda: client
        return client

    return make


def test_chat_runs_tools_and_persists_the_conversation(client: TestClient, fake) -> None:
    gemini = fake(reply="Dnes je sobota.", calls=[("get_calendar", {"days": 1})])

    first = client.post("/api/ai/chat", json={"message": "Jaký je dnes den?"}).json()
    client.post("/api/ai/chat", json={"message": "A zítra?", "conversation_id": first["conversation_id"]})

    assert first["reply"] == "Dnes je sobota."
    assert first["tool_calls_made"] == ["get_calendar"]
    assert first["model"] == "fake-1"
    second_history = gemini.created[1]["history"]
    assert [(c.role, c.parts[0].text) for c in second_history] == [
        ("user", "Jaký je dnes den?"),
        ("model", "Dnes je sobota."),
    ]
    conversation = client.get(f"/api/ai/conversations/{first['conversation_id']}").json()
    assert [m["role"] for m in conversation["messages"]] == ["user", "model", "user", "model"]
    assert conversation["messages"][1]["tool_calls"] == [{"name": "get_calendar", "args": {}}]


def test_system_instruction_has_today_and_exercise_names(client: TestClient, fake) -> None:
    gemini = fake()

    client.post("/api/ai/chat", json={"message": "Ahoj"})

    instruction = gemini.created[0]["config"].system_instruction
    assert "Dnes je" in instruction
    assert "- Bench Press (Barbell) [chest]" in instruction


def test_tiers_pick_model_and_thinking(client: TestClient, fake, monkeypatch: pytest.MonkeyPatch) -> None:
    gemini = fake()
    client.post("/api/ai/chat", json={"message": "x", "model": "smart"})
    monkeypatch.setattr(settings, "gemini_model_smart", "smart-model")
    client.post("/api/ai/chat", json={"message": "x", "model": "smart"})
    client.post("/api/ai/chat", json={"message": "x"})

    used = [(c["model"], c["config"].thinking_config.thinking_level) for c in gemini.created]
    assert used == [("fast-model", "HIGH"), ("smart-model", "HIGH"), ("fast-model", "LOW")]


def test_drafts_and_saved_sets_are_returned(client: TestClient, fake) -> None:
    fake(
        calls=[
            ("log_workout_sets_from_ai", {"exercise_name": "Pull Up", "sets": [SetInput(weight_kg=0, reps=10)]}),
            ("log_workout_sets_from_ai", {"exercise_name": "kelso šrag", "sets": [SetInput(weight_kg=60, reps=10)]}),
        ]
    )

    result = client.post("/api/ai/chat", json={"message": "Shyby 10, kelso šrag 60 na 10"}).json()

    assert result["saved_sets"][0]["exercise"] == "Pull Up"
    assert result["drafts"][0]["reason"] == "exercise_uncertain"
    assert result["drafts"][0]["candidates"][0]["name"] == "Kelso Shrug"


def test_voice_recording_is_transcoded_for_gemini(client: TestClient, fake) -> None:
    gemini = fake()
    webm = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "libopus",
            "-f",
            "webm",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout

    response = client.post(
        "/api/ai/voice-workout", files={"audio": ("rec.webm", webm, "audio/webm;codecs=opus")}, data={"text": "bench"}
    )

    assert response.status_code == 200, response.text
    audio_part, text_part = gemini.sent[0]
    assert audio_part.inline_data.mime_type == "audio/flac"
    assert audio_part.inline_data.data[:4] == b"fLaC"
    assert "hlasovou nahrávku" in text_part.text


def test_voice_needs_audio_or_text(client: TestClient, fake) -> None:
    fake()

    assert client.post("/api/ai/voice-workout").status_code == 422


def test_quota_errors_become_429(client: TestClient, fake) -> None:
    gemini = fake()
    gemini.error = genai_errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )

    assert client.post("/api/ai/chat", json={"message": "x"}).status_code == 429


def test_missing_model_config_is_503(client: TestClient, fake, monkeypatch: pytest.MonkeyPatch) -> None:
    fake()
    monkeypatch.setattr(settings, "gemini_model_fast", None)

    assert client.post("/api/ai/chat", json={"message": "x"}).status_code == 503


def test_confirming_a_draft_saves_the_sets_with_the_chosen_exercise(
    client: TestClient, exercises: dict[str, int]
) -> None:
    body = {
        "exercise_id": exercises["Kelso Shrug"],
        "sets": [{"weight_kg": 60, "reps": 10}, {"weight_kg": 60, "reps": 8}],
    }

    first = client.post("/api/ai/drafts/confirm", json=body).json()
    second = client.post("/api/ai/drafts/confirm", json=body).json()

    assert first["sets_saved"] == 2 and first["exercise"] == "Kelso Shrug"
    assert second["workout_id"] == first["workout_id"]  # appended to the same open workout
    workout = client.get(f"/api/workouts/{first['workout_id']}").json()
    assert [(s["exercise_order"], s["set_order"]) for s in workout["sets"]] == [(1, 1), (1, 2), (1, 3), (1, 4)]
