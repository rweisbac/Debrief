"""Best practice profile (DEBRIEF_BEST_PRACTICE) and the AE's confirmed fields in reruns."""
import asyncio
import json

from src import config, prompts
from src.chain import Chain, load_context
from src.llm import LLMClient
from tests.fakes import FakeBackend, capture_a, scripted_clean_run


def _profile(monkeypatch, on: bool):
    monkeypatch.setattr(config, "PLAYBOOK_FILE", config.ROOT / "data" / ("playbook_v2.md" if on else "playbook.md"))
    monkeypatch.setattr(config, "PROMPT_PINS", {} if on else {"assess_and_recommend": 2, "draft_recap_email": 2,
                                                              "judge": 1})
    prompts.stable_reference.cache_clear()


def test_profile_off_keeps_recorded_versions(monkeypatch):
    _profile(monkeypatch, False)
    assert prompts.load("assess_and_recommend")[1] == "v2"
    assert prompts.load("judge")[1] == "v1"
    assert "PB-16" not in prompts.playbook_rule_ids()
    prompts.stable_reference.cache_clear()


def test_profile_on_uses_research(monkeypatch):
    _profile(monkeypatch, True)
    assert prompts.load("assess_and_recommend")[1] == "v3"
    assert prompts.load("draft_recap_email")[1] == "v3"
    assert prompts.load("judge")[1] == "v2"
    assert {"PB-11", "PB-16"} <= prompts.playbook_rule_ids()
    assert "Baseline hygiene" in prompts.stable_reference()[0]
    prompts.stable_reference.cache_clear()


def test_judge_v2_overall_and_strong():
    from evals import judges
    from src.schemas import JudgeResultV2
    base = {c: True for c in judges.CRITERIA_V2}
    j = JudgeResultV2(**base, best_practice_rule="PB-09", critique="ok")
    assert judges.overall(j) and judges.strong(j)
    j = JudgeResultV2(**{**base, "r7_beyond_hygiene": False}, best_practice_rule="PB-01", critique="routine")
    assert judges.overall(j) and not judges.strong(j)
    j = JudgeResultV2(**{**base, "r6_respects_process": False}, best_practice_rule="none", critique="chase")
    assert not judges.overall(j)


def _requests(tmp_path, confirmed):
    fb = scripted_clean_run(FakeBackend())
    llm = LLMClient(mode="live", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                    redact=lambda s: s)
    asyncio.run(Chain(llm).run(load_context("deal_a"), confirmed=confirmed))
    return [json.dumps(r) for _, r in fb.requests]


def test_confirmed_fields_reach_assess_and_drafts_only_when_given(tmp_path):
    assert not any("ae_confirmed_capture" in r for r in _requests(tmp_path, None))
    from src import capture
    final = capture.field_values(capture_a())
    reqs = _requests(tmp_path, final)
    with_block = [r for r in reqs if "ae_confirmed_capture" in r]
    assert len(with_block) == 4  # assess plus the three drafts; never the extraction or the verifier
