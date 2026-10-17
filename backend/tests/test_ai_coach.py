"""Coach chat and voice routes against a fake Gemini client that runs the real tools (no network)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fakes import FakeGemini
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from app.config import settings
from app.main import app
from app.routers.ai_coach import gemini_client
from app.services.ai_tools import SetInput

# 1 s synthetic tones in the formats phones record: Chrome webm/Opus, Safari fragmented mp4/AAC
FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.mark.parametrize(
    ("fixture", "mime_type"),
    [("recording-chrome.webm", "audio/webm;codecs=opus"), ("recording-safari.mp4", "audio/mp4")],
)
def test_voice_recording_is_transcoded_for_gemini(client: TestClient, fake, fixture: str, mime_type: str) -> None:
    gemini = fake()
    recording = (FIXTURES / fixture).read_bytes()

    response = client.post(
        "/api/ai/voice-workout", files={"audio": (fixture, recording, mime_type)}, data={"text": "bench"}
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
