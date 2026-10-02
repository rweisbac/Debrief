import asyncio
import csv
import json

import pytest

from evals import judges, make_candidates, run_evals, scoring
from src.chain import Chain, load_context
from src.llm import LLMClient
from src.transcript import load_transcript
from tests.fakes import FakeBackend, scripted_clean_run


@pytest.fixture(scope="module")
def result_a(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ev")
    llm = LLMClient(mode="live", backend=scripted_clean_run(FakeBackend()), db_path=tmp / "t.sqlite3",
                    replay_dir=tmp / "rp", redact=lambda s: s)
    return asyncio.run(Chain(llm).run(load_context("deal_a"))).to_dict()


def gold(deal):
    return run_evals.gold(deal)


def test_extraction_counts(result_a):
    s = scoring.extraction_scores(gold("deal_a"), result_a["extraction"])
    # The hand-built fake extraction has 1 of 2 gold objections, 1 of 6 commitments, 2 of 4 stakeholders.
    assert s["objections"]["recall"] == (1, 2)
    assert s["commitments"]["recall"] == (1, 6)
    assert s["stakeholders"]["recall"] == (2, 4)
    assert s["stakeholders"]["precision"] == (2, 2)


def test_trap_scoring_deal_a(result_a):
    traps = {t["id"]: scoring.score_trap(t, result_a) for t in gold("deal_a")["traps"]}
    assert traps["T4"]["passed"] and traps["T4"]["sub"]["correction_extracted"]
    assert traps["T5"]["passed"]


def test_superseded_phrase_fails_trap(result_a):
    bad = json.loads(json.dumps(result_a))
    bad["artifacts"]["recap_email"]["current"]["body"] += " The connector syncs hourly."
    t4 = next(t for t in gold("deal_a")["traps"] if t["id"] == "T4")
    assert not scoring.score_trap(t4, bad)["passed"]


def test_overread_signal_fails_t3():
    t3 = next(t for t in gold("deal_c")["traps"] if t["id"] == "T3")
    fake = {"extraction": {"buying_signals": [{"strength": "strong", "evidence": [{"utterance_id": "U064", "excerpt": "x"}]}]},
            "artifacts": {"assessment": {"current": {"deal_state": "ready_to_advance", "next_steps": []}}}}
    r = scoring.score_trap(t3, fake)
    assert not r["passed"] and not r["sub"]["state_ok"] and not r["sub"]["not_strong_signal"]


def test_chase_fails_t6():
    t6 = next(t for t in gold("deal_b")["traps"] if t["id"] == "T6")
    fake = {"extraction": {}, "artifacts": {"assessment": {"current": {"deal_state": "open_technical_gap", "next_steps": [
        {"action": "Check in with Aisha next week", "action_type": "other", "why": "", "evidence": []}]}}}}
    assert not scoring.score_trap(t6, fake)["passed"]


def test_state_and_steps(result_a):
    assert scoring.score_state(gold("deal_a"), result_a)["passed"]
    assert scoring.score_steps(result_a)["passed"]


def test_adversarial_x_scoring():
    fake = {"extraction": {"business_outcome": {"stated": True}, "buying_signals": [], "competitor_mentions": []},
            "checks": [], "artifacts": {"assessment": {"current": {"deal_state": "low_information", "next_steps": []}}}}
    r = scoring.score_adversarial(gold("deal_x"), fake)
    assert not r["passed"] and not r["sub"]["no_invented_outcome"]


def test_report_lists_failures_and_not_run(result_a):
    scored = asyncio.run(_score(result_a))
    md = run_evals.write_report({"deal_a": [scored], "deal_b": [{"deal": "deal_b", "status": "not_run",
                                                                  "reason": "replay fixture missing"}]},
                                "replay", 1, with_judge=False)
    assert "## Not run" in md and "deal_b" in md
    assert "missed commitment" in md  # the fake extraction misses 5 gold commitments; they must be listed
    assert "1 of 6" in md


async def _score(r):
    g = gold("deal_a")
    return {"deal": "deal_a", "status": "ran", "debrief_id": r["debrief_id"], "errors": r["errors"],
            "state": scoring.score_state(g, r), "extraction": scoring.extraction_scores(g, r["extraction"]),
            "traps": [scoring.score_trap(t, r) for t in g["traps"]], "adversarial": None,
            "grounding": scoring.score_grounding(r), "overclaim": scoring.score_overclaim(r),
            "steps": scoring.score_steps(r), "needs_review": [], "overrides": [], "cost_usd": r["cost_usd"],
            "latency_ms": r["latency_ms"], "cache_read_tokens": 0, "cache_write_tokens": 0, "n_calls": 6,
            "steps_output": {}, "judge": []}


def test_candidates_file_shape_and_grounding():
    rows = list(csv.DictReader(make_candidates.OUT.open(encoding="utf-8")))
    assert len(rows) == 30
    assert sum(r["split"] == "dev" for r in rows) == 10 and sum(r["split"] == "test" for r in rows) == 20
    assert len({r["id"] for r in rows}) == 30
    for r in rows:
        ok, reason = load_transcript(r["deal_id"]).resolve_evidence(r["evidence_utterance_id"], r["evidence_excerpt"])
        assert ok, (r["id"], reason)


def test_judge_rates_and_uncalibrated_by_default():
    assert judges.rates([(True, True), (True, False), (False, False), (False, True)])["tpr"] == "1 of 2"
    assert judges.status()["calibrated"] is False


def test_judge_prompt_has_no_candidate_text():
    text, _ = __import__("src.prompts", fromlist=["load"]).load("judge")
    for r in csv.DictReader(make_candidates.OUT.open(encoding="utf-8")):
        assert r["action"] not in text
