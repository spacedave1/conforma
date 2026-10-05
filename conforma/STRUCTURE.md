---
generated: 2026-10-05T12:09:09+00:00
module: conforma
---

# conforma

## Files
- `__init__.py` — Conforma — spec-conformance evaluation and run logs for LLM prompts.
- `chart.py` — Chart per-model judge scores over time for one target folder.
- `judge.py`
- `loader.py`
- `providers.py`
- `reports.py`
- `run.py`
- `store.py`
- `validation.py`

## Classes
### FakeProvider
_defined in `providers.py`_

- `chat_completion(messages: list[dict[str, Any]]) -> dict[str, Any]`
- `structured_completion(messages: list[dict[str, Any]], response_schema: dict[str, Any], temperature: float = 0.0, **_: Any) -> dict[str, Any]`

## Functions
- `build_judge_messages(spec: str, output: Any) -> list[dict]` _judge.py_
- `init_db(path: Path) -> sqlite3.Connection` _store.py_
- `judge_output(judge_llm, spec: str, output: Any)` _judge.py_
- `llm_provider(model: str, platform: str, **_: Any)` _providers.py_
- `load_series(db_path: Path) -> dict[str, list[tuple[datetime, float, int]]]` _chart.py_ — Returns {model: [(invocation_timestamp, mean_score_across_scenarios, n_judge_runs), ...]}
- `load_target(folder: Path)` _loader.py_
- `main() -> int` (`chart.py`)
- `main() -> int` (`run.py`)
- `now_iso() -> str` _store.py_
- `persist_inputs(con: sqlite3.Connection, target: dict) -> tuple[int, int, int, int]` _store.py_
- `persist_samples(con: sqlite3.Connection, samples: list[dict]) -> list[int]` _store.py_
- `print_judge_result(judge_index: int, jres: dict)` _reports.py_ — Print a judge score, rule counts, and a brief rationale.
- `refresh_chart(folder: Path)` _chart.py_ — Refresh the history chart and report an unavailable chart dependency.
- `render(series, out_path: Path) -> None` _chart.py_
- `run_eval(target_folder: str, scenario: str | None = None, provider_factory=None) -> int` _run.py_
- `validate_structural(output: Any, schema: dict | None)` _validation.py_ — jsonschema validation if available; minimal required-keys check otherwise.
- `write_outputs(con: sqlite3.Connection, folder: Path, prompt_id: int)` _reports.py_ — Write all outputs from this invocation to outputs.md for easy reading.
- `write_summary(con: sqlite3.Connection, folder: Path, prompt_id: int, schema_id: int, spec_id: int)` _reports.py_ — Append per-model aggregates for THIS invocation to <target>/summaries.json.

## Docstring Issues
- `main()` `chart.py` — missing
- `render()` `chart.py` — missing
- `build_judge_messages()` `judge.py` — missing
- `judge_output()` `judge.py` — missing
- `load_target()` `loader.py` — missing
- `FakeProvider.chat_completion()` `providers.py` — missing
- `FakeProvider.structured_completion()` `providers.py` — missing
- `llm_provider()` `providers.py` — missing
- class `FakeProvider` `providers.py` — missing
- `main()` `run.py` — missing
- `run_eval()` `run.py` — missing
- `init_db()` `store.py` — missing
- `now_iso()` `store.py` — missing
- `persist_inputs()` `store.py` — missing
- `persist_samples()` `store.py` — missing
