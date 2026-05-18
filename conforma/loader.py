from __future__ import annotations

import json
from pathlib import Path

import yaml


def load_target(folder: Path) -> dict:
    config = yaml.safe_load((folder / "config.yaml").read_text())
    spec = (folder / "spec.md").read_text()
    schema_path = folder / "schema.json"
    schema = json.loads(schema_path.read_text()) if schema_path.exists() else None

    scenarios_dir = folder / "scenarios"
    scenarios: list[dict] = []
    if scenarios_dir.is_dir():
        for p in sorted(scenarios_dir.glob("*.json")):
            messages = json.loads(p.read_text())
            scenarios.append({"label": p.stem, "messages": messages})

    prompt_path = folder / "prompt.md"
    prompt_text = prompt_path.read_text()

    return {
        "config": config,
        "spec": spec,
        "schema": schema,
        "samples": scenarios,
        "prompt_text": prompt_text,
        "prompt_yaml_path": str(prompt_path),
        "prompt_yaml_key": "prompt.md",
    }

