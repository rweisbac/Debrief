"""Runtime configuration. All values come from env vars with safe defaults."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODEL = os.environ.get("DEBRIEF_MODEL", "claude-sonnet-5-5")
MODE = os.environ.get("DEBRIEF_MODE", "replay")  # live, record, replay
if MODE not in {"live", "record", "replay"}:
    raise ValueError(f"DEBRIEF_MODE must be live, record or replay, got {MODE!r}")

DB_PATH = Path(os.environ.get("DEBRIEF_DB", ROOT / "debrief.sqlite3"))
REPLAY_DIR = ROOT / "fixtures" / "replay"

# USD per million tokens. Source: claude-api skill model table, cached 2026-09-25.
# Cache write rate assumes the standard 1.25x of input for the 5 minute TTL. Verify before quoting.
PRICING_USD_PER_MTOK = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
}


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             cache_read: int = 0, cache_write: int = 0) -> float:
    """Cost of one call. input_tokens is the uncached input count reported by the API."""
    p = PRICING_USD_PER_MTOK.get(model)
    if p is None:
        return 0.0
    total = (input_tokens * p["input"] + output_tokens * p["output"]
             + cache_read * p["cache_read"] + cache_write * p["cache_write"])
    return round(total / 1_000_000, 6)
