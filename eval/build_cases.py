"""Write CRM and Gong-style activity files for the eval transcripts in eval/data/transcripts.

Synthetic data, fictional companies. Run: python eval/build_cases.py
Each case lists its account facts here; transcripts are hand-written text files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.transcript import load_transcript  # noqa: E402

DATA = ROOT / "eval" / "data"
NOTE = "Synthetic data, fictional company. Eval case for interview prep."

# id: account, industry, acv, demo (date, start, end, tz), champion, economic buyer, outcome, pains,
# decision process, competitors, checklist values (dated next step, stakeholder to add, sc commitment)
CASES = {
    "e01": dict(account="Northwind Grocers", industry="Retail", acv=310000, date="2026-09-28", start="09:00",
                end="09:09", champion="Maya Lindqvist", eb="", outcome="Store managers see on hand including open orders within minutes.",
                pains=["Shipping to stores that are already full"], process="Not discussed.", competitors=[],
                checklist=("CFO meeting Oct 6", "Priscilla, CFO", "Change feed setup doc"),
                extra_contacts=[("Priscilla Grant", "CFO", "economic_buyer")]),
    "e02": dict(account="Calder Bank", industry="Financial services", acv=520000, date="2026-09-29", start="10:00",
                end="10:10", champion="Gregor Hale", eb="", outcome="", pains=["Governance spread across three tools"],
                process="Not discussed.", competitors=[], checklist=("Reconnect week after next", "", ""),
                extra_contacts=[]),
    "e03": dict(account="Harbor Freightways", industry="Logistics", acv=180000, date="2026-09-28", start="13:00",
                end="13:09", champion="Frank Delacroix", eb="", outcome="Dispatch sees every truck in real time.",
                pains=["Positions update every 5 minutes"], process="Not discussed.", competitors=[],
                checklist=("", "", "Residency answer by Oct 1"), extra_contacts=[]),
    "e04": dict(account="Vela Therapeutics", industry="Life sciences", acv=450000, date="2026-09-30", start="11:00",
                end="11:10", champion="Simone Achebe", eb="", outcome="", pains=["Audit trail spread across systems"],
                process="CISO sign off required for trial data.", competitors=[], checklist=("", "", ""),
                extra_contacts=[("Dr. Amaka Okafor", "CISO", "security")]),
    "e05": dict(account="Brightline Media", industry="Media", acv=275000, date="2026-10-01", start="14:00",
                end="14:18", champion="Doug Whitfield", eb="", outcome="Daily audience numbers without the four hour job.",
                pains=["Dedupe job takes four hours and fails at night"], process="Budget planning in November.",
                competitors=[], checklist=("One pager for Ann by Oct 7", "Ann, data budget owner", ""),
                extra_contacts=[]),
    "e06": dict(account="Ostrava Precision Works", industry="Manufacturing", acv=390000, date="2026-10-01",
                start="09:00", end="09:10", champion="Petra Novak", eb="", outcome="Plant managers see downtime by cause per shift.",
                pains=["Weekly downtime spreadsheet"], process="Not discussed.", competitors=[],
                checklist=("Pilot on line 3", "", "Pilot plan by Oct 5"), extra_contacts=[]),
    "e07": dict(account="Summit Health Plans", industry="Healthcare", acv=600000, date="2026-10-01", start="10:00",
                end="10:07", champion="Monica Reyes", eb="", outcome="Actuaries see the cost trend daily instead of six weeks late.",
                pains=["Monthly cost trend"], process="Vendor security review, then finance.", competitors=[],
                checklist=("Review board Oct 22", "Daniel, finance", "Data flow diagram by Oct 9"), extra_contacts=[]),
    "e08": dict(account="Kestrel Outfitters", industry="Retail", acv=340000, date="2026-09-30", start="15:00",
                end="15:08", champion="Rachel Kim", eb="", outcome="Days to reorder point by store with open orders.",
                pains=["Batch inventory is a day stale"], process="Leadership approval for a second platform.",
                competitors=["Lakestream"], checklist=("Cost comparison review Oct 14", "", "Workload cost comparison"),
                extra_contacts=[]),
    "e09": dict(account="Juniper Energy", industry="Utilities", acv=120000, date="2026-09-29", start="16:00",
                end="16:06", champion="", eb="", outcome="", pains=["Meter data loads are manual"],
                process="Not discussed.", competitors=[], checklist=("", "", ""), extra_contacts=[]),
    "e10": dict(account="Corvid Telecom", industry="Telecommunications", acv=480000, date="2026-10-02", start="09:00",
                end="09:07", champion="Fatima Zahid", eb="", outcome="", pains=["Usage pipeline takes 5 hours"],
                process="Architecture board approves SSO design.", competitors=[],
                checklist=("Architecture board Nov 3", "", "SSO design and nested claims date by Oct 9"),
                extra_contacts=[]),
    "e11": dict(account="Alder State University", industry="Higher education", acv=150000, date="2026-09-30",
                start="13:00", end="13:07", champion="Dr. Elise Martin", eb="Dr. Abernathy", outcome="",
                pains=["Retention reporting is manual"], process="Provost approval and technology committee.",
                competitors=[], checklist=("", "", ""), extra_contacts=[]),
    "e12": dict(account="Mosaic Mutual Insurance", industry="Insurance", acv=410000, date="2026-10-01",
                start="15:00", end="15:09", champion="Neil Patterson", eb="Neil Patterson",
                outcome="Daily loss ratio to change how we reprice.", pains=["Monthly loss ratio report"],
                process="Not discussed.", competitors=[], checklist=("Signature by Oct 30", "", ""),
                extra_contacts=[]),
    "e13": dict(account="Tidewater Port Authority", industry="Transportation", acv=530000, date="2026-10-02",
                start="08:00", end="08:09", champion="Henrik Larsen", eb="", outcome="Crane operators get data in under 2 seconds.",
                pains=["Telemetry latency"], process="Not discussed.", competitors=[],
                checklist=("Results review Oct 12", "", "Dedicated cluster latency test by Oct 8"), extra_contacts=[]),
    "e14": dict(account="Pinehurst Hotels Europe", industry="Hospitality", acv=370000, date="2026-10-01",
                start="11:00", end="11:07", champion="Charlotte Dubois", eb="", outcome="",
                pains=["Guest records split across three booking systems"], process="Group security office review.",
                competitors=[], checklist=("", "", "Support access wording by Oct 7"), extra_contacts=[]),
    "e15": dict(account="Granite Payments", industry="Financial services", acv=560000, date="2026-10-02",
                start="10:00", end="10:07", champion="Liam O'Connor", eb="", outcome="Fraud features fresh within seconds, not an hour.",
                pains=["Features are an hour stale"], process="Not discussed.", competitors=[],
                checklist=("Talk next week", "", ""), extra_contacts=[]),
}

ROLE_BY_TITLE = {"cfo": "economic_buyer", "security": "security", "ciso": "security"}


def contacts(case_id: str, c: dict) -> list[dict]:
    t = load_transcript(case_id, DATA / "transcripts")
    out = []
    for p in t.participants:
        if p.side != "customer":
            continue
        role = "champion" if p.name == c["champion"] else next(
            (r for k, r in ROLE_BY_TITLE.items() if k in p.title.lower()), "technical_evaluator")
        email = p.name.lower().replace("dr. ", "").replace("'", "").replace(" ", ".") + f"@{case_id}.example"
        out.append({"name": p.name, "title": p.title, "role": role, "email": email, "phone": ""})
    for name, title, role in c["extra_contacts"]:
        out.append({"name": name, "title": title, "role": role, "email": "", "phone": ""})
    return out


def build(case_id: str, c: dict) -> None:
    t = load_transcript(case_id, DATA / "transcripts")
    ae = next(p.name for p in t.participants if p.side == "apex" and "Account" in p.title)
    sc = next(p.name for p in t.participants if p.side == "apex" and "Solutions" in p.title)
    tz = "-05:00"
    start, end = f"{c['date']}T{c['start']}:00{tz}", f"{c['date']}T{c['end']}:00{tz}"
    nxt, stake, scc = c["checklist"]
    filled = f"{c['date']}T{c['end']}:30{tz}"
    crm = {
        "deal_id": case_id, "account": c["account"], "segment": "Enterprise", "industry": c["industry"],
        "acv_usd": c["acv"], "stage": "Technical Validation", "close_date": "2026-12-18", "owner_ae": ae, "sc": sc,
        "pod": "Eval-1", "tv_entered_at": "2026-09-14T09:00:00-05:00", "contacts": contacts(case_id, c),
        "champion": c["champion"], "economic_buyer": c["eb"],
        "discovery_notes": {"stated_business_outcome": c["outcome"], "pains": c["pains"],
                            "decision_process": c["process"]},
        "prior_call_notes": [{"date": "2026-09-14", "type": "discovery", "summary": "Agreed the TV items."}],
        "competitors": c["competitors"],
        "demo": {"call_id": f"gong-{case_id}", "scheduled_start": start, "scheduled_end": end, "actual_end": end},
        "close_the_demo": {
            "started_at": start,
            "dated_next_step": {"value": nxt, "filled_at": filled if nxt else ""},
            "stakeholder_to_add": {"value": stake, "filled_at": filled if stake else ""},
            "business_outcome": {"value": c["outcome"], "prefilled_from_discovery": True, "edited": False,
                                 "filled_at": filled if c["outcome"] else ""},
            "sc_commitment": {"value": scc, "filled_at": filled if scc else ""},
        },
        "_note": NOTE,
    }
    activity = {"_note": NOTE, "deal_id": case_id, "call_id": f"gong-{case_id}", "started_at": start,
                "ended_at": end, "transcript_file": f"eval/data/transcripts/{case_id}.txt", "post_demo_activity": []}
    for sub, obj in (("crm", crm), ("gong_activity", activity)):
        (DATA / sub / f"{case_id}.json").write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    print(f"{case_id}: {len(t.utterances)} utterances, {t.word_count} words, AE {ae}, SC {sc}")


if __name__ == "__main__":
    for cid, case in CASES.items():
        build(cid, case)
