"""Fake google-genai client shared by the assistant tests: it runs the real tools, no network."""

from types import SimpleNamespace
from typing import Any

from google.genai import types


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
        # One-shot calls (nutrition chooser, web estimate): scripted responses, popped in order
        self.generated: list[dict[str, Any]] = []
        self.generate_responses: list[Any] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _create(self, model: str, config: types.GenerateContentConfig, history: list[types.Content]) -> FakeChat:
        self.created.append({"model": model, "config": config, "history": history})
        return FakeChat(self, config, history)

    def _generate(self, model: str, contents: Any, config: types.GenerateContentConfig) -> Any:
        self.generated.append({"model": model, "contents": contents, "config": config})
        if not self.generate_responses:
            raise RuntimeError("no scripted generate_content response")
        response = self.generate_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
