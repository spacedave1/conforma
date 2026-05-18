from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from conforma.judge import JUDGE_SCHEMA, JUDGE_SYSTEM_PROMPT, JUDGE_TEMPERATURE


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yaml_path TEXT,
    yaml_key TEXT,
    content TEXT,
    captured_at TEXT
);
CREATE TABLE IF NOT EXISTS structural_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_json TEXT,
    captured_at TEXT
);
CREATE TABLE IF NOT EXISTS specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    captured_at TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT,
    messages_json TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER,
    schema_id INTEGER,
    spec_id INTEGER,
    sample_id INTEGER,
    model TEXT,
    output_json TEXT,
    parse_ok INTEGER,
    structural_errors TEXT,
    timestamp TEXT,
    FOREIGN KEY(prompt_id) REFERENCES prompts(id),
    FOREIGN KEY(schema_id) REFERENCES structural_contracts(id),
    FOREIGN KEY(spec_id)   REFERENCES specs(id),
    FOREIGN KEY(sample_id) REFERENCES samples(id)
);
CREATE TABLE IF NOT EXISTS judge_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    judge_model TEXT,
    overall_score INTEGER,
    rationale TEXT,
    timestamp TEXT,
    judge_config_id INTEGER,
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY(judge_config_id) REFERENCES judge_configs(id)
);
CREATE TABLE IF NOT EXISTS judge_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judge_system_prompt TEXT,
    judge_schema_json TEXT,
    temperature REAL,
    code_self_hash TEXT,
    git_sha TEXT,
    captured_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA_SQL)
    cur = con.execute("PRAGMA table_info(judge_runs)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if "judge_config_id" not in existing_cols:
        con.execute("ALTER TABLE judge_runs ADD COLUMN judge_config_id INTEGER REFERENCES judge_configs(id)")
    con.commit()
    return con


def persist_inputs(con: sqlite3.Connection, target: dict) -> tuple[int, int, int, int]:
    cur = con.cursor()
    ts = now_iso()
    cur.execute(
        "INSERT INTO prompts(yaml_path, yaml_key, content, captured_at) VALUES (?,?,?,?)",
        (target["prompt_yaml_path"], target["prompt_yaml_key"], target["prompt_text"], ts),
    )
    prompt_id = cur.lastrowid
    cur.execute(
        "INSERT INTO structural_contracts(schema_json, captured_at) VALUES (?,?)",
        (json.dumps(target["schema"]) if target["schema"] is not None else None, ts),
    )
    schema_id = cur.lastrowid
    cur.execute(
        "INSERT INTO specs(content, captured_at) VALUES (?,?)",
        (target["spec"], ts),
    )
    spec_id = cur.lastrowid
    cur.execute(
        """INSERT INTO judge_configs(judge_system_prompt, judge_schema_json,
           temperature, code_self_hash, git_sha, captured_at)
           VALUES (?,?,?,?,?,?)""",
        (JUDGE_SYSTEM_PROMPT, json.dumps(JUDGE_SCHEMA), JUDGE_TEMPERATURE,
         _self_hash(), _git_sha(), ts),
    )
    judge_config_id = cur.lastrowid
    con.commit()
    return prompt_id, schema_id, spec_id, judge_config_id


def persist_samples(con: sqlite3.Connection, samples: list[dict]) -> list[int]:
    cur = con.cursor()
    ids: list[int] = []
    for s in samples:
        cur.execute(
            "INSERT INTO samples(label, messages_json) VALUES (?,?)",
            (s.get("label", ""), json.dumps(s["messages"])),
        )
        ids.append(cur.lastrowid)
    con.commit()
    return ids


def _self_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

