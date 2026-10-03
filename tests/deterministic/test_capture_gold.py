"""Capture ground truth: 12 deals in 4 buckets, labels consistent with the transcripts, scorer and simulated AE."""
import pytest

from evals import capture_scoring as cs
from src import capture
from src.chain import load_context
from src.checks import call_dates
from src.schemas import ChampionStatusEnum, TopRiskEnum, YesNoUnclearEnum
from scripts.build_capture_samples import SAMPLES

DEALS = cs.deals()


def test_twelve_deals_three_per_bucket():
    assert len(DEALS) == 12
    buckets = [cs.gold(d)["bucket"] for d in DEALS]
    for b in ("clear_next_step", "non_committal", "hidden_blocker", "ambiguous"):
        assert buckets.count(b) == 3, b


@pytest.mark.parametrize("deal", DEALS)
def test_gold_is_consistent_with_the_call(deal):
    g, ctx = cs.gold(deal), load_context(deal)
    text = ctx.transcript.full_text().lower()
    assert set(g["champion_status"]["accepted"]) <= {e.value for e in ChampionStatusEnum}
    assert set(g["champion_status"]["economic_buyer_identified"]) <= {e.value for e in YesNoUnclearEnum}
    assert set(g["top_risk"]["accepted"]) <= {e.value for e in TopRiskEnum}
    for group in g["priority_why_now"]["must_mention"] + g["next_step"]["must_mention"]:
        assert any(alt.lower() in text for alt in group), (deal, group)  # the label rests on words in the call
    if g["next_step"]["exists"]:
        from datetime import date
        assert date.fromisoformat(g["next_step"]["date"]) in call_dates(ctx.transcript, ctx.as_of)
    # the AE's correction must itself pass the scorer
    for f in capture.FIELDS:
        assert cs.field_correct(f, g[f], {**g[f]["ae_value"]}), (deal, f)


@pytest.mark.parametrize("deal", list(SAMPLES))
def test_hand_written_samples_match_gold(deal):
    ctx = load_context(deal)
    scored = capture.score(SAMPLES[deal](), ctx.transcript, ctx.crm, ctx.as_of)
    g = cs.gold(deal)
    assert all(cs.field_correct(f, g[f], scored[f]["values"]) for f in capture.FIELDS)


def test_scorer_catches_wrong_values():
    g = cs.gold("deal_a")
    assert not cs.field_correct("next_step", g["next_step"], {"value": "Session with Elena", "date": "2026-10-09"})
    assert not cs.field_correct("top_risk", g["top_risk"], {"value": "budget"})
    gx = cs.gold("deal_x")
    assert cs.field_correct("priority_why_now", gx["priority_why_now"], {"value": "Not stated in the call"})
    assert not cs.field_correct("priority_why_now", gx["priority_why_now"], {"value": "Faster claims loads"})


def test_simulated_ae_corrects_only_wrong_fields():
    ctx = load_context("deal_a")
    rec = SAMPLES["deal_a"]()
    rec.top_risk.value = TopRiskEnum.budget
    scored = capture.score(rec, ctx.transcript, ctx.crm, ctx.as_of)
    routing = capture.route(scored, ae_confirms_so_far=0, spot_rate=0)
    edits, seconds, wrong = cs.simulate_ae(cs.gold("deal_a"), scored, routing)
    assert wrong == ["top_risk"] and edits["top_risk"]["value"] == "timeline"
    assert seconds == cs.SIM_BASE + cs.SIM_PER_QUESTION * 2 + cs.SIM_PER_CORRECTION
