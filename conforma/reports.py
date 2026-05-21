from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def write_outputs(con: sqlite3.Connection, folder: Path, prompt_id: int) -> None:
    """Write all outputs from this invocation to outputs.md for easy reading."""
    cur = con.cursor()
    cur.execute("""
        SELECT r.model, s.label, r.output_json,
               rs.tokens_per_second, rs.total_output_tokens, rs.input_tokens,
               rs.time_to_first_token_seconds,
               j.overall_score, j.rationale
        FROM runs r
        JOIN samples s ON r.sample_id = s.id
        LEFT JOIN run_stats rs ON rs.run_id = r.id
        LEFT JOIN judge_runs j ON j.run_id = r.id
        WHERE r.prompt_id = ?
        ORDER BY r.id, j.id
    """, (prompt_id,))
    rows = cur.fetchall()

    lines = [f"# Outputs — prompt_id={prompt_id}\n"]
    seen: set[int] = set()
    for (
        model, label, output_json,
        tokens_per_second, total_output_tokens, input_tokens,
        time_to_first_token_seconds,
        score, rationale,
    ) in rows:
        key = (model, label)
        if key in seen:
            continue
        seen.add(key)
        output = json.loads(output_json)
        text = output if isinstance(output, str) else json.dumps(output, indent=2)
        lines.append(f"## {model} / {label}  (score={score})\n")
        stats_line = _format_stats(
            tokens_per_second=tokens_per_second,
            total_output_tokens=total_output_tokens,
            input_tokens=input_tokens,
            time_to_first_token_seconds=time_to_first_token_seconds,
        )
        if stats_line:
            lines.append(stats_line)
            lines.append("")
        lines.append(text)
        if rationale:
            lines.append(f"\n**Judge:** {rationale}")
        lines.append("\n---\n")

    out_path = folder / "outputs.md"
    out_path.write_text("\n".join(lines))
    print(f"Outputs: {out_path}")


def _format_stats(
    *,
    tokens_per_second,
    total_output_tokens,
    input_tokens,
    time_to_first_token_seconds,
) -> str:
    parts = []
    if tokens_per_second is not None:
        parts.append(f"tokens_per_second={float(tokens_per_second):.2f}")
    if total_output_tokens is not None:
        parts.append(f"total_output_tokens={int(total_output_tokens)}")
    if input_tokens is not None:
        parts.append(f"input_tokens={int(input_tokens)}")
    if time_to_first_token_seconds is not None:
        parts.append(f"time_to_first_token_seconds={float(time_to_first_token_seconds):.3f}")
    return f"**Run stats:** {', '.join(parts)}" if parts else ""


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
