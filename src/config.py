"""Runtime configuration. All values come from env vars with safe defaults."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def apply_api_key_alias(env=os.environ) -> None:
    """Treat DEBRIEF_API_KEY as ANTHROPIC_API_KEY. An explicit ANTHROPIC_API_KEY wins."""
    if not env.get("ANTHROPIC_API_KEY") and env.get("DEBRIEF_API_KEY"):
        env["ANTHROPIC_API_KEY"] = env["DEBRIEF_API_KEY"]


apply_api_key_alias()

MODEL = os.environ.get("DEBRIEF_MODEL", "claude-sonnet-5-5")
MODE = os.environ.get("DEBRIEF_MODE", "replay")  # live, record, replay
if MODE not in {"live", "record", "replay"}:
    raise ValueError(f"DEBRIEF_MODE must be live, record or replay, got {MODE!r}")

DB_PATH = Path(os.environ.get("DEBRIEF_DB", ROOT / "debrief.sqlite3"))
REPLAY_DIR = ROOT / "fixtures" / "replay"
# In record mode an existing fixture is reused unless this is set, so a second record pass
# (for example the verifier ablation after the evals) does not overwrite earlier recordings.
RERECORD = os.environ.get("DEBRIEF_RERECORD", "") == "1"

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


# Where step rules go. "mid_conversation_system" keeps the transcript in the shared cached prefix
# across steps. "top_system" is the fallback if the live smoke test shows the API rejects it.
STEP_RULES_PLACEMENT = os.environ.get("DEBRIEF_STEP_RULES_PLACEMENT", "mid_conversation_system")
if STEP_RULES_PLACEMENT not in {"mid_conversation_system", "top_system"}:
    raise ValueError(f"bad DEBRIEF_STEP_RULES_PLACEMENT {STEP_RULES_PLACEMENT!r}")

# Effort and max_tokens per step. max_tokens covers thinking plus output.
STEP_SETTINGS = {
    "extract": {"effort": "low", "max_tokens": 16000},
    "extract_b": {"effort": "low", "max_tokens": 16000},
    "assess_and_recommend": {"effort": "medium", "max_tokens": 12000},
    "draft_recap_email": {"effort": "low", "max_tokens": 8000},
    "draft_internal_summary": {"effort": "low", "max_tokens": 8000},
    "draft_mutual_action_plan": {"effort": "low", "max_tokens": 8000},
    "verify": {"effort": "medium", "max_tokens": 12000},
    "judge": {"effort": "medium", "max_tokens": 4000},
    "capture": {"effort": "low", "max_tokens": 8000},
}

# Post-demo capture routing (src/capture.py). A field at or above the threshold is confirmed by the agent and
# collapsed; below it, the AE is asked. Judgment fields are always asked for each AE's first N confirms. A share of
# auto-confirmed fields is shown anyway as a spot check, so the error rate among auto-confirmed fields is measured
# rather than assumed.
# Best practice profile (DECISIONS D-17). On: playbook v2 from the research, next step prompt v3, recap v3 and judge
# v2. Off: the versions the recorded fixtures were made with, so replay keeps working until a re-record.
BEST_PRACTICE = os.environ.get("DEBRIEF_BEST_PRACTICE", "") == "1"
PLAYBOOK_FILE = ROOT / "data" / ("playbook_v2.md" if BEST_PRACTICE else "playbook.md")
PROMPT_PINS = {} if BEST_PRACTICE else {"assess_and_recommend": 2, "draft_recap_email": 2, "judge": 1}
MAX_RECAP_WORDS = 120 if BEST_PRACTICE else 180

# Where the confirm page is served (src/web.py). The Slack card links here.
PUBLIC_URL = os.environ.get("DEBRIEF_PUBLIC_URL", "http://localhost:8000").rstrip("/")
CAPTURE_THRESHOLD = float(os.environ.get("DEBRIEF_CAPTURE_THRESHOLD", "0.90"))
CAPTURE_JUDGMENT_WARMUP = int(os.environ.get("DEBRIEF_CAPTURE_WARMUP", "20"))
CAPTURE_SPOT_CHECK_RATE = float(os.environ.get("DEBRIEF_CAPTURE_SPOT_CHECK", "0.10"))

LOW_INFO_MIN_CUSTOMER_UTTERANCES = 8  # substantive = 8 or more words
LOW_INFO_MAX_STEPS = 2
