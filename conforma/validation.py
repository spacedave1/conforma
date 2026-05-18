from __future__ import annotations

from typing import Any


def validate_structural(output: Any, schema: dict | None) -> tuple[bool, list[str]]:
    """jsonschema validation if available; minimal required-keys check otherwise.
    If schema is None (free-form mode), always passes."""
    if schema is None:
        return True, []
    try:
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(schema)
        errors = [e.message for e in validator.iter_errors(output)]
        return (len(errors) == 0, errors)
    except ImportError:
        required = schema.get("required", [])
        errors = [
            f"missing required key: {k}"
            for k in required
            if not isinstance(output, dict) or k not in output
        ]
        return (len(errors) == 0, errors)

