"""Web and Slack entry points for the post-demo capture ("confirm, don't write").

Run: uvicorn src.web:app --reload   (make capture)

- POST /slack/interactions  Slack buttons, menus and modals (signed requests only)
- GET  /capture/{deal_id}   the confirm card as a web page (same card as Slack, for the demo and non-Slack users)
- GET  /api/capture/{deal_id}            card data: fields, confidence, routing, quotes from the transcript
- POST /api/capture/{deal_id}/confirm    store the AE's confirm and return the payoff
- POST /meetings            intake: transcript text plus CRM context, runs the same pipeline as the Gong trigger
- GET  /metrics             capture metrics (measured and simulated kept apart)
- GET  /api/simulate        threshold simulator over stored labels
- GET  /dashboard           metrics page with the threshold slider

Nothing here sends anything to a customer.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src import capture, config, events, service, slack_actions
from src.adapters import FileCRMSource
from src.config import ROOT

WEB = ROOT / "web"
app = FastAPI(title="Debrief", docs_url=None, redoc_url=None)
_DEAL_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def _deal(deal_id: str) -> dict:
    if not _DEAL_RE.match(deal_id):
        raise HTTPException(400, "bad deal id")
    try:
        return FileCRMSource().deal(deal_id)
    except FileNotFoundError:
        raise HTTPException(404, "unknown deal")


# Pages

@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse("/capture/deal_a")


@app.get("/capture/{deal_id}")
def capture_page(deal_id: str) -> FileResponse:
    _deal(deal_id)
    return FileResponse(WEB / "capture.html")


@app.get("/dashboard")
def dashboard_page() -> FileResponse:
    return FileResponse(WEB / "dashboard.html")


# Capture API

@app.get("/api/deals")
def deals() -> list[dict]:
    crm = FileCRMSource()
    return [{"deal_id": d, "account": crm.deal(d)["account"]} for d in service.DEALS]


@app.get("/api/capture/{deal_id}")
def capture_card(deal_id: str) -> dict:
    crm = _deal(deal_id)
    cap, source = service.load_capture(deal_id)
    if not cap:
        raise HTTPException(404, "No pre-filled card for this deal yet. It appears after the call is processed.")
    routing = service.card_routing(cap, crm["owner_ae"])
    events.log("capture_card_opened", "ae", deal_id, channel="web", source=source)
    session = capture.session_for(cap["capture_id"])
    return {
        "deal_id": deal_id, "account": crm["account"], "ae": crm["owner_ae"],
        "meeting_date": crm["demo"]["actual_end"][:10], "capture_id": cap["capture_id"], "source": source,
        "sample_label": cap.get("sample_label", ""), "threshold": config.CAPTURE_THRESHOLD,
        "fields": [{"field": f, **cap["scored"][f], "display": capture.display(f, cap["scored"][f]["values"]),
                    "confidence_label": capture.confidence_label(cap["scored"][f]["confidence"]), **routing[f]}
                   for f in capture.FIELDS],
        "options": {k: [{"value": v, "label": l} for v, l in opts] for k, opts in capture.ENUM_OPTIONS.items()},
        "confirmed": bool(session),
    }


class ConfirmBody(BaseModel):
    capture_id: str
    values: dict[str, dict]
    seconds: float


@app.post("/api/capture/{deal_id}/confirm")
def confirm(deal_id: str, body: ConfirmBody, background: BackgroundTasks) -> dict:
    crm = _deal(deal_id)
    cap = service.find_capture(body.capture_id)
    if not cap or cap["deal_id"] != deal_id:
        raise HTTPException(404, "unknown card")
    allowed = {f: set(capture.field_values_template(f)) for f in capture.FIELDS}
    values = {f: {k: str(v)[:400] for k, v in (body.values.get(f) or {}).items() if k in allowed[f]}
              for f in capture.FIELDS if f in body.values}
    session = service.confirm_capture(cap, crm["owner_ae"], values, max(0.0, min(body.seconds, 3600.0)), "web")
    refreshing = bool(session["corrected"]) and config.MODE != "replay"
    if refreshing:  # steps and drafts are rebuilt with the AE's corrections; the page fetches /api/payoff again
        background.add_task(service.refresh_with_confirmed, deal_id, session["final"])
    out = payoff(deal_id, session["final"])
    out["refreshing"] = refreshing
    out["refresh_note"] = ("Updating the steps and recap with your corrections. They appear here in about a minute."
                           if refreshing else
                           "Steps and recap were drafted from the agent's values. With the live model connected, "
                           "they are rebuilt from your corrections." if session["corrected"] else "")
    return {"session": session, "payoff": out}


@app.get("/api/payoff/{deal_id}")
def payoff_now(deal_id: str) -> dict:
    _deal(deal_id)
    sess = None
    cap, _ = service.load_capture(deal_id, allow_run=False)
    if cap:
        sess = capture.session_for(cap["capture_id"])
    final = {l["field"]: json.loads(l["ae_value"]) for l in (sess or {}).get("labels", [])}
    return payoff(deal_id, final)


def payoff(deal_id: str, final: dict) -> dict:
    """Shown right after confirm: next best steps, the recap draft for approval, and the stakeholder map."""
    crm = FileCRMSource().deal(deal_id)
    record, source = service.load_debrief(deal_id)
    if not record:
        return {"available": False, "reason": "The debrief for this call is not ready yet."}
    a = (record.get("artifacts", {}).get("assessment") or {}).get("current") or {}
    recap = (record.get("artifacts", {}).get("recap_email") or {})
    from src.transcript import load_transcript
    t = load_transcript(deal_id)
    steps = []
    for s in a.get("next_steps", [])[:3]:
        quote = t.render_quote(s["evidence"][0]["utterance_id"]) if s.get("evidence") else None
        steps.append({**s, "quote": quote})
    return {
        "available": True, "source": source, "sample_label": record.get("sample_label", ""),
        "deal_state": a.get("deal_state", ""), "deal_state_why": a.get("deal_state_why", ""),
        "next_steps": steps,
        "recap": {"subject": (recap.get("current") or {}).get("subject", ""),
                  "body": (recap.get("current") or {}).get("body", ""),
                  "needs_review": bool(recap.get("needs_review")), "flagged": recap.get("flagged", [])},
        "stakeholders": capture.stakeholder_map(record.get("extraction") or {}, crm, final),
        "crm_written": capture.crm_fields(final),
    }


# Intake

class MeetingBody(BaseModel):
    deal_id: str
    transcript: str
    crm: dict


@app.post("/meetings")
def meetings(body: MeetingBody) -> dict:
    """Accept a transcript and CRM context, store them like the Gong and CRM adapters would, and run the same
    pipeline the Gong trigger runs (debrief, then the pre-filled confirm card)."""
    from src import ingest
    from src.adapters import FileCRMSource as CRM, FileGongSource as Gong
    if not _DEAL_RE.match(body.deal_id):
        raise HTTPException(400, "deal_id must be lowercase letters, digits or underscores")
    base = config.ROOT / "var" / "meetings"
    for sub in ("transcripts", "crm", "gong_activity"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (base / "transcripts" / f"{body.deal_id}.txt").write_text(body.transcript, encoding="utf-8")
    crm = {**body.crm, "deal_id": body.deal_id}
    (base / "crm" / f"{body.deal_id}.json").write_text(json.dumps(crm, indent=1), encoding="utf-8")
    (base / "gong_activity" / f"{body.deal_id}.json").write_text(
        json.dumps({"deal_id": body.deal_id, "post_demo_activity": []}), encoding="utf-8")
    try:
        return ingest.process_call(body.deal_id, gong=Gong(base), crm_source=CRM(base),
                                   ledger_path=base / "ledger.json")
    except Exception as e:  # bad transcript format or missing CRM keys; report, do not crash the server
        raise HTTPException(422, f"{type(e).__name__}: {e}"[:300])


# Metrics

@app.get("/metrics")
def metrics() -> dict:
    return {"measured": capture.metrics(simulated=False), "simulated": capture.metrics(simulated=True),
            "threshold": config.CAPTURE_THRESHOLD, "warmup": config.CAPTURE_JUDGMENT_WARMUP,
            "spot_check_rate": config.CAPTURE_SPOT_CHECK_RATE}


@app.get("/api/simulate")
def simulate(threshold: float = 0.9, simulated: bool = False) -> dict:
    return capture.simulate_threshold(max(0.0, min(threshold, 1.0)), simulated=simulated)


# Slack

@app.post("/slack/interactions")
async def slack_interactions(request: Request) -> JSONResponse:
    body = await request.body()
    secret = os.environ.get("DEBRIEF_SLACK_SIGNING_SECRET", "")
    if not slack_actions.verify(secret, request.headers.get("X-Slack-Request-Timestamp", ""), body,
                                request.headers.get("X-Slack-Signature", "")):
        raise HTTPException(401, "bad signature")
    payload = json.loads(parse_qs(body.decode("utf-8")).get("payload", ["{}"])[0])
    return JSONResponse(slack_actions.handle(payload))
