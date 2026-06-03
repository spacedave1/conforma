from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def llm_provider(model: str, platform: str, **_: Any):
    _load_dotenv()
    if platform == "fake":
        return FakeProvider(model)
    raise RuntimeError(
        "No provider factory was supplied. Pass provider_factory to run_eval "
        "or use platform: fake for local smoke tests."
    )


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
        **_: Any,
    ) -> dict[str, Any]:
        if "rule_checks" in response_schema.get("properties", {}):
            return {"data": {
                "rule_checks": [{
                    "rule": "The output should satisfy the contract.",
                    "verdict": "pass",
                    "evidence": "fake provider deterministic response",
                    "explanation": "The fake judge returns a stable passing result for smoke tests.",
                }],
                "overall": 100,
                "rationale": "Fake judge smoke result.",
            }}
        return {"data": _fake_output_for_schema(response_schema)}


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
