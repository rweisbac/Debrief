"""Post-demo capture: confidence from checkable signals, routing, storage and metrics. No network."""
import asyncio
from datetime import date

import pytest

from src import capture
from src.adapters import FileCRMSource
from src.llm import LLMClient
from src.transcript import load_transcript
from src.schemas import BasisEnum
from tests.fakes import FakeBackend, capture_a, ev, extraction_a, raw_body

T_A = load_transcript("deal_a")
CRM_A = FileCRMSource().deal("deal_a")
AS_OF = date(2026, 9, 30)


def scored(record=None):
    return capture.score(record or capture_a(), T_A, CRM_A, AS_OF)


def test_clean_capture_keeps_model_confidence():
    s = scored()
    assert s["next_step"]["confidence"] == 0.96
    assert s["next_step"]["signals"] == ["Said in the call, with a matching line"]
    assert s["next_step"]["quotes"][0]["utterance_id"] == "U072"
    assert s["next_step"]["quotes"][0]["speaker"] == "Sam Lee"  # quote text comes from the transcript


def test_no_basis_is_zero():
    r = capture_a()
    r.next_step.basis, r.next_step.value, r.next_step.date, r.next_step.evidence = BasisEnum.none, "", "", []
    assert scored(r)["next_step"]["confidence"] == 0.0


def test_inferred_is_capped():
    r = capture_a()
    r.priority_why_now.basis = BasisEnum.inferred
    s = scored(r)["priority_why_now"]
    assert s["confidence"] == capture.CAP_INFERRED and "Inferred, not said in the call" in s["signals"]


def test_unmatched_evidence_is_capped():
    r = capture_a()
    r.top_risk.evidence = [ev("U076", "She loved the last platform project")]
    assert scored(r)["top_risk"]["confidence"] == capture.CAP_NO_EVIDENCE


def test_unsaid_date_never_auto_confirms():
    r = capture_a()
    r.next_step.date = "2026-10-09"
    s = scored(r)["next_step"]
    assert s["confidence"] == capture.CAP_DATE_NOT_SAID and not s["auto_eligible"]
    routing = capture.route({**scored(), "next_step": s}, ae_confirms_so_far=100, threshold=0.1, spot_rate=0)
    assert routing["next_step"]["mode"] == "ask"


def test_crm_disagreement_caps_champion():
    r = capture_a()
    r.champion_status.economic_buyer_name = "Grace Oyelaran"
    s = scored(r)["champion_status"]
    assert s["confidence"] == capture.CAP_CRM_DISAGREES and any("Elena Varga" in x for x in s["signals"])


def test_judgment_fields_always_asked_during_warmup():
    routing = capture.route(scored(), ae_confirms_so_far=3, threshold=0.5, warmup=20, spot_rate=0)
    assert routing["champion_status"]["mode"] == "ask" and routing["top_risk"]["mode"] == "ask"
    assert routing["next_step"]["mode"] == "auto"


def test_after_warmup_threshold_decides():
    routing = capture.route(scored(), ae_confirms_so_far=20, threshold=0.9, warmup=20, spot_rate=0)
    assert routing["champion_status"]["mode"] == "auto"  # 0.92
    assert routing["top_risk"]["mode"] == "ask"  # 0.8


def test_spot_check_is_deterministic_and_respects_rate():
    always = capture.route(scored(), ae_confirms_so_far=99, threshold=0.0, spot_rate=1.0, spot_key="k")
    never = capture.route(scored(), ae_confirms_so_far=99, threshold=0.0, spot_rate=0.0, spot_key="k")
    assert all(r["mode"] == "ask" for r in always.values())
    assert all(r["mode"] == "auto" for r in never.values())


def test_correction_compares_graded_parts_only():
    agent = {"value": "strong", "champion_name": "Dana Ortiz", "economic_buyer_identified": "yes",
             "economic_buyer_name": "Elena Varga"}
    assert not capture.corrected("champion_status", agent, {**agent, "champion_name": "Dana"})
    assert capture.corrected("champion_status", agent, {**agent, "value": "unclear"})
    assert not capture.corrected("next_step", {"value": "Session with Elena.", "date": "2026-10-08"},
                                 {"value": "session with elena", "date": "2026-10-08"})


def test_submit_stores_labels_and_metrics(tmp_path):
    db = tmp_path / "t.sqlite3"
    cap = capture.save_capture("deal_a", capture_a(), scored(), "sample", db_path=db)
    assert capture.latest_capture("deal_a", db)["capture_id"] == cap["capture_id"]
    out = capture.submit(cap, "Sam Lee", {"top_risk": {"value": "competitor"}}, 21.5, db_path=db)
    assert out["corrected"] == ["top_risk"]
    assert capture.ae_confirms("Sam Lee", db_path=db) == 1
    m = capture.metrics(db_path=db)
    assert m["sessions"] == 1 and m["fields"] == 4
    assert m["per_field_accuracy"]["top_risk"]["accuracy"] == 0.0
    assert m["per_field_accuracy"]["next_step"]["accuracy"] == 1.0
    assert m["median_seconds_to_complete"] == 21.5
    assert capture.metrics(simulated=True, db_path=db)["sessions"] == 0  # simulated rows are kept apart


def test_threshold_simulator(tmp_path):
    db = tmp_path / "t.sqlite3"
    cap = capture.save_capture("deal_a", capture_a(), scored(), "sample", db_path=db)
    capture.submit(cap, "Sam Lee", {"top_risk": {"value": "competitor"}}, 30, db_path=db)
    low = capture.simulate_threshold(0.5, db_path=db)
    high = capture.simulate_threshold(0.95, db_path=db)
    assert low["auto_confirm_rate"] == 1.0 and low["error_rate_among_auto"] == 0.25
    assert high["auto_confirm_rate"] == 0.25 and high["error_rate_among_auto"] == 0.0


def test_run_capture_uses_parse_and_validates(tmp_path):
    from src.chain import load_context
    ctx = load_context("deal_a")
    bad = capture_a()
    bad.top_risk.evidence = [ev("U076", "words nobody said in this call at all")]
    fb = FakeBackend().queue("CaptureRecord", raw_body(bad), raw_body(capture_a()))
    llm = LLMClient(mode="live", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                    redact=lambda s: s)
    res = asyncio.run(capture.run_capture(llm, ctx.transcript, ctx.context_block(), extraction_a(), "d1"))
    assert res.attempts == 2 and res.parsed is not None and not res.validator_errors


@pytest.mark.parametrize("field", capture.FIELDS)
def test_every_field_has_label_and_graded_parts(field):
    assert capture.LABELS[field] and capture.GRADED[field]
