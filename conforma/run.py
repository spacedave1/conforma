from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

from conforma.judge import judge_output
from conforma.loader import load_target
from conforma.providers import llm_provider
from conforma.reports import write_outputs, write_summary
from conforma.store import init_db, now_iso, persist_inputs, persist_samples
from conforma.validation import validate_structural


async def run_eval(target_folder: str) -> int:
    folder = Path(target_folder)
    if not folder.is_dir():
        print(f"ERROR: target folder not found: {folder}", file=sys.stderr)
        return 2

    target = load_target(folder)
    if not target["samples"]:
        print(f"No scenarios in {folder/'scenarios'}/. Drop json files (each = list of messages) there first.")
        return 0

    con = init_db(folder / "log.db")
    prompt_id, schema_id, spec_id, judge_config_id = persist_inputs(con, target)
    sample_ids = persist_samples(con, target["samples"])

    config = target["config"]
    models = config["models_to_test"]
    judge_cfg = config["judge_model"]
    runs_per_sample = int(config.get("runs_per_sample", 1))
    judge_runs_per_output = int(config.get("judge_runs_per_output", 3))
    judge_timeout_seconds = float(config.get("judge_timeout_seconds", 120))
    target_timeout_seconds = float(config.get("target_timeout_seconds", 120))

    judge_llm = llm_provider(model=judge_cfg["model"], platform=judge_cfg["platform"], **_provider_kwargs(judge_cfg))
    resolved_judge_model = getattr(judge_llm, "model", None) or judge_cfg["model"]

    print(f"Target: {folder}", flush=True)
    print(f"  prompt: {target['prompt_yaml_path']} key={target['prompt_yaml_key']}", flush=True)
    print(f"  samples: {len(target['samples'])}", flush=True)
    print(f"  models to test: {[m['name'] for m in models]}", flush=True)
    print(f"  judge: {judge_cfg}", flush=True)
    print(flush=True)

    judge_tasks: list[asyncio.Task[None]] = []
    db_lock = asyncio.Lock()
    for model_cfg in models:
        name = model_cfg["name"]
        target_llm = llm_provider(model=model_cfg["model"], platform=model_cfg["platform"], **_provider_kwargs(model_cfg))
        resolved_model = getattr(target_llm, "model", None) or name
        print(f"=== Model: {name}  ({resolved_model}) ===", flush=True)
        for sample, sample_id in zip(target["samples"], sample_ids):
            await _run_sample(
                con=con,
                target=target,
                sample=sample,
                sample_id=sample_id,
                target_llm=target_llm,
                resolved_model=resolved_model,
                judge_llm=judge_llm,
                resolved_judge_model=resolved_judge_model,
                prompt_id=prompt_id,
                schema_id=schema_id,
                spec_id=spec_id,
                judge_config_id=judge_config_id,
                runs_per_sample=runs_per_sample,
                target_timeout_seconds=target_timeout_seconds,
                judge_runs_per_output=judge_runs_per_output,
                judge_timeout_seconds=judge_timeout_seconds,
                judge_tasks=judge_tasks,
                db_lock=db_lock,
            )

    if judge_tasks:
        print(f"\nWaiting for {len(judge_tasks)} judge run(s)...", flush=True)
        await asyncio.gather(*judge_tasks)

    write_summary(con, folder, prompt_id, schema_id, spec_id)
    write_outputs(con, folder, prompt_id)
    con.close()
    _refresh_chart(folder)

    print(f"\nDone. Run log: {folder/'log.db'}  Summary: {folder/'summaries.json'}", flush=True)
    return 0


async def _run_sample(
    con: sqlite3.Connection,
    target: dict,
    sample: dict,
    sample_id: int,
    target_llm,
    resolved_model: str,
    judge_llm,
    resolved_judge_model: str,
    prompt_id: int,
    schema_id: int,
    spec_id: int,
    judge_config_id: int,
    runs_per_sample: int,
    target_timeout_seconds: float,
    judge_runs_per_output: int,
    judge_timeout_seconds: float,
    judge_tasks: list[asyncio.Task[None]],
    db_lock: asyncio.Lock,
) -> None:
    label = sample.get("label", f"sample_{sample_id}")
    for run_n in range(runs_per_sample):
        full_messages = [{"role": "system", "content": target["prompt_text"]}] + sample["messages"]
        print(f"  [{label} run {run_n+1}] target start", flush=True)
        try:
            if target["schema"] is None:
                resp = await asyncio.wait_for(
                    target_llm.chat_completion(messages=full_messages),
                    timeout=target_timeout_seconds,
                )
                output = resp["choices"][0]["message"]["content"]
            else:
                raw = await asyncio.wait_for(
                    target_llm.structured_completion(
                        messages=full_messages,
                        response_schema=target["schema"],
                        temperature=0.0,
                    ),
                    timeout=target_timeout_seconds,
                )
                output = raw["data"] if isinstance(raw, dict) and "data" in raw else raw
        except asyncio.TimeoutError:
            print(
                f"  [{label} run {run_n+1}] target error: timed out after {target_timeout_seconds:g}s",
                flush=True,
            )
            continue
        except Exception as e:
            print(f"  [{label} run {run_n+1}] target error: {e}", flush=True)
            continue

        ok, errors = validate_structural(output, target["schema"])
        cur = con.cursor()
        cur.execute(
            """INSERT INTO runs(prompt_id, schema_id, spec_id, sample_id, model,
               output_json, parse_ok, structural_errors, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (prompt_id, schema_id, spec_id, sample_id, resolved_model,
             json.dumps(output), int(ok), json.dumps(errors), now_iso()),
        )
        run_id = cur.lastrowid
        stats = getattr(target_llm, "last_stats", None)
        if isinstance(stats, dict):
            cur.execute(
                """INSERT OR REPLACE INTO run_stats(
                   run_id, stats_json, tokens_per_second, total_output_tokens,
                   input_tokens, time_to_first_token_seconds
                   ) VALUES (?,?,?,?,?,?)""",
                (
                    run_id,
                    json.dumps(stats),
                    _optional_float(stats.get("tokens_per_second")),
                    _optional_int(stats.get("total_output_tokens")),
                    _optional_int(stats.get("input_tokens")),
                    _optional_float(stats.get("time_to_first_token_seconds")),
                ),
            )
        con.commit()
        print(f"  [{label} run {run_n+1}] structural_ok={ok} errors={len(errors)}{_stats_suffix(stats)}", flush=True)

        for j in range(judge_runs_per_output):
            judge_tasks.append(asyncio.create_task(_run_judge(
                con=con,
                db_lock=db_lock,
                judge_llm=judge_llm,
                spec=target["spec"],
                output=output,
                run_id=run_id,
                judge_index=j + 1,
                resolved_judge_model=resolved_judge_model,
                judge_config_id=judge_config_id,
                label=label,
                timeout_seconds=judge_timeout_seconds,
            )))


async def _run_judge(
    *,
    con: sqlite3.Connection,
    db_lock: asyncio.Lock,
    judge_llm,
    spec: str,
    output,
    run_id: int,
    judge_index: int,
    resolved_judge_model: str,
    judge_config_id: int,
    label: str,
    timeout_seconds: float,
) -> None:
    try:
        jres = await asyncio.wait_for(
            judge_output(judge_llm, spec, output),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        print(f"    [{label}] judge {judge_index} timeout after {timeout_seconds:g}s")
        return
    except Exception as e:
        print(f"    [{label}] judge {judge_index} error: {e}")
        return
    async with db_lock:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO judge_runs(run_id, judge_model, overall_score,
               rationale, timestamp, judge_config_id)
               VALUES (?,?,?,?,?,?)""",
            (run_id, resolved_judge_model, int(jres["overall"]),
             jres.get("rationale", ""), now_iso(), judge_config_id),
        )
        con.commit()
    print(f"    [{label}] ", end="")
    _print_judge_result(judge_index, jres)


def _print_judge_result(judge_index: int, jres: dict) -> None:
    rat = jres.get("rationale", "").replace("\n", " ")
    if len(rat) > 140:
        rat = rat[:137] + "..."
    checks = jres.get("rule_checks", []) or []
    n_pass = sum(1 for c in checks if c.get("verdict") == "pass")
    n_fail = sum(1 for c in checks if c.get("verdict") == "fail")
    print(f"    judge {judge_index}: overall={jres['overall']} ({n_pass} pass, {n_fail} fail)  {rat}")


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stats_suffix(stats) -> str:
    if not isinstance(stats, dict):
        return ""
    parts = []
    tps = _optional_float(stats.get("tokens_per_second"))
    if tps is not None:
        parts.append(f"{tps:.1f} tok/s")
    total = _optional_int(stats.get("total_output_tokens"))
    if total is not None:
        parts.append(f"{total} output tok")
    ttft = _optional_float(stats.get("time_to_first_token_seconds"))
    if ttft is not None:
        parts.append(f"{ttft:.2f}s ttft")
    return f" ({', '.join(parts)})" if parts else ""


def _refresh_chart(folder: Path) -> None:
    try:
        from conforma.chart import load_series, render

        chart_out = folder / "chart.png"
        series = load_series(folder / "log.db")
        render(series, chart_out)
        n_points = sum(len(v) for v in series.values())
        print(f"Chart: {chart_out} ({len(series)} curves, {n_points} points)")
    except Exception as e:
        print(f"Chart refresh skipped: {type(e).__name__}: {e}")


def _provider_kwargs(config: dict) -> dict:
    return {
        key: value
        for key, value in config.items()
        if key not in {"name", "platform", "model"}
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m conforma.run <target-folder>", file=sys.stderr)
        return 2
    return asyncio.run(run_eval(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
