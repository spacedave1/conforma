"""Chart per-model judge scores over time for one target folder.

Reads <target>/log.db and plots one curve per (model, scenario) pair: x = run
timestamp, y = mean overall_score over that run's judge reruns.

Usage:
  python -m conforma.chart <target-folder> [--out <path.png>]
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_series(db_path: Path) -> dict[str, list[tuple[datetime, float, int]]]:
    """Returns {model: [(invocation_timestamp, mean_score_across_scenarios, n_judge_runs), ...]}
    sorted by time. One point per (model × Conforma invocation), where each
    invocation persists exactly one prompts row that all its runs reference. The y-value
    averages every judge_runs.overall_score for that (model, invocation) — so it averages
    over (scenarios × judge_reruns × per-scenario reruns).
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute("""
        SELECT r.model, p.captured_at, AVG(j.overall_score), COUNT(j.id)
        FROM runs r
        JOIN prompts p     ON r.prompt_id = p.id
        JOIN judge_runs j  ON j.run_id    = r.id
        GROUP BY r.model, p.id
        ORDER BY p.captured_at
    """)
    series: dict[str, list[tuple[datetime, float, int]]] = defaultdict(list)
    for model, ts, mean_score, n in cur.fetchall():
        if mean_score is None:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        series[model].append((dt, float(mean_score), int(n)))
    con.close()
    return series


def render(series, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not series:
        print("No runs in log.db — nothing to plot.")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    for model, points in sorted(series.items()):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.plot(xs, ys, marker="o", label=model)

    ax.set_xlabel("Conforma invocation timestamp")
    ax.set_ylabel("mean conformance score across scenarios (0-100)")
    ax.set_ylim(-5, 105)
    ax.set_title(f"Conforma — {out_path.parent.name}")
    ax.legend(loc="best", fontsize="small")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("target_folder")
    p.add_argument("--out", default=None, help="output png path; default: <target>/chart.png")
    args = p.parse_args()

    folder = Path(args.target_folder)
    db_path = folder / "log.db"
    if not db_path.exists():
        print(f"ERROR: no log.db at {db_path}", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else folder / "chart.png"
    series = load_series(db_path)
    render(series, out_path)
    n_points = sum(len(v) for v in series.values())
    print(f"Wrote {out_path} ({len(series)} curves — one per model, {n_points} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
