"""R-03 (DECISIONS D-17): the keyword reference matcher read a negated phrase as the mistake it negates.

"with no week estimates" matched the wrong step "estimate implementation in weeks", and "without writing a legal
opinion" matched "write a legal opinion". Both alternatives were removed; good steps must never trip a wrong pattern.
"""
from evals import reference as ref


def test_no_week_estimates_is_not_a_guessed_timeline():
    step = {"action": "Send Helen a short outline of the guided onboarding program, with no week estimates.", "why": ""}
    out = ref.score("deal_c", {"deal_state": "competitive_risk", "next_steps": [step]})
    assert out["steps"][0]["label"] != "wrong"


def test_without_legal_opinion_is_not_legal_advice():
    step = {"action": "Send IT and compliance the same neutral hosting brief, without writing a legal opinion.",
            "why": ""}
    out = ref.score("deal_y", {"deal_state": "waiting_on_customer", "next_steps": [step]})
    assert out["steps"][0]["label"] == "must_have"
