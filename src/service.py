"""Application logic behind app.py, kept out of Streamlit so it can be tested directly."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta

from src import config, events, nudges, record_store
from src.adapters import FileCRMSource, FileGongSource, FileNotifier
from src.chain import Chain, load_context
from src.llm import LLMClient, ReplayMiss

DEALS = ["deal_a", "deal_b", "deal_c", "deal_x", "deal_y"]
SAMPLES_DIR = config.ROOT / "fixtures" / "samples"
POD_MANAGERS = {"Central-1": "Morgan Diaz", "East-2": "Riley Chen", "West-1": "Avery Brooks"}  # fictional
OUTCOMES = {"advanced": "advanced", "stalled": "stalled", "closed_won": "closed won", "closed_lost": "closed lost"}


def samples_enabled() -> bool:
    return os.environ.get("DEBRIEF_SAMPLES", "") == "1"


def load_debrief(deal_id: str, allow_run: bool = True) -> tuple[dict | None, str]:
    """Load order: a saved real run, then a replay run from fixtures, then a hand-written sample (only when
    DEBRIEF_SAMPLES=1). Returns (record, source) where source is saved, replay, sample or none."""
    saved = record_store.load_latest_debrief(deal_id)
    if saved and saved.get("source") != "sample":
        return saved, "saved"
    if allow_run and config.MODE == "replay":
        try:
            result = asyncio.run(Chain(LLMClient(mode="replay")).run(load_context(deal_id)))
            payload = result.to_dict()
            payload["source"] = "replay"
            record_store.save_debrief(result.debrief_id, deal_id, result.prompt_versions, payload)
            return payload, "replay"
        except ReplayMiss:
            pass
    path = SAMPLES_DIR / f"{deal_id}.json"
    if samples_enabled() and path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "sample"
    return None, "none"


def demo_end(crm: dict) -> datetime:
    return datetime.fromisoformat(crm["demo"]["actual_end"])


def card_generated(deal_id: str) -> bool:
    return bool(events.list_events(deal_id, "card_generated"))


def step_status(deal_id: str) -> dict[int, dict]:
    """Per step index: {"status": acted|dismissed, "detail": ...} from logged events."""
    out: dict[int, dict] = {}
    for e in events.list_events(deal_id):
        if e["name"] == "step_dismissed":
            out[e["step"]] = {"status": "dismissed", "detail": events.DISMISS_REASONS[e["reason"]]}
        elif e["name"] == "step_action_taken":
            out[e["step"]] = {"status": "acted", "detail": e.get("action", "")}
    return out


def customer_touches(deal_id: str, activity: dict) -> list[datetime]:
    touches = [datetime.fromisoformat(a["at"]) for a in activity.get("post_demo_activity", []) if a.get("customer_facing")]
    touches += [datetime.fromisoformat(e["ts"]) for e in events.list_events(deal_id, "draft_marked_sent")]
    return sorted(touches)


def sc_commitments(record: dict, crm: dict, deal_id: str) -> list[dict]:
    done = {e.get("commitment") for e in events.list_events(deal_id, "next_step_completed")}
    ex = record.get("extraction") or {}
    return [{"what": c["what"], "due": c["by_when"], "done": c["what"] in done}
            for c in ex.get("commitments", []) if c["who"] == crm["sc"]]


def nudge_state(record: dict, crm: dict, activity: dict) -> nudges.DealNudgeState:
    deal_id = crm["deal_id"]
    a = (record["artifacts"].get("assessment") or {}).get("current") or {}
    ex = record.get("extraction") or {}
    deps = [d["summary"] for d in ex.get("customer_dependencies", []) if d.get("blocks_progress")]
    sent = [(datetime.fromisoformat(e["ts"]), e["kind"]) for e in events.list_events(deal_id, "nudge_sent")]
    return nudges.DealNudgeState(
        deal_id=deal_id, account=crm["account"], deal_state=a.get("deal_state", ""), demo_end=demo_end(crm),
        ae=crm["owner_ae"], sc=crm["sc"], manager=POD_MANAGERS.get(crm["pod"], "Pod manager"),
        top_step=(a.get("next_steps") or [{}])[0].get("action", ""), dependency=deps[0] if deps else "",
        customer_touches=customer_touches(deal_id, activity), sc_commitments=sc_commitments(record, crm, deal_id),
        nudges_sent=sent)


def tick_nudges(record: dict, crm: dict, activity: dict, now: datetime, notifier: FileNotifier | None = None) -> list[nudges.Nudge]:
    """Evaluate nudges at simulated time now; send and log any that fire."""
    notifier = notifier or FileNotifier()
    fired = nudges.evaluate(nudge_state(record, crm, activity), now)
    for n in fired:
        for m in n.messages:
            notifier.send(m["recipient"], m["role"], crm["deal_id"], "nudge", {"kind": n.kind, "text": m["text"],
                                                                               "at": now.isoformat()})
        events.log("nudge_sent", "system", crm["deal_id"], ts=now.isoformat(), kind=n.kind)
    return fired


def report_outcome(record: dict, crm: dict, outcome: str, now: datetime, role: str,
                   notifier: FileNotifier | None = None) -> str | None:
    """Record the outcome; for advanced or stalled, send the SC a loop closing message."""
    notifier = notifier or FileNotifier()
    record_store.set_deal_status(crm["deal_id"], outcome, now.isoformat())
    events.log("outcome_reported", role, crm["deal_id"], ts=now.isoformat(), outcome=outcome)
    if outcome in ("advanced", "stalled"):
        text = nudges.loop_closure_message(crm["account"], OUTCOMES[outcome], record.get("extraction") or {}, crm["sc"])
        notifier.send(crm["sc"], "sc", crm["deal_id"], "loop_closure", {"text": text, "at": now.isoformat()})
        return text
    return None


def generate_card(deal_id: str, record: dict, now: datetime, prompt_version: str = "") -> None:
    """Log card generation plus the rule overrides and verifier flags it carried."""
    events.log("card_generated", "system", deal_id, prompt_version, ts=now.isoformat(), source=record.get("source", ""))
    for o in record.get("overrides", []):
        events.log("rule_override_applied", "system", deal_id, prompt_version, ts=now.isoformat(), rule_id=o["rule_id"])
    for v in record.get("verifier", []):
        if not v["passed"]:
            events.log("verifier_flagged", "system", deal_id, prompt_version, ts=now.isoformat(), check=v["check"],
                       artifact=v["artifact"])
    record_store.save_debrief(record["debrief_id"], deal_id, record.get("prompt_versions", {}), record)


def manager_rows(now: datetime) -> list[dict]:
    crm_source, gong = FileCRMSource(), FileGongSource()
    rows = []
    for deal_id in DEALS:
        crm, activity = crm_source.deal(deal_id), gong.activity(deal_id)
        record, source = load_debrief(deal_id, allow_run=False)
        a = ((record or {}).get("artifacts", {}).get("assessment") or {}).get("current") or {}
        ex = (record or {}).get("extraction") or {}
        replies = sum(1 for x in activity.get("post_demo_activity", []) if x["type"] == "email_in")
        replies += len(events.list_events(deal_id, "customer_reply_received"))
        hours = (now - demo_end(crm)).total_seconds() / 3600
        rows.append({
            "Account": crm["account"], "AE": crm["owner_ae"], "Deal state": a.get("deal_state", "no debrief yet"),
            "Hours since demo": f"{hours:.1f}" if hours >= 0 else "demo not ended",
            "Dated next step agreed in the call": ("yes" if ex.get("agreed_next_step", {}).get("exists") else "no")
            if record else "unknown",
            "Customer replies": replies, "Status": record_store.deal_status(deal_id), "Source": source,
            "_deal_id": deal_id, "_top_step": (a.get("next_steps") or [{}])[0].get("action", ""),
        })
    return rows


COACHING = {
    "ready_to_advance": "Ask {ae} how the economic buyer meeting is set up, and what {account} needs to see there.",
    "open_technical_gap": "Ask {ae} who owns the open technical answer and when {account} will hear it.",
    "missing_stakeholder": "Ask {ae} how the champion at {account} will bring the missing person in.",
    "competitive_risk": "Ask {ae} what {account} will compare, and whether deal desk has the competitor flag.",
    "waiting_on_customer": "Ask {ae} what the customer's process needs from us, not when they will decide.",
    "low_information": "Ask {ae} what would make the next call worth the customer's time at {account}.",
}


def coaching_prompt(row: dict) -> str:
    template = COACHING.get(row["Deal state"])
    if not template:
        return f"No debrief yet for {row['Account']}."
    prompt = template.format(ae=row["AE"].split()[0], account=row["Account"])
    if row["_top_step"]:
        prompt += f" Suggested top step: {row['_top_step']}"
    return prompt


def mark_ignored_cards(now: datetime) -> None:
    """Log card_ignored_24h once for any card generated more than 24h ago (simulated) and never opened."""
    for deal_id in DEALS:
        gen = events.list_events(deal_id, "card_generated")
        if not gen or events.list_events(deal_id, "card_opened") or events.list_events(deal_id, "card_ignored_24h"):
            continue
        if now - datetime.fromisoformat(gen[0]["ts"]) > timedelta(hours=24):
            events.log("card_ignored_24h", "system", deal_id, ts=now.isoformat())
