import asyncio

import pytest

from src.chain import Chain, load_context
from src.llm import LLMClient
from tests.fakes import (FakeBackend, failing_report, raw_body, recap_a, scripted_clean_run, clean_report)


@pytest.fixture
def make_chain(tmp_path):
    def make(fb):
        llm = LLMClient(mode="live", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                        redact=lambda s: s)
        return Chain(llm)
    return make


def run(chain):
    return asyncio.run(chain.run(load_context("deal_a")))


def test_clean_path_is_six_calls(make_chain):
    fb = scripted_clean_run(FakeBackend())
    result = run(make_chain(fb))
    assert len(fb.requests) == 6
    assert [c["step"] for c in result.calls][:2] == ["extract", "assess_and_recommend"]
    assert not any(a.needs_review for a in result.artifacts.values())
    assert result.errors == []
    assert result.cost_usd > 0
    assert len(result.assessment.next_steps) == 2


def test_cached_prefix_identical_across_steps(make_chain):
    fb = scripted_clean_run(FakeBackend())
    run(make_chain(fb))
    systems = {str(req["system"]) for _, req in fb.requests}
    firsts = {req["messages"][0]["content"][0]["text"] for _, req in fb.requests}
    assert len(systems) == 1 and len(firsts) == 1


def test_high_failure_regenerates_once_and_keeps_original(make_chain):
    fb = scripted_clean_run(FakeBackend())
    fb.queues["VerifierReport"].clear()
    better = recap_a(body="Hi Dana,\n\nThanks for today. Priya will build the partner policy by October 6. "
                          "See you Thursday October 8 with Elena.\n\nSam")
    fb.queue("VerifierReport", raw_body(failing_report("recap_email")), raw_body(clean_report()))
    fb.queue("RecapEmail", raw_body(better))
    result = run(make_chain(fb))
    recap = result.artifacts["recap_email"]
    assert recap.regenerated and not recap.needs_review
    assert recap.original != recap.current
    assert fb.count("RecapEmail") == 2 and fb.count("VerifierReport") == 2
    retry_blocks = fb.requests[[n for n, _ in fb.requests].index("RecapEmail", 3)][1]["messages"][0]["content"]
    assert "reviewer_findings_to_fix" in retry_blocks[-1]["text"]


def test_still_failing_marks_needs_review(make_chain):
    fb = scripted_clean_run(FakeBackend())
    fb.queues["VerifierReport"].clear()
    fb.queue("VerifierReport", raw_body(failing_report("recap_email")), raw_body(failing_report("recap_email")))
    fb.queue("RecapEmail", raw_body(recap_a()))
    result = run(make_chain(fb))
    recap = result.artifacts["recap_email"]
    assert recap.needs_review and recap.flagged and recap.original is not None


def test_refused_draft_needs_review_without_retry(make_chain):
    fb = scripted_clean_run(FakeBackend())
    fb.queues["RecapEmail"].clear()
    fb.queue("RecapEmail", raw_body(None, stop="refusal", stop_details={"type": "refusal", "category": None}))
    result = run(make_chain(fb))
    recap = result.artifacts["recap_email"]
    assert recap.refused and recap.needs_review and fb.count("RecapEmail") == 1


def test_result_serializes(make_chain):
    import json
    result = run(make_chain(scripted_clean_run(FakeBackend())))
    json.dumps(result.to_dict())
