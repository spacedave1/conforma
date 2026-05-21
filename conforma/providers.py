from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
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
    if platform == "lm_studio_api":
        return LMStudioAPIProvider(model, **kwargs)
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
        response = await asyncio.to_thread(
            self._client.chat.completions.create,
            model=self.model,
            messages=messages,
            temperature=0.0,
        )
        return {
            "choices": [
                {
                    "message": {
                        "content": response.choices[0].message.content or "",
                    }
                }
            ]
        }

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
    json_start = min(
        [idx for idx in (text.find("{"), text.find("[")) if idx >= 0],
        default=-1,
    )
    if json_start > 0:
        text = text[json_start:].strip()
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
        base_url = base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3].rstrip("/")
        model = model or _loaded_lm_studio_chat_model(base_url)
        kwargs["base_url"] = f"{base_url}/v1"
        kwargs.setdefault("api_key", os.environ.get("LM_STUDIO_TOKEN") or "lm-studio")
        super().__init__(model, **kwargs)


class LMStudioAPIProvider:
    def __init__(self, model: str, **kwargs: Any) -> None:
        self.model = model
        self.last_stats: dict[str, Any] | None = None
        base_url = str(kwargs.pop("base_url", "") or os.environ.get("LM_STUDIO_BASE_URL", "")).strip()
        if not base_url:
            raise RuntimeError("lm_studio_api requires LM_STUDIO_BASE_URL or config base_url")
        base_url = base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3].rstrip("/")
        self.model = model or _loaded_lm_studio_chat_model(base_url)
        self._chat_url = f"{base_url}/api/v1/chat"
        self._api_key = str(kwargs.pop("api_key", "") or os.environ.get("LM_STUDIO_TOKEN", "")).strip()

    async def chat_completion(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self._payload_for_messages(messages)
        data = await asyncio.to_thread(self._post_chat, payload)
        self.last_stats = data.get("stats") if isinstance(data.get("stats"), dict) else None
        content = _lm_studio_api_content(data)
        return {"choices": [{"message": {"content": str(content)}}]}

    async def structured_completion(
        self,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        schema_instruction = (
            "Return only a JSON value that conforms to this JSON Schema. "
            "Do not include markdown fences, prose, explanations, or comments.\n\n"
            f"JSON Schema:\n{json.dumps(response_schema, indent=2)}"
        )
        payload = self._payload_for_messages([
            *messages,
            {"role": "system", "content": schema_instruction},
        ])
        data = await asyncio.to_thread(self._post_chat, payload)
        self.last_stats = data.get("stats") if isinstance(data.get("stats"), dict) else None
        content = _lm_studio_api_content(data)
        return {"data": _parse_json_content(content)}

    def _payload_for_messages(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        system_prompt = "\n\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        input_text = "\n\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") != "system"
        )
        return {
            "model": self.model,
            "system_prompt": system_prompt,
            "input": input_text,
        }

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._chat_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self._api_key:
            request.add_header("Authorization", f"Bearer {self._api_key}")
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LM Studio API request failed: HTTP {exc.code}: {detail}") from exc


def _lm_studio_api_content(data: dict[str, Any]) -> str:
    output = data.get("output")
    if isinstance(output, list):
        messages = [
            str(item.get("content") or "")
            for item in output
            if isinstance(item, dict) and item.get("type") == "message"
        ]
        content = "\n".join(message for message in messages if message.strip()).strip()
        if content:
            return content
    if isinstance(output, str) and output.strip():
        return output
    for key in ("content", "response"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    message = data.get("message")
    if isinstance(message, dict):
        value = message.get("content")
        if isinstance(value, str) and value.strip():
            return value
    raise RuntimeError(f"LM Studio API response did not contain message content: {data!r}")


def _loaded_lm_studio_chat_model(base_url: str) -> str:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/v0/models")
    token = os.environ.get("LM_STUDIO_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LM Studio model detection failed at {base_url}/api/v0/models: {exc}") from exc

    loaded_chat_models = [
        item.get("id")
        for item in data.get("data", [])
        if item.get("state") == "loaded"
        and item.get("type") in {"llm", "vlm"}
        and item.get("id")
    ]
    if not loaded_chat_models:
        raise RuntimeError(
            "lm_studio model is empty, but LM Studio has no loaded chat model. "
            "Load a local LLM in LM Studio or set model explicitly."
        )
    return str(loaded_chat_models[0])


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
