from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def write_outputs(con: sqlite3.Connection, folder: Path, prompt_id: int) -> None:
    """Write all outputs from this invocation to outputs.md for easy reading."""
    cur = con.cursor()
    cur.execute("""
        SELECT r.model, s.label, r.output_json,
               j.overall_score, j.rationale
        FROM runs r
        JOIN samples s ON r.sample_id = s.id
        LEFT JOIN judge_runs j ON j.run_id = r.id
        WHERE r.prompt_id = ?
        ORDER BY r.id, j.id
    """, (prompt_id,))
    rows = cur.fetchall()

    lines = [f"# Outputs — prompt_id={prompt_id}\n"]
    seen: set[int] = set()
    for model, label, output_json, score, rationale in rows:
        key = (model, label)
        if key in seen:
            continue
        seen.add(key)
        output = json.loads(output_json)
        text = output if isinstance(output, str) else json.dumps(output, indent=2)
        lines.append(f"## {model} / {label}  (score={score})\n")
        lines.append(text)
        if rationale:
            lines.append(f"\n**Judge:** {rationale}")
        lines.append("\n---\n")

    out_path = folder / "outputs.md"
    out_path.write_text("\n".join(lines))
    print(f"Outputs: {out_path}")


def write_summary(con: sqlite3.Connection, folder: Path, prompt_id: int, schema_id: int, spec_id: int) -> None:
    """Append per-model aggregates for THIS invocation to <target>/summaries.json.
    Aggregate = mean overall_score across all (scenario × judge_rerun) rows that share this prompt_id."""
    cur = con.cursor()
    cur.execute("""
        SELECT r.model,
               p.captured_at,
               AVG(j.overall_score),
               COUNT(DISTINCT s.id),
               COUNT(j.id)
        FROM runs r
        JOIN prompts    p ON r.prompt_id = p.id
        JOIN samples    s ON r.sample_id = s.id
        JOIN judge_runs j ON j.run_id    = r.id
        WHERE r.prompt_id = ?
        GROUP BY r.model
        ORDER BY r.model
    """, (prompt_id,))
    rows = cur.fetchall()
    new_entries = []
    for model, captured_at, mean_score, n_scenarios, n_judge_runs in rows:
        new_entries.append({
            "invocation_id": prompt_id,
            "captured_at": captured_at,
            "model": model,
            "mean_score": round(float(mean_score), 2) if mean_score is not None else None,
            "n_scenarios": int(n_scenarios),
            "n_judge_runs": int(n_judge_runs),
            "prompt_id": prompt_id,
            "schema_id": schema_id,
            "spec_id": spec_id,
        })

    summary_path = folder / "summaries.json"
    existing: list = []
    if summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.extend(new_entries)
    summary_path.write_text(json.dumps(existing, indent=2))

