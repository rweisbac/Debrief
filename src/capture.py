"""Post-demo capture: "confirm, don't write".

The agent pre-fills 4 fields of AE judgment from the transcript and CRM. The AE confirms or corrects them in
under a minute. Every confirm is stored as a labeled example, so the confidence shown to the AE can be checked
against how often the AE agreed.

Confidence is computed in code, not taken from the model. The model's own probability is the starting point and
is then capped by signals that can be checked:
- no basis: 0
- no cited line, or a cited line that does not match the transcript: at most 0.4
- inferred rather than said in the call: at most 0.75
- the CRM disagrees on the champion or economic buyer: at most 0.6
- top risk "other": at most 0.6 (free text needs a human read)
- a next step date that was not said in the call: at most 0.5, and never auto-confirmed

Routing: a field at or above the threshold is confirmed by the agent and collapsed. Below it, the AE is asked.
champion_status and top_risk are judgment fields and are always asked for each AE's first N confirms. A fixed
share of auto-confirmed fields is asked anyway as a spot check: an AE rarely reopens a collapsed field, so
without spot checks the error rate among auto-confirmed fields would look better than it is.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from src import config, record_store
from src.checks import call_dates
from src.llm import CallResult, LLMClient
from src.prompts import load
from src.schemas import BasisEnum, CaptureRecord, ExtractionRecord, TopRiskEnum, validate_capture
from src.transcript import Transcript

FIELDS = ["priority_why_now", "champion_status", "top_risk", "next_step"]
JUDGMENT_FIELDS = {"champion_status", "top_risk"}
LABELS = {"priority_why_now": "Priority and why now", "champion_status": "Champion and economic buyer",
          "top_risk": "Top risk", "next_step": "Next step"}
# The parts of each field that count when deciding whether the AE corrected it. Names and notes are shown and
# editable but are not graded.
GRADED = {"priority_why_now": ("value",), "champion_status": ("value", "economic_buyer_identified"),
          "top_risk": ("value",), "next_step": ("value", "date")}
BUCKETS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0001)]

CAP_NO_EVIDENCE, CAP_INFERRED, CAP_CRM_DISAGREES, CAP_OTHER, CAP_DATE_NOT_SAID = 0.4, 0.75, 0.6, 0.6, 0.5


# Model call

async def run_capture(llm: LLMClient, transcript: Transcript, context_block: dict, extraction: ExtractionRecord,
                      debrief_id: str) -> CallResult:
    """One call. Same cached prefix as the debrief chain, plus the extraction so the two agree."""
    rules_text, version = load("capture")

    def validator(c: CaptureRecord) -> list[str]:
        errors = validate_capture(c)
        for f in FIELDS:
            for ref in getattr(c, f).evidence:
                ok, reason = transcript.resolve_evidence(ref.utterance_id, ref.excerpt)
                if not ok:
                    errors.append(f"{f} evidence {ref.utterance_id} {ref.excerpt!r}: {reason}. Copy it word for word.")
        return errors

    block = {"type": "text", "text": "<extraction>\n" + json.dumps(extraction.model_dump(mode="json"), indent=1,
                                                                     sort_keys=True) + "\n</extraction>"}
    return await llm.acall(step="capture", output_model=CaptureRecord, step_rules=rules_text,
                           prompt_version=version, user_blocks=[context_block, block], debrief_id=debrief_id,
                           validator=validator)


# Confidence

def field_values(record: CaptureRecord) -> dict[str, dict]:
    """Flat values per field, as the AE sees and edits them."""
    p, c, r, n = record.priority_why_now, record.champion_status, record.top_risk, record.next_step
    return {
        "priority_why_now": {"value": p.value},
        "champion_status": {"value": c.value.value, "champion_name": c.champion_name,
                            "economic_buyer_identified": c.economic_buyer_identified.value,
                            "economic_buyer_name": c.economic_buyer_name},
        "top_risk": {"value": r.value.value, "note": r.note},
        "next_step": {"value": n.value, "date": n.date},
    }


def _names_match(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a and b) and (a in b or b in a)


def score(record: CaptureRecord, transcript: Transcript, crm: dict, as_of: date) -> dict[str, dict]:
    """Per field: values, confidence, the signals that set it, quotes rendered from the transcript, and whether
    the field may ever be auto-confirmed."""
    values = field_values(record)
    customers = {p.name for p in transcript.participants if p.side == "customer"}
    said_dates = call_dates(transcript, as_of)
    out = {}
    for name in FIELDS:
        f = getattr(record, name)
        conf = max(0.0, min(1.0, float(f.model_confidence)))
        signals: list[str] = []
        auto_eligible = True

        def cap(limit: float, why: str) -> None:
            nonlocal conf
            if conf > limit:
                conf = limit
            signals.append(why)

        resolved = [e for e in f.evidence if transcript.resolve_evidence(e.utterance_id, e.excerpt)[0]]
        if f.basis == BasisEnum.none:
            conf = 0.0
            signals.append("Not found in the call; add it if there is one")
        else:
            if not f.evidence:
                cap(CAP_NO_EVIDENCE, "No line from the call cited")
            elif len(resolved) < len(f.evidence):
                cap(CAP_NO_EVIDENCE, "A cited line does not match the transcript")
            if f.basis == BasisEnum.inferred:
                cap(CAP_INFERRED, "Inferred, not said in the call")

        if name == "champion_status":
            crm_champ, crm_eb = crm.get("champion", ""), crm.get("economic_buyer", "")
            if f.value.value == "strong" and f.champion_name and f.champion_name not in customers:
                cap(CAP_CRM_DISAGREES, f"{f.champion_name} was not a customer in the call")
            if crm_champ and f.champion_name and not _names_match(crm_champ, f.champion_name):
                cap(CAP_CRM_DISAGREES, f"CRM lists {crm_champ} as champion")
            if crm_eb and f.economic_buyer_identified.value == "no":
                cap(CAP_CRM_DISAGREES, f"CRM names {crm_eb} as economic buyer")
            if crm_eb and f.economic_buyer_name and not _names_match(crm_eb, f.economic_buyer_name):
                cap(CAP_CRM_DISAGREES, f"CRM names {crm_eb} as economic buyer")
        if name == "top_risk" and f.value == TopRiskEnum.other:
            cap(CAP_OTHER, "Other risk needs a human read")
        if name == "next_step" and f.date:
            try:
                said = date.fromisoformat(f.date) in said_dates
            except ValueError:
                said = False
            if not said:
                cap(CAP_DATE_NOT_SAID, "Date was not said in the call")
                auto_eligible = False

        if not signals and conf > 0:
            signals.append("Said in the call, with a matching line")
        quotes = [transcript.render_quote(e.utterance_id) for e in resolved[:2]]
        out[name] = {"label": LABELS[name], "values": values[name], "basis": f.basis.value,
                     "model_confidence": round(float(f.model_confidence), 2), "confidence": round(conf, 2),
                     "signals": signals, "quotes": quotes, "auto_eligible": auto_eligible}
    return out


# Routing

def _spot_check(key: str, field: str, rate: float) -> bool:
    digest = hashlib.sha256(f"{key}:{field}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF < rate


def route(scored: dict[str, dict], *, ae_confirms_so_far: int, threshold: float | None = None,
          warmup: int | None = None, spot_rate: float | None = None, spot_key: str = "") -> dict[str, dict]:
    """Per field: mode "auto" (confirmed by the agent, collapsed) or "ask" (needs the AE), and why."""
    threshold = config.CAPTURE_THRESHOLD if threshold is None else threshold
    warmup = config.CAPTURE_JUDGMENT_WARMUP if warmup is None else warmup
    spot_rate = config.CAPTURE_SPOT_CHECK_RATE if spot_rate is None else spot_rate
    out = {}
    for name in FIELDS:
        s = scored[name]
        if name in JUDGMENT_FIELDS and ae_confirms_so_far < warmup:
            out[name] = {"mode": "ask", "reason": f"Judgment call: always confirmed for your first {warmup} demos"}
        elif not s["auto_eligible"]:
            out[name] = {"mode": "ask", "reason": "Needs your call: " + s["signals"][0]}
        elif s["confidence"] < threshold:
            out[name] = {"mode": "ask", "reason": "Needs your call: " + (s["signals"][0] if s["signals"] else
                                                                          "low confidence")}
        elif spot_key and _spot_check(spot_key, name, spot_rate):
            out[name] = {"mode": "ask", "reason": "Spot check: we ask about a few confident fields to keep "
                                                  "the agent honest"}
        else:
            out[name] = {"mode": "auto", "reason": "Confirmed by agent"}
    return out


# Storage

def save_capture(deal_id: str, record: CaptureRecord, scored: dict, source: str, debrief_id: str = "",
                 db_path: Path | None = None) -> dict:
    capture_id = f"{deal_id}-cap-{uuid.uuid4().hex[:8]}"
    payload = {"capture_id": capture_id, "deal_id": deal_id, "debrief_id": debrief_id, "source": source,
               "record": record.model_dump(mode="json"), "scored": scored}
    with record_store.connect(db_path) as conn:
        conn.execute("INSERT INTO captures VALUES (?, ?, ?, ?, ?)",
                     (capture_id, deal_id, datetime.now(timezone.utc).isoformat(), source, json.dumps(payload)))
    return payload


def latest_capture(deal_id: str, db_path: Path | None = None) -> dict | None:
    with record_store.connect(db_path) as conn:
        row = conn.execute("SELECT payload FROM captures WHERE deal_id = ? ORDER BY created_at DESC LIMIT 1",
                           (deal_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def ae_confirms(ae: str, simulated: bool = False, db_path: Path | None = None) -> int:
    with record_store.connect(db_path) as conn:
        (n,) = conn.execute("SELECT COUNT(*) FROM capture_sessions WHERE ae = ? AND simulated = ?",
                            (ae, int(simulated))).fetchone()
    return n


def session_for(capture_id: str, db_path: Path | None = None) -> dict | None:
    with record_store.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM capture_sessions WHERE capture_id = ? AND simulated = 0 "
                           "ORDER BY submitted_at DESC LIMIT 1", (capture_id,)).fetchone()
        if not row:
            return None
        labels = conn.execute("SELECT * FROM capture_labels WHERE session_id = ?", (row["session_id"],)).fetchall()
    return {**dict(row), "labels": [dict(r) for r in labels]}


def _norm(v) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", str(v).lower())).strip()


def corrected(field: str, agent: dict, final: dict) -> bool:
    return any(_norm(agent.get(k, "")) != _norm(final.get(k, "")) for k in GRADED[field])


def submit(capture: dict, ae: str, final_values: dict[str, dict], seconds: float, *, simulated: bool = False,
           threshold: float | None = None, db_path: Path | None = None) -> dict:
    """Store one AE confirm. Routing is recomputed here, before the session is counted, so it matches the card
    the AE saw. Returns the session with per field labels."""
    threshold = config.CAPTURE_THRESHOLD if threshold is None else threshold
    routing = route(capture["scored"], ae_confirms_so_far=ae_confirms(ae, simulated, db_path),
                    threshold=threshold, spot_key=capture["capture_id"])
    session_id = uuid.uuid4().hex
    rows = []
    for name in FIELDS:
        agent = capture["scored"][name]["values"]
        final = {**agent, **(final_values.get(name) or {})}
        rows.append((session_id, capture["deal_id"], name, json.dumps(agent, sort_keys=True),
                     capture["scored"][name]["confidence"], int(routing[name]["mode"] == "auto"),
                     json.dumps(final, sort_keys=True), int(corrected(name, agent, final)), int(simulated)))
    asked = sum(1 for r in routing.values() if r["mode"] == "ask")
    with record_store.connect(db_path) as conn:
        conn.execute("INSERT INTO capture_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (session_id, capture["capture_id"], capture["deal_id"], ae,
                      datetime.now(timezone.utc).isoformat(), float(seconds), asked, threshold, int(simulated)))
        conn.executemany("INSERT INTO capture_labels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return {"session_id": session_id, "questions_shown": asked, "routing": routing,
            "corrected": [r[2] for r in rows if r[7]],
            "final": {r[2]: json.loads(r[6]) for r in rows}}


# Metrics

def _labels(simulated: bool, db_path: Path | None = None) -> list[dict]:
    with record_store.connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM capture_labels WHERE simulated = ?", (int(simulated),))]


def _sessions(simulated: bool, db_path: Path | None = None) -> list[dict]:
    with record_store.connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM capture_sessions WHERE simulated = ? ORDER BY "
                                              "submitted_at", (int(simulated),))]


def _share(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def metrics(simulated: bool = False, db_path: Path | None = None) -> dict:
    """Accuracy means the AE did not correct the field. For auto-confirmed fields that is an upper bound,
    since a collapsed field is rarely reopened; spot-checked fields are the unbiased sample."""
    labels, sessions = _labels(simulated, db_path), _sessions(simulated, db_path)
    per_field = {}
    for f in FIELDS:
        rows = [l for l in labels if l["field"] == f]
        per_field[f] = {"n": len(rows), "accuracy": _share(sum(1 for l in rows if not l["was_corrected"]), len(rows))}
    calibration = []
    for lo, hi in BUCKETS:
        rows = [l for l in labels if lo <= l["confidence"] < hi]
        calibration.append({"bucket": f"{lo:.1f} to {min(hi, 1.0):.1f}", "n": len(rows),
                            "accuracy": _share(sum(1 for l in rows if not l["was_corrected"]), len(rows))})
    secs = [s["seconds_to_complete"] for s in sessions]
    trend = [s["questions_shown"] for s in sessions]
    return {
        "simulated": simulated, "sessions": len(sessions), "fields": len(labels),
        "per_field_accuracy": per_field, "calibration": calibration,
        "auto_confirm_rate": _share(sum(l["auto_confirmed"] for l in labels), len(labels)),
        "avg_questions_per_meeting": round(statistics.mean(trend), 2) if trend else None,
        "questions_trend": trend,
        "median_seconds_to_complete": round(statistics.median(secs), 1) if secs else None,
    }


def simulate_threshold(threshold: float, simulated: bool = False, db_path: Path | None = None) -> dict:
    """Recompute from stored labels what a different threshold would have done: share of fields auto-confirmed,
    and the error rate among them (fields the AE corrected). Ignores the judgment warmup and spot checks."""
    labels = _labels(simulated, db_path)
    auto = [l for l in labels if l["confidence"] >= threshold]
    return {"threshold": threshold, "fields": len(labels), "auto_confirm_rate": _share(len(auto), len(labels)),
            "error_rate_among_auto": _share(sum(l["was_corrected"] for l in auto), len(auto)),
            "questions_per_meeting": round((len(labels) - len(auto)) / max(1, len({l["session_id"] for l in labels})),
                                           2) if labels else None}


# Stakeholder map (code only, no model call)

# An absent person gets a brief only when they are part of the decision (signs, approves, reviews, owns budget).
DECISION_RE = re.compile(r"\b(sign|approv|budget|econom|decid|decision|review|security|cfo|coo|ceo|cto|cio|vp|"
                         r"vice president|director|head of|chief|committee|boss|procurement|legal|finance)", re.I)

def stakeholder_map(extraction: dict, crm: dict, final: dict[str, dict]) -> list[dict]:
    """One row per customer stakeholder from the call record. Stance is supportive only for the confirmed
    champion, concerned only for someone who raised a concern that is still open, and unknown otherwise:
    a stance is never guessed from tone. Each row carries the line it rests on, when there is one."""
    champ = (final.get("champion_status") or {})
    champ_name = champ.get("champion_name", "") if champ.get("value") in {"strong", "unclear"} else ""
    eb_name = (champ.get("economic_buyer_name") or crm.get("economic_buyer", "")).strip()
    open_by: dict[str, dict] = {}
    for o in extraction.get("objections", []):
        if o.get("status") != "resolved" and o.get("raised_by"):
            open_by.setdefault(o["raised_by"], o)
    rows = []
    for s in extraction.get("stakeholders", []):
        name = s["name"]
        evidence = (s.get("evidence") or [{}])[0].get("utterance_id", "")
        if champ_name and _names_match(name, champ_name):
            stance, touch = "supportive", "Send the recap written so they can forward it unedited (PB-01)"
        elif name in open_by:
            stance = "concerned"
            touch = f"Answer their open concern in writing: {open_by[name]['summary']}"
            evidence = (open_by[name].get("evidence") or [{}])[0].get("utterance_id", evidence)
        else:
            stance, touch = "unknown", "Include on the recap"
        if not s.get("present", True):
            matters = DECISION_RE.search(f"{s.get('title', '')} {s.get('why_they_matter', '')}")
            if eb_name and _names_match(name, eb_name):
                touch = "Brief through the champion before any commercials: outcome, risk, time to value (PB-03)"
            elif matters:
                touch = "Give the champion a 1 page brief that answers this person's likely question (PB-05)"
            else:
                touch = "No action: mentioned in passing, not part of the decision"
        rows.append({"name": name, "role": s.get("title") or s.get("why_they_matter", ""),
                     "present": bool(s.get("present", True)), "stance": stance, "next_touch": touch,
                     "evidence_utterance_id": evidence})
    return rows


# Display (shared by the Slack card and the web page)

ENUM_OPTIONS = {
    "champion_status.value": [("strong", "Strong"), ("unclear", "Unclear"), ("absent", "Absent")],
    "champion_status.economic_buyer_identified": [("yes", "Yes"), ("no", "No"), ("unclear", "Unclear")],
    "top_risk.value": [("budget", "Budget"), ("timeline", "Timeline"), ("competitor", "Competitor"),
                       ("security_review", "Security review"), ("integration", "Integration"),
                       ("no_urgency", "No urgency"), ("other", "Other")],
}


def option_label(key: str, value: str) -> str:
    return dict(ENUM_OPTIONS.get(key, [])).get(value, value)


def display(field: str, v: dict) -> str:
    """One line a rep can read at a glance."""
    if field == "priority_why_now":
        return v.get("value") or "Not stated in the call"
    if field == "champion_status":
        champ = option_label("champion_status.value", v.get("value", ""))
        if v.get("champion_name"):
            champ += f": {v['champion_name']}"
        eb = option_label("champion_status.economic_buyer_identified", v.get("economic_buyer_identified", ""))
        eb_line = f"Economic buyer named: {eb}" + (f" ({v['economic_buyer_name']})" if v.get("economic_buyer_name") else "")
        return f"{champ}. {eb_line}"
    if field == "top_risk":
        risk = option_label("top_risk.value", v.get("value", ""))
        return f"{risk}: {v['note']}" if v.get("note") else risk
    if field == "next_step":
        if not v.get("value"):
            return "No next step agreed in the call"
        return f"{v['value']}" + (f" ({v['date']})" if v.get("date") else ", no date")
    return json.dumps(v)


def confidence_label(conf: float) -> str:
    return "High" if conf >= 0.9 else "Medium" if conf >= 0.7 else "Low"


# CRM write-back

CRM_FIELD_MAP = {  # Salesforce opportunity fields; NextStep is standard, the rest are custom fields to create
    ("priority_why_now", "value"): "Why_Now__c",
    ("champion_status", "value"): "Champion_Status__c",
    ("champion_status", "champion_name"): "Champion__c",
    ("champion_status", "economic_buyer_identified"): "Economic_Buyer_Identified__c",
    ("champion_status", "economic_buyer_name"): "Economic_Buyer__c",
    ("top_risk", "value"): "Top_Risk__c",
    ("top_risk", "note"): "Top_Risk_Note__c",
    ("next_step", "value"): "NextStep",
    ("next_step", "date"): "Next_Step_Date__c",
}


def crm_fields(final: dict[str, dict]) -> dict:
    return {crm: final.get(field, {}).get(part, "") for (field, part), crm in CRM_FIELD_MAP.items()}


def field_values_template(field: str) -> tuple[str, ...]:
    """The parts of a field the AE may set."""
    return {"priority_why_now": ("value",),
            "champion_status": ("value", "champion_name", "economic_buyer_identified", "economic_buyer_name"),
            "top_risk": ("value", "note"), "next_step": ("value", "date")}[field]
