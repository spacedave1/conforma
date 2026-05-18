from __future__ import annotations

import asyncio
import json
import os
from typing import Any


def llm_provider(model: str, platform: str):
    if platform == "fake":
        return FakeProvider(model)
    if platform == "openai":
        return OpenAIProvider(model)
    if platform == "gemini":
        return GeminiProvider(model)
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
    def __init__(self, model: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Install OpenAI support with `pip install 'conforma[openai]'`.") from exc

        self.model = model
        self._client = OpenAI()

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
    def __init__(self, model: str) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise ImportError("Install Gemini support with `pip install 'conforma[gemini]'`.") from exc

        self.model = model
        self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

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

