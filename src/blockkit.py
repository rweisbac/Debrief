"""Slack Block Kit card for the AE. Quotes are rendered from the transcript table, never from model text.

Paste assets/ae_card_blockkit.json into Block Kit Builder to see it as Slack would render it.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.config import ROOT
from src.events import DISMISS_REASONS
from src.transcript import Transcript

ASSET = ROOT / "assets" / "ae_card_blockkit.json"
STATE_LABELS = {
    "ready_to_advance": "Ready to advance", "open_technical_gap": "Open technical gap",
    "missing_stakeholder": "Missing stakeholder", "competitive_risk": "Competitive risk",
    "waiting_on_customer": "Waiting on customer", "low_information": "Not enough from the call yet",
}
ACTION_LABELS = {
    "send_recap": "Send recap", "book_meeting": "Book meeting", "send_material": "Open draft",
    "route_to_sc": "Send to SC", "reach_stakeholder": "Draft intro", "support_customer_process": "Open packet draft",
    "flag_deal_desk": "Flag to deal desk", "resolve_with_champion": "Draft note to champion", "other": "Open",
}


def _text(t: str) -> dict:
    return {"type": "mrkdwn", "text": t[:2900]}


def quote_line(transcript: Transcript, utterance_id: str) -> str:
    q = transcript.render_quote(utterance_id)
    return f"> \"{q['text']}\"\n> {q['speaker']}, {q['title']}, at {q['timestamp']}"


def card(record: dict, transcript: Transcript, crm: dict) -> dict:
    a = (record["artifacts"].get("assessment") or {}).get("current") or {}
    ex = record.get("extraction") or {}
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": f"Debrief: {crm['account']}"[:150]}}]
    labels = ["Synthetic data, fictional company."]
    if record.get("source") == "sample":
        labels.append(record["sample_label"])
    blocks.append({"type": "context", "elements": [_text(" ".join(labels))]})
    state = STATE_LABELS.get(a.get("deal_state", ""), a.get("deal_state", "unknown"))
    blocks.append({"type": "section", "text": _text(f"*{state}.* {a.get('deal_state_why', '')}")})
    blocks.append({"type": "divider"})
    for i, s in enumerate(a.get("next_steps", [])[:3]):
        lead = "*Most important:* " if i == 0 else f"*Step {i + 1}:* "
        meta = [f"Owner: {s['owner']}", f"Due: {s['due_by'] or 'no date'}", f"Rule: {s['playbook_rule_id']}"]
        if s.get("release_card_id"):
            meta.append(f"Use: {s['release_card_id']}")
        blocks.append({"type": "section", "block_id": f"step_{i}", "text": _text(lead + s["action"])})
        blocks.append({"type": "context", "elements": [_text(" | ".join(meta))]})
        why = f"*Why this step:* {s['why']}"
        if s.get("evidence"):
            why += "\n" + quote_line(transcript, s["evidence"][0]["utterance_id"])
        blocks.append({"type": "section", "text": _text(why)})
        elements = [{"type": "button", "action_id": f"act_{i}", "style": "primary",
                     "text": {"type": "plain_text", "text": ACTION_LABELS.get(s["action_type"], "Open")},
                     "value": json.dumps({"deal_id": record["deal_id"], "step": i, "action": s["action_type"]})}]
        for key, label in DISMISS_REASONS.items():
            elements.append({"type": "button", "action_id": f"dismiss_{i}_{key}", "text": {"type": "plain_text", "text": label},
                             "value": json.dumps({"deal_id": record["deal_id"], "step": i, "reason": key})})
        blocks.append({"type": "actions", "block_id": f"actions_{i}", "elements": elements})
    if a.get("watch_items"):
        watch = "\n".join(f"- {w['summary']}" + (f" (use {w['release_card_id']})" if w.get("release_card_id") else "")
                          for w in a["watch_items"])
        blocks += [{"type": "divider"}, {"type": "section", "text": _text("*Watch*\n" + watch)}]
    open_items = [f"- {o['summary']} (owner: {o['owner']})" for o in ex.get("open_technical_items", [])]
    if open_items:
        blocks += [{"type": "section", "text": _text("*Open*\n" + "\n".join(open_items))}]
    cost = record.get("cost_usd")
    footer = "Sample card: no cost" if cost is None else f"Cost for this debrief: ${cost:.4f}"
    review = [k for k, v in record["artifacts"].items() if v.get("needs_review")]
    if review:
        footer += " | Needs review: " + ", ".join(k.replace("_", " ") for k in review)
    blocks.append({"type": "context", "elements": [_text(footer)]})
    return {"blocks": blocks}


def save(payload: dict, path: Path = ASSET) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return path


def summary_text(record: dict, crm: dict) -> str:
    """One line for the Slack notification preview: the account and the most important step."""
    a = (record["artifacts"].get("assessment") or {}).get("current") or {}
    steps = a.get("next_steps", [])
    top = f" Most important: {steps[0]['action']}" if steps else " No new steps from this call."
    return f"Debrief ready for {crm['account']}.{top}"[:300]


def sc_card(record: dict, transcript: Transcript, crm: dict, commitments: list[dict]) -> dict:
    """Slack card for the SC: only what is theirs. Steps they own, promises they made, open technical items."""
    a = (record["artifacts"].get("assessment") or {}).get("current") or {}
    ex = record.get("extraction") or {}
    sc = crm["sc"]
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": f"Your items: {crm['account']}"[:150]}}]
    labels = ["Synthetic data, fictional company."]
    if record.get("source") == "sample":
        labels.append(record["sample_label"])
    blocks.append({"type": "context", "elements": [_text(" ".join(labels))]})
    mine = [s for s in a.get("next_steps", []) if s["owner"] == sc]
    for s in mine:
        meta = f"Due: {s['due_by'] or 'no date'} | Rule: {s['playbook_rule_id']}"
        if s.get("release_card_id"):
            meta += f" | Use: {s['release_card_id']}"
        why = f"*Why:* {s['why']}"
        if s.get("evidence"):
            why += "\n" + quote_line(transcript, s["evidence"][0]["utterance_id"])
        blocks += [{"type": "section", "text": _text(f"*To do:* {s['action']}")},
                   {"type": "context", "elements": [_text(meta)]},
                   {"type": "section", "text": _text(why)}]
    open_commitments = [c for c in commitments if not c["done"]]
    if open_commitments:
        lines = "\n".join(f"- {c['what']} (due {c['due'] or 'no date'})" for c in open_commitments)
        blocks += [{"type": "divider"}, {"type": "section", "text": _text("*You said you would*\n" + lines)}]
    mine_open = [o for o in ex.get("open_technical_items", []) if o["owner"] == sc]
    if mine_open:
        blocks.append({"type": "section", "text": _text(
            "*Open technical items*\n" + "\n".join(f"- {o['summary']}" for o in mine_open))})
    if not (mine or open_commitments or mine_open):
        blocks.append({"type": "section", "text": _text("Nothing new for you from this call.")})
    return {"blocks": blocks}


def slack_safe(payload: dict, app_url: str = "") -> list[dict]:
    """Blocks for a plain posted message. Buttons need an interactivity endpoint that this demo does not run,
    so they are dropped and replaced with a link to the app where the same actions work."""
    blocks = [b for b in payload["blocks"] if b["type"] != "actions"]
    if app_url:
        blocks.append({"type": "section", "text": _text(f"<{app_url}|Open in Debrief> to act on or dismiss a step.")})
    return blocks
