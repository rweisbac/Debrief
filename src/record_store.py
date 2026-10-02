"""SQLite storage for model call logs and saved debriefs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src import config

LLM_CALLS_DDL = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    debrief_id TEXT NOT NULL,
    step TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    mode TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    input_hash TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_input_tokens INTEGER NOT NULL,
    cache_creation_input_tokens INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    stop_reason TEXT NOT NULL,
    effort TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    replay_hit INTEGER NOT NULL,
    error TEXT NOT NULL,
    logged_input TEXT NOT NULL,
    logged_output TEXT NOT NULL
)"""

DEBRIEFS_DDL = """
CREATE TABLE IF NOT EXISTS debriefs (
    debrief_id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prompt_versions TEXT NOT NULL,
    payload TEXT NOT NULL
)"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(LLM_CALLS_DDL)
    conn.execute(DEBRIEFS_DDL)
    return conn


def log_llm_call(row: dict, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        conn.execute(f"INSERT INTO llm_calls ({cols}) VALUES ({marks})", list(row.values()))


def calls_for_debrief(debrief_id: str, db_path: Path | None = None) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM llm_calls WHERE debrief_id = ? ORDER BY created_at", (debrief_id,))
        return [dict(r) for r in rows]


def cost_for_debrief(debrief_id: str, db_path: Path | None = None) -> float:
    with connect(db_path) as conn:
        (total,) = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE debrief_id = ?",
                                (debrief_id,)).fetchone()
        return round(total, 6)


def save_debrief(debrief_id: str, deal_id: str, prompt_versions: dict, payload: dict,
                 db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO debriefs VALUES (?, ?, ?, ?, ?)",
                     (debrief_id, deal_id, datetime.now(timezone.utc).isoformat(),
                      json.dumps(prompt_versions, sort_keys=True), json.dumps(payload)))


def load_latest_debrief(deal_id: str, db_path: Path | None = None) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT payload FROM debriefs WHERE deal_id = ? ORDER BY created_at DESC LIMIT 1",
                           (deal_id,)).fetchone()
        return json.loads(row["payload"]) if row else None
