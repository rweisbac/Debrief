"""CS handoff brief (Phase 2 preview), built from the stored debrief record. No model calls."""
from __future__ import annotations

UNKNOWN = "Unknown after TV demo"


def brief(record: dict, crm: dict) -> dict:
    """One page brief for the CSM. Every section comes from the record captured at the TV demo."""
    ex = record.get("extraction") or {}
    med = record.get("meddpicc") or {}
    stakeholders = [f"{s['name']} ({s['title'] or s['why_they_matter']}){'' if s['present'] else ', not in the demo'}"
                    for s in ex.get("stakeholders", [])]
    outcome = ex.get("business_outcome") or {}
    objections = [f"{o['summary']}: {o['answer_given'] or 'no answer given'} ({o['status'].replace('_', ' ')})"
                  for o in ex.get("objections", [])]
    open_items = [f"{i['summary']} (owner: {i['owner']})" for i in ex.get("open_technical_items", [])]
    commitments = [f"{c['who']}: {c['what']}" + (f" by {c['by_when']}" if c["by_when"] else "")
                   for c in ex.get("commitments", [])]
    risks = [r["summary"] for r in ex.get("risk_signals", [])] + [c["summary"] for c in ex.get("contradictions", [])]
    gaps = [name.replace("_", " ") for name, f in med.items() if f.get("status") == "unknown"]

    first_30 = []
    if outcome.get("stated"):
        first_30.append(f"Agree how to measure the stated outcome in week 1: {outcome['summary']}")
    else:
        first_30.append("Ask the champion for the business outcome in week 1; it was not stated in the TV demo")
    first_30 += [f"Close the open item: {i}" for i in open_items[:2]]
    apex_commitments = [f"{c['who']}: {c['what']}" for c in ex.get("commitments", []) if c.get("side") == "apex"]
    first_30 += [f"Confirm with the customer that this was delivered: {c}" for c in apex_commitments[:2]]
    if risks:
        first_30.append(f"Watch: {risks[0]}")
    return {
        "label": "Phase 2 preview",
        "account": crm.get("account", ""),
        "champion": crm.get("champion") or UNKNOWN,
        "stakeholders": stakeholders or [UNKNOWN],
        "business_outcome": outcome.get("summary") if outcome.get("stated") else "Not stated in the TV demo",
        "objections_and_resolutions": objections or ["None raised"],
        "open_technical_items": open_items or ["None"],
        "integration_patterns": [p["summary"] for p in ex.get("integration_patterns", [])] or ["None agreed"],
        "commitments": commitments or ["None"],
        "risks": risks or ["None noted"],
        "meddpicc_gaps": [f"{g}: {UNKNOWN}" for g in gaps] or ["None"],
        "suggested_first_30_days": first_30,
    }
