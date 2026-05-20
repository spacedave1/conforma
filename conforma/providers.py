from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


def llm_provider(model: str, platform: str, **kwargs: Any):
    _load_dotenv()
    if platform == "fake":
        return FakeProvider(model)
    if platform == "openai":
        return OpenAIProvider(model, **kwargs)
    if platform == "gemini":
        return GeminiProvider(model, **kwargs)
    if platform == "lm_studio":
        return LMStudioProvider(model, **kwargs)
    raise ValueError(f"unknown platform: {platform}")


class FakeProvider:
    def __init__(self, model: str) -> None:
        self.model = model

    async def chat_completion(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "Fake free-form response."}}]}

    async def structured_completion(
        self,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        if "rule_checks" in response_schema.get("properties", {}):
            return {
                "data": {
                    "rule_checks": [
                        {
                            "rule": "The output should satisfy the contract.",
                            "verdict": "pass",
                            "evidence": "fake provider deterministic response",
                            "explanation": "The fake judge returns a stable passing result for smoke tests.",
                        }
                    ],
                    "overall": 100,
                    "rationale": "Fake judge smoke result.",
                }
            }
        return {"data": _fake_output_for_schema(response_schema)}


class OpenAIProvider:
    def __init__(self, model: str, **kwargs: Any) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Install OpenAI support with `pip install 'conforma[openai]'`.") from exc

        self.model = model
        client_kwargs = {
            key: kwargs[key]
            for key in ("api_key", "base_url", "timeout")
            if key in kwargs
        }
        self._client = OpenAI(**client_kwargs)

    async def chat_completion(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._client.chat.completions.create,
            model=self.model,
            messages=messages,
            temperature=0.0,
        )

    async def structured_completion(
        self,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        response = await asyncio.to_thread(
            self._client.chat.completions.create,
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "conforma_response",
                    "strict": False,
                    "schema": response_schema,
                },
            },
        )
        content = response.choices[0].message.content or "{}"
        return {"data": _parse_json_content(content)}


class GeminiProvider:
    def __init__(self, model: str, **kwargs: Any) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise ImportError("Install Gemini support with `pip install 'conforma[gemini]'`.") from exc

        aliases = {"fast": "GEMINI_FAST", "medium": "GEMINI_MEDIUM", "strong": "GEMINI_STRONG"}
        if model in aliases:
            env_key = aliases[model]
            model = os.environ.get(env_key, "")
            if not model:
                raise RuntimeError(f"{env_key} is not set")

        self.model = model
        self._client = genai.Client(api_key=kwargs.get("api_key") or os.environ.get("GEMINI_API_KEY"))

    async def chat_completion(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self.model,
            contents=_messages_to_text(messages),
            config={"temperature": 0.0},
        )
        return {"choices": [{"message": {"content": response.text or ""}}]}

    async def structured_completion(
        self,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self.model,
            contents=_messages_to_text(messages),
            config={
                "temperature": temperature,
                "response_mime_type": "application/json",
                "response_schema": _schema_for_gemini(response_schema),
            },
        )
        return {"data": _parse_json_content(response.text or "{}")}


def _fake_output_for_schema(schema: dict[str, Any]) -> Any:
    if schema.get("type") != "object":
        return {}
    output = {}
    properties = schema.get("properties", {})
    for key in schema.get("required", []):
        prop = properties.get(key, {})
        prop_type = prop.get("type")
        if "enum" in prop:
            output[key] = prop["enum"][0]
        elif prop_type == "array":
            min_items = int(prop.get("minItems", 1))
            output[key] = ["fake evidence"] * max(1, min_items)
        elif prop_type == "integer":
            output[key] = 50
        elif prop_type == "number":
            output[key] = 50.0
        elif prop_type == "boolean":
            output[key] = True
        elif prop_type == "object":
            output[key] = {}
        else:
            output[key] = "fake response"
    return output


def _messages_to_text(messages: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"{message.get('role', 'user').upper()}:\n{message.get('content', '')}"
        for message in messages
    )


def _parse_json_content(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _schema_for_gemini(schema: Any) -> Any:
    blocked = {"$schema", "additionalProperties"}
    if isinstance(schema, dict):
        return {
            key: _schema_for_gemini(value)
            for key, value in schema.items()
            if key not in blocked
        }
    if isinstance(schema, list):
        return [_schema_for_gemini(item) for item in schema]
    return schema


class LMStudioProvider(OpenAIProvider):
    def __init__(self, model: str, **kwargs: Any) -> None:
        base_url = str(kwargs.pop("base_url", "") or os.environ.get("LM_STUDIO_BASE_URL", "")).strip()
        if not base_url:
            raise RuntimeError("lm_studio requires LM_STUDIO_BASE_URL or config base_url")
        kwargs["base_url"] = base_url.rstrip("/")
        kwargs.setdefault("api_key", os.environ.get("LM_STUDIO_TOKEN") or "lm-studio")
        super().__init__(model, **kwargs)


def _load_dotenv() -> None:
    for candidate in (Path.cwd() / ".env", Path.cwd().parent / ".env"):
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
        return
