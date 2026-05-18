import sys
import types

import pytest

from conforma.providers import GeminiProvider, OpenAIProvider


@pytest.mark.asyncio
async def test_openai_provider_structured_completion(monkeypatch) -> None:
    captured = {}

    class ChatCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content='{"answer": "ok"}')
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    class OpenAI:
        def __init__(self):
            self.chat = types.SimpleNamespace(completions=ChatCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))

    provider = OpenAIProvider("test-openai")
    result = await provider.structured_completion(
        messages=[{"role": "user", "content": "Return ok."}],
        response_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    )

    assert result == {"data": {"answer": "ok"}}
    assert captured["model"] == "test-openai"
    assert captured["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_gemini_provider_structured_completion_sanitizes_schema(monkeypatch) -> None:
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text='{"answer": "ok"}')

    class Client:
        def __init__(self, api_key=None):
            self.models = Models()

    google_module = types.ModuleType("google")
    genai_module = types.SimpleNamespace(Client=Client)
    google_module.genai = genai_module
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)

    provider = GeminiProvider("test-gemini")
    result = await provider.structured_completion(
        messages=[{"role": "user", "content": "Return ok."}],
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    )

    assert result == {"data": {"answer": "ok"}}
    assert captured["model"] == "test-gemini"
    assert captured["config"]["response_mime_type"] == "application/json"
    assert "additionalProperties" not in str(captured["config"]["response_schema"])

