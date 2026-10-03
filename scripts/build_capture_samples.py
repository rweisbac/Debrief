"""Hand-written sample captures for the confirm card, used before any capture output is recorded.

These are NOT model output. Every place that shows them says so. They go through the real confidence and routing
code (src/capture.py), so the card shows what the code does with them. Excerpts are copied word for word from the
transcripts.

Run: python scripts/build_capture_samples.py   (writes fixtures/samples/capture_<deal>.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import schemas as S  # noqa: E402

OUT = ROOT / "fixtures" / "samples"
SAMPLE_LABEL = "Sample written by hand to show the confirm card. Not generated from the call."


def _ev(uid: str, excerpt: str) -> S.EvidenceRef:
    return S.EvidenceRef(utterance_id=uid, excerpt=excerpt)


def deal_a() -> S.CaptureRecord:
    """Halvorsen Freight: clear champion and a dated next step. Most fields should be confirmed by the agent."""
    return S.CaptureRecord(
        priority_why_now=S.CapturePriority(
            value="Catch late loads while dispatch can still reroute; detention fees are the COO's top question",
            basis="stated", model_confidence=0.93,
            evidence=[_ev("U035", "Detention fees and missed delivery windows are the number one thing the COO asks me about")]),
        champion_status=S.CaptureChampion(
            value="strong", champion_name="Dana Ortiz", economic_buyer_identified="yes",
            economic_buyer_name="Elena Varga", basis="stated", model_confidence=0.92,
            evidence=[_ev("U066", "she owns the budget line for this"),
                      _ev("U071", "Let me look at her calendar, I have access")]),
        top_risk=S.CaptureRisk(
            value="timeline", note="COO was burned by an 8 month project and will ask about time to value",
            basis="stated", model_confidence=0.8,
            evidence=[_ev("U076", "She got burned on the last platform project")]),
        next_step=S.CaptureNextStep(
            value="45 minute session with Elena Varga on the late load scenario", date="2026-10-08",
            basis="stated", model_confidence=0.96,
            evidence=[_ev("U072", "Thursday October 8th, 2pm Central, forty five minutes")]))


def deal_b() -> S.CaptureRecord:
    """Meridian Health: hidden blocker (security review) and no agreed next step. Most fields need the AE."""
    return S.CaptureRecord(
        priority_why_now=S.CapturePriority(
            value="A daily readmission risk list; with the weekly job, a third of patients are readmitted before outreach",
            basis="stated", model_confidence=0.9,
            evidence=[_ev("U027", "by Monday a third of the people on the list have already been readmitted"),
                      _ev("U027", "The whole goal is daily")]),
        champion_status=S.CaptureChampion(
            value="strong", champion_name="Aisha Karim", economic_buyer_identified="unclear",
            economic_buyer_name="", basis="inferred", model_confidence=0.65,
            evidence=[_ev("U061", "Send it to me and copy Raj"),
                      _ev("U077", "then we'll talk pricing with finance")]),
        top_risk=S.CaptureRisk(
            value="security_review", note="Vendor security committee meets Oct 9 and needs a written SSO design",
            basis="stated", model_confidence=0.9,
            evidence=[_ev("U056", "nothing moves until the vendor security review clears")]),
        next_step=S.CaptureNextStep(
            value="", date="", basis="none", model_confidence=0.0,
            evidence=[]))


SAMPLES = {"deal_a": deal_a, "deal_b": deal_b}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for deal_id, build in SAMPLES.items():
        payload = {"deal_id": deal_id, "source": "sample", "sample_label": SAMPLE_LABEL,
                   "record": build().model_dump(mode="json")}
        path = OUT / f"capture_{deal_id}.json"
        path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
