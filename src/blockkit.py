"""Slack Block Kit card for the AE. Quotes are rendered from the transcript table, never from model text.

Paste assets/ae_card_blockkit.json into Block Kit Builder to see it as Slack would render it.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.config import PUBLIC_URL, ROOT
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
    blocks.append(confirm_block(record["deal_id"]))
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


def confirm_url(deal_id: str) -> str:
    return f"{PUBLIC_URL}/capture/{deal_id}"


def confirm_block(deal_id: str) -> dict:
    """Link to the confirm card. A real interactive Slack card needs a Slack app with a public request URL;
    the prototype links to a page that looks like the card."""
    return {"type": "section", "block_id": "confirm",
            "text": _text("*Confirm 4 things about this call.* Pre-filled from the transcript; most take one tap."),
            "accessory": {"type": "button", "action_id": "open_confirm", "style": "primary",
                          "text": {"type": "plain_text", "text": "Confirm"}, "url": confirm_url(deal_id)}}


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


def slack_safe(payload: dict, app_url: str = "", interactive: bool = False) -> list[dict]:
    """Blocks for a posted message. With interactivity configured (src/web.py serves /slack/interactions and
    DEBRIEF_SLACK_SIGNING_SECRET is set) buttons and menus are kept. Without it they would do nothing, so they
    are dropped and replaced with a link to the app where the same actions work."""
    if interactive:
        return payload["blocks"]
    blocks = [b for b in payload["blocks"] if b["type"] != "actions"]
    if app_url:
        blocks.append({"type": "section", "text": _text(f"<{app_url}|Open in Debrief> to act on or dismiss a step.")})
    return blocks


# Post-demo capture card ("confirm, don't write")

def _option(key: str, value: str) -> dict:
    from src.capture import option_label
    return {"text": {"type": "plain_text", "text": option_label(key, value)}, "value": value}


def _select(capture_id: str, field: str, part: str, current: str) -> dict:
    from src.capture import ENUM_OPTIONS
    key = f"{field}.{part}"
    sel = {"type": "static_select", "action_id": f"cap_sel|{capture_id}|{field}|{part}",
           "placeholder": {"type": "plain_text", "text": "Choose"},
           "options": [_option(key, v) for v, _ in ENUM_OPTIONS[key]]}
    if current:
        sel["initial_option"] = _option(key, current)
    return sel


def capture_card(cap: dict, routing: dict, crm: dict, values: dict | None = None) -> dict:
    """Interactive Slack card. Fields the agent is sure of are one line with a check; fields that need the AE get
    tap-to-select menus (enums) or an Edit button (text, opens a modal). One Confirm all button submits.
    values overrides the agent values with the AE's pending edits."""
    from src.capture import FIELDS, confidence_label, display
    values = values or {}
    cid = cap["capture_id"]
    asked = [f for f in FIELDS if routing[f]["mode"] == "ask"]
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Confirm the demo: {crm['account']}"[:150]}},
        {"type": "context", "elements": [_text(
            f"Pre-filled from the call. {len(asked)} of 4 need you; the rest are confirmed by the agent. "
            "About 30 seconds." + (f" _{cap['sample_label']}_" if cap.get("sample_label") else ""))]},
    ]
    for f in FIELDS:
        s = cap["scored"][f]
        v = {**s["values"], **(values.get(f) or {})}
        edited = bool(values.get(f))
        if routing[f]["mode"] == "auto" and not edited:
            blocks.append({"type": "section", "block_id": f"cap_{f}",
                           "text": _text(f":white_check_mark: *{s['label']}:* {display(f, v)}"),
                           "accessory": {"type": "button", "action_id": f"cap_edit|{cid}|{f}",
                                         "text": {"type": "plain_text", "text": "Edit"}}})
            blocks.append({"type": "context", "elements": [_text(
                f"Confirmed by agent ({confidence_label(s['confidence'])}, {round(s['confidence'] * 100)}%)")]})
            continue
        flag = ":pencil2: *Edited.*" if edited else ":large_orange_circle: *Needs your call.*"
        blocks.append({"type": "section", "block_id": f"cap_{f}",
                       "text": _text(f"{flag} *{s['label']}:* {display(f, v)}"),
                       "accessory": {"type": "button", "action_id": f"cap_edit|{cid}|{f}",
                                     "text": {"type": "plain_text", "text": "Edit"}}})
        if f == "champion_status":
            blocks.append({"type": "actions", "block_id": f"cap_sel_{f}", "elements": [
                _select(cid, f, "value", v.get("value", "")),
                _select(cid, f, "economic_buyer_identified", v.get("economic_buyer_identified", ""))]})
        elif f == "top_risk":
            blocks.append({"type": "actions", "block_id": f"cap_sel_{f}",
                           "elements": [_select(cid, f, "value", v.get("value", ""))]})
        why = routing[f]["reason"]
        if s["quotes"]:
            q = s["quotes"][0]
            why += f"\n> \"{q['text'][:220]}\"\n> {q['speaker']}, at {q['timestamp']}"
        blocks.append({"type": "context", "elements": [_text(why)]})
    blocks.append({"type": "actions", "block_id": "cap_submit", "elements": [
        {"type": "button", "action_id": f"cap_confirm|{cid}", "style": "primary",
         "text": {"type": "plain_text", "text": "Confirm all"}, "value": cid},
        {"type": "button", "action_id": f"cap_web|{cid}", "text": {"type": "plain_text", "text": "Open full card"},
         "url": confirm_url(cap["deal_id"])}]})
    return {"blocks": blocks, "text": f"Confirm 4 things about the {crm['account']} demo"}


def capture_done_card(cap: dict, crm: dict, session: dict, record: dict | None) -> dict:
    """What replaces the capture card after Confirm all: the confirmed values, then the payoff."""
    from src.capture import FIELDS, LABELS, display
    lines = [f"*{LABELS[f]}:* {display(f, session['final'][f])}" + (" _(you corrected this)_"
                                                                     if f in session["corrected"] else "")
             for f in FIELDS]
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Confirmed: {crm['account']}"[:150]}},
              {"type": "section", "text": _text("\n".join(lines))},
              {"type": "context", "elements": [_text("Saved to the opportunity in CRM. Nothing was sent to the customer.")]}]
    a = ((record or {}).get("artifacts", {}).get("assessment") or {}).get("current") or {}
    if a.get("next_steps"):
        top = a["next_steps"][0]
        blocks += [{"type": "divider"},
                   {"type": "section", "text": _text(f"*Next best step:* {top['action']}\n"
                                                     f"Owner: {top['owner']} | Due: {top['due_by'] or 'no date'} | "
                                                     f"Rule: {top['playbook_rule_id']}")}]
    blocks.append({"type": "actions", "elements": [
        {"type": "button", "action_id": f"cap_web|{cap['capture_id']}", "style": "primary",
         "text": {"type": "plain_text", "text": "Review recap and steps"}, "url": confirm_url(cap["deal_id"])}]})
    return {"blocks": blocks, "text": f"Confirmed: {crm['account']}"}


def capture_edit_modal(cap: dict, field: str, values: dict) -> dict:
    """Slack modal for editing one field. private_metadata carries the capture and field."""
    from src.capture import LABELS
    v = {**cap["scored"][field]["values"], **(values.get(field) or {})}
    blocks = []

    def text_input(part: str, label: str, multiline: bool = False) -> dict:
        el = {"type": "plain_text_input", "action_id": part, "multiline": multiline}
        if v.get(part):
            el["initial_value"] = v[part]
        return {"type": "input", "block_id": part, "optional": True, "label": {"type": "plain_text", "text": label},
                "element": el}

    def select_input(part: str, label: str) -> dict:
        sel = _select(cap["capture_id"], field, part, v.get(part, ""))
        sel["action_id"] = part
        return {"type": "input", "block_id": part, "label": {"type": "plain_text", "text": label}, "element": sel}

    if field == "priority_why_now":
        blocks.append(text_input("value", "Priority and why now (25 words max)", True))
    elif field == "champion_status":
        blocks += [select_input("value", "Champion"), text_input("champion_name", "Champion name"),
                   select_input("economic_buyer_identified", "Economic buyer named?"),
                   text_input("economic_buyer_name", "Economic buyer name")]
    elif field == "top_risk":
        blocks += [select_input("value", "Top risk"), text_input("note", "One line on the risk")]
    elif field == "next_step":
        date_el = {"type": "datepicker", "action_id": "date"}
        if v.get("date"):
            date_el["initial_date"] = v["date"]
        blocks += [text_input("value", "Next step the customer agreed to"),
                   {"type": "input", "block_id": "date", "optional": True,
                    "label": {"type": "plain_text", "text": "Date"}, "element": date_el}]
    return {"type": "modal", "callback_id": "cap_edit",
            "private_metadata": json.dumps({"capture_id": cap["capture_id"], "field": field}),
            "title": {"type": "plain_text", "text": LABELS[field][:24]},
            "submit": {"type": "plain_text", "text": "Save"}, "blocks": blocks}
