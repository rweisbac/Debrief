"""Score capture fields against the hand labels in data/gold_capture, and simulate an AE confirming a card.

A field is right when:
- priority_why_now: stated in the call and every must_mention group appears in the value; or not stated and the
  value is empty or says it was not stated
- champion_status: the champion status and the economic buyer answer are both in the accepted lists
- top_risk: the risk is in the accepted list
- next_step: no step was agreed and the value and date are empty; or a step was agreed, the date matches and every
  must_mention group appears

The simulated AE accepts a right field and types the gold ae_value for a wrong one. It is a stand-in for real
confirms and is labeled simulated everywhere it shows up.
"""
from __future__ import annotations

import json

from src.config import ROOT

GOLD = ROOT / "data" / "gold_capture"
NOT_STATED = ("not stated", "no trigger", "none stated")
# Simulated timing, in seconds: a glance at the card, then each question and each correction.
SIM_BASE, SIM_PER_QUESTION, SIM_PER_CORRECTION = 4.0, 5.0, 9.0


def gold(deal_id: str) -> dict:
    return json.loads((GOLD / f"{deal_id}.json").read_text(encoding="utf-8"))


def deals() -> list[str]:
    return sorted(p.stem for p in GOLD.glob("deal_*.json"))


def _mentions(text: str, groups: list[list[str]]) -> bool:
    t = text.lower()
    return all(any(alt.lower() in t for alt in group) for group in groups)


def field_correct(field: str, g: dict, v: dict) -> bool:
    if field == "priority_why_now":
        val = (v.get("value") or "").strip()
        if not g["stated"]:
            return not val or any(p in val.lower() for p in NOT_STATED)
        return bool(val) and _mentions(val, g["must_mention"])
    if field == "champion_status":
        return v.get("value") in g["accepted"] and v.get("economic_buyer_identified") in g["economic_buyer_identified"]
    if field == "top_risk":
        return v.get("value") in g["accepted"]
    if field == "next_step":
        if not g["exists"]:
            return not (v.get("value") or "").strip() and not v.get("date")
        return v.get("date") == g["date"] and _mentions(v.get("value") or "", g["must_mention"])
    raise ValueError(field)


def simulate_ae(g: dict, scored: dict, routing: dict) -> tuple[dict, float, list[str]]:
    """Returns (edits to submit, simulated seconds, fields corrected). The simulated AE checks every field, which
    is kinder than reality: a real AE rarely reopens a field the agent confirmed."""
    edits, wrong = {}, []
    for field, s in scored.items():
        if not field_correct(field, g[field], s["values"]):
            edits[field] = dict(g[field]["ae_value"])
            wrong.append(field)
    asked = sum(1 for r in routing.values() if r["mode"] == "ask")
    seconds = SIM_BASE + SIM_PER_QUESTION * asked + SIM_PER_CORRECTION * len(wrong)
    return edits, seconds, wrong
