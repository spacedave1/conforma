import shutil
import sqlite3
from pathlib import Path

import pytest

from conforma.chart import load_series
from conforma.loader import load_target
from conforma.run import run_eval


ROOT = Path(__file__).parents[1]


def test_load_target_requires_prompt_md() -> None:
    target = load_target(ROOT / "examples" / "rag_grounded_answer")

    assert "retrieved context" in target["prompt_text"]
    assert target["prompt_yaml_key"] == "prompt.md"
    assert [sample["label"] for sample in target["samples"]] == [
        "answerable_with_caveat",
        "citation_trap",
        "conflicting_sources",
        "missing_context",
        "outdated_policy",
    ]
    assert [model["name"] for model in target["config"]["models_to_test"]] == [
        "gpt-5-mini",
        "gemini-3.1-flash-lite-preview",
    ]


@pytest.mark.asyncio
async def test_run_eval_preserves_original_artifacts(tmp_path) -> None:
    target_dir = tmp_path / "rag_grounded_answer"
    shutil.copytree(ROOT / "examples" / "rag_grounded_answer", target_dir)
    (target_dir / "config.yaml").write_text(
        """models_to_test:
  - name: fake
    platform: fake
    model: fake
judge_model:
  platform: fake
  model: fake-judge
runs_per_sample: 1
judge_runs_per_output: 1
"""
    )

    result = await run_eval(str(target_dir))

    assert result == 0
    assert (target_dir / "log.db").exists()
    assert (target_dir / "summaries.json").exists()
    assert (target_dir / "outputs.md").exists()
    assert (target_dir / "chart.png").exists()


@pytest.mark.asyncio
async def test_run_eval_filters_to_one_scenario(tmp_path) -> None:
    target_dir = tmp_path / "rag_grounded_answer"
    shutil.copytree(ROOT / "examples" / "rag_grounded_answer", target_dir)
    (target_dir / "config.yaml").write_text(
        """models_to_test:
  - name: fake
    platform: fake
    model: fake
judge_model:
  platform: fake
  model: fake-judge
runs_per_sample: 1
judge_runs_per_output: 0
"""
    )

    result = await run_eval(str(target_dir), scenario="citation_trap")

    assert result == 0
    con = sqlite3.connect(target_dir / "log.db")
    labels = [
        row[0]
        for row in con.execute(
            "SELECT label FROM samples ORDER BY id"
        )
    ]
    run_count = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    con.close()

    assert labels == ["citation_trap"]
    assert run_count == 1


def test_chart_series_groups_by_model_and_invocation(tmp_path) -> None:
    db = tmp_path / "log.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE prompts(id INTEGER PRIMARY KEY, captured_at TEXT);
        CREATE TABLE runs(id INTEGER PRIMARY KEY, prompt_id INTEGER, model TEXT);
        CREATE TABLE judge_runs(id INTEGER PRIMARY KEY, run_id INTEGER, overall_score INTEGER);
        INSERT INTO prompts(id, captured_at) VALUES
            (1, '2026-01-01T00:00:00+00:00'),
            (2, '2026-01-02T00:00:00+00:00');
        INSERT INTO runs(id, prompt_id, model) VALUES
            (1, 1, 'model-a'),
            (2, 1, 'model-a'),
            (3, 2, 'model-a'),
            (4, 2, 'model-b');
        INSERT INTO judge_runs(id, run_id, overall_score) VALUES
            (1, 1, 40),
            (2, 2, 60),
            (3, 3, 80),
            (4, 4, 30);
        """
    )
    con.close()

    series = load_series(db)

    assert [point[1] for point in series["model-a"]] == [50.0, 80.0]
    assert [point[1] for point in series["model-b"]] == [30.0]
