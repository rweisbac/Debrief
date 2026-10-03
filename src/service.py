"""Application logic behind app.py, kept out of Streamlit so it can be tested directly."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta

from src import capture, config, events, nudges, record_store
from src.adapters import FileCRMSource, FileGongSource, FileNotifier
from src.chain import Chain, load_context
from src.llm import LLMClient, ReplayMiss
from src.schemas import CaptureRecord, ExtractionRecord

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


# Post-demo capture

def build_capture(deal_id: str, record: dict, llm: LLMClient | None = None, source: str = "",
                  gong=None, crm_source=None) -> dict | None:
    """Run the capture call for a debrief that has an extraction, score it and save it. None if the call fails.
    Raises ReplayMiss in replay mode when no recording exists."""
    if not record or not record.get("extraction"):
        return None
    llm = llm or LLMClient()
    ctx = load_context(deal_id, gong, crm_source)
    extraction = ExtractionRecord.model_validate(record["extraction"])
    res = asyncio.run(capture.run_capture(llm, ctx.transcript, ctx.context_block(), extraction,
                                          record.get("debrief_id", deal_id)))
    if res.parsed is None:
        return None
    scored = capture.score(res.parsed, ctx.transcript, ctx.crm, ctx.as_of)
    return capture.save_capture(deal_id, res.parsed, scored, source or llm.mode, record.get("debrief_id", ""))


def sample_capture(deal_id: str) -> dict | None:
    """Hand-written sample capture, scored by the real code. Only when DEBRIEF_SAMPLES=1."""
    path = SAMPLES_DIR / f"capture_{deal_id}.json"
    if not samples_enabled() or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    ctx = load_context(deal_id)
    rec = CaptureRecord.model_validate(data["record"])
    return {"capture_id": f"{deal_id}-cap-sample", "deal_id": deal_id, "debrief_id": "", "source": "sample",
            "sample_label": data["sample_label"], "record": rec.model_dump(mode="json"),
            "scored": capture.score(rec, ctx.transcript, ctx.crm, ctx.as_of)}


def load_capture(deal_id: str, allow_run: bool = True) -> tuple[dict | None, str]:
    """Load order: a saved capture, then one run from the replay cache, then a hand-written sample."""
    saved = capture.latest_capture(deal_id)
    if saved:
        return saved, saved["source"]
    if allow_run and config.MODE == "replay":
        record, src = load_debrief(deal_id, allow_run=True)
        if src in {"saved", "replay"}:
            try:
                built = build_capture(deal_id, record, LLMClient(mode="replay"), "replay")
                if built:
                    return built, "replay"
            except ReplayMiss:
                pass
    sample = sample_capture(deal_id)
    return (sample, "sample") if sample else (None, "none")


def find_capture(capture_id: str) -> dict | None:
    """A saved capture by id, or a sample capture (id <deal>-cap-sample)."""
    if capture_id.endswith("-cap-sample"):
        return sample_capture(capture_id[: -len("-cap-sample")])
    with record_store.connect() as conn:
        row = conn.execute("SELECT payload FROM captures WHERE capture_id = ?", (capture_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def card_routing(cap: dict, ae: str) -> dict:
    return capture.route(cap["scored"], ae_confirms_so_far=capture.ae_confirms(ae), spot_key=cap["capture_id"])


def confirm_capture(cap: dict, ae: str, values: dict[str, dict], seconds: float, channel: str,
                    crm_writer=None) -> dict:
    """The one confirm path for Slack and the web page: store labels, log events, write confirmed fields to CRM."""
    from src.adapters import FileCRMWriter
    session = capture.submit(cap, ae, values, seconds)
    deal_id = cap["deal_id"]
    events.log("capture_confirmed", "ae", deal_id, channel=channel, seconds=seconds,
               questions_shown=session["questions_shown"], corrected=len(session["corrected"]),
               source=cap.get("source", ""))
    for f in session["corrected"]:
        events.log("capture_field_corrected", "ae", deal_id, field=f)
    (crm_writer or FileCRMWriter()).update_opportunity(deal_id, capture.crm_fields(session["final"]),
                                                       source=f"debrief capture confirmed by {ae}")
    return session


def refresh_with_confirmed(deal_id: str, final: dict, llm: LLMClient | None = None) -> dict | None:
    """Rerun the debrief with the AE's confirmed fields, so steps and drafts reflect the correction. Live and record
    modes only: replay has no recording for a correction the AE has not made yet."""
    if (llm.mode if llm else config.MODE) == "replay":
        return None
    result = asyncio.run(Chain(llm or LLMClient()).run(load_context(deal_id), confirmed=final))
    payload = result.to_dict()
    payload["source"] = "auto"
    record_store.save_debrief(result.debrief_id, deal_id, result.prompt_versions, payload)
    return payload
