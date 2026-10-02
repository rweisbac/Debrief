"""Instrumentation. Every user action and system decision that the measurement plan needs is logged here."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from src import record_store

EVENT_NAMES = {
    "demo_checklist_started", "demo_checklist_filled_before_call_end", "card_generated", "card_opened",
    "card_ignored_24h", "step_expanded", "step_dismissed", "step_action_taken", "draft_edited", "draft_approved",
    "draft_sent_unedited", "draft_rejected", "draft_marked_sent", "next_step_completed", "nudge_sent",
    "nudge_acted_on", "record_confirmed_by_sc", "handoff_brief_viewed", "outcome_reported",
    "customer_reply_received", "rule_override_applied", "verifier_flagged",
}
DISMISS_REASONS = {"already_done": "Already done", "waiting_on_customer": "Waiting on customer",
                   "not_relevant": "Not relevant", "no_time": "No time"}


def log(name: str, role: str, deal_id: str, prompt_version: str = "", ts: str | None = None,
        db_path: Path | None = None, **props) -> dict:
    if name not in EVENT_NAMES:
        raise ValueError(f"unknown event {name!r}")
    if name == "step_dismissed" and props.get("reason") not in DISMISS_REASONS:
        raise ValueError(f"step_dismissed needs a reason in {sorted(DISMISS_REASONS)}")
    ts = ts or datetime.now(timezone.utc).isoformat()
    with record_store.connect(db_path) as conn:
        conn.execute("INSERT INTO events (ts, name, role, deal_id, prompt_version, props) VALUES (?, ?, ?, ?, ?, ?)",
                     (ts, name, role, deal_id, prompt_version, json.dumps(props, sort_keys=True)))
    return {"ts": ts, "name": name, "role": role, "deal_id": deal_id, "prompt_version": prompt_version, **props}


def list_events(deal_id: str | None = None, name: str | None = None, db_path: Path | None = None) -> list[dict]:
    q, args = "SELECT * FROM events WHERE 1=1", []
    if deal_id:
        q += " AND deal_id = ?"
        args.append(deal_id)
    if name:
        q += " AND name = ?"
        args.append(name)
    with record_store.connect(db_path) as conn:
        rows = conn.execute(q + " ORDER BY id", args).fetchall()
    return [{**{k: r[k] for k in ("id", "ts", "name", "role", "deal_id", "prompt_version")}, **json.loads(r["props"])}
            for r in rows]


def edit_ratio(original: str, edited: str) -> float:
    """Share of the draft the rep changed: 1 minus normalized Levenshtein similarity. 0 means sent as drafted."""
    return round(1 - Levenshtein.normalized_similarity(original, edited), 4)
