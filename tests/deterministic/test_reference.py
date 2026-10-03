"""Research reference answers and the keyword coverage scorer."""
import pytest

from evals import reference as ref

DEALS = ref.deals()


def test_five_scenarios_with_three_must_haves():
    assert DEALS == ["deal_a", "deal_b", "deal_c", "deal_x", "deal_y"]
    for d in DEALS:
        assert sum(s["kind"] == "must_have" for s in ref.reference(d)["steps"]) == 3


@pytest.mark.parametrize("deal", DEALS)
def test_each_reference_step_matches_its_own_terms(deal):
    """Good steps match their own text. Wrong steps are written as descriptions, so they carry a concrete example
    of how a tool step might phrase the mistake, and must match that."""
    for s in ref.reference(deal)["steps"]:
        target = s["example"] if s["kind"] == "wrong" else s["text"]
        assert ref.matches(target, s["match"]), s["id"]


@pytest.mark.parametrize("deal", DEALS)
def test_good_reference_steps_never_trip_a_wrong_pattern(deal):
    steps = ref.reference(deal)["steps"]
    wrong = [s for s in steps if s["kind"] == "wrong"]
    for s in steps:
        if s["kind"] in {"must_have", "optional"}:
            assert not any(ref.matches(s["text"], w["match"]) for w in wrong), (s["id"], s["text"])


@pytest.mark.parametrize("deal", DEALS)
def test_rules_exist_in_playbook_v2(deal):
    import re
    from src.config import ROOT
    ids = set(re.findall(r"^## (PB-\d{2}):", (ROOT / "data" / "playbook_v2.md").read_text(), flags=re.M))
    assert ids == {f"PB-{i:02d}" for i in range(1, 17)}
    for s in ref.reference(deal)["steps"]:
        assert set(s["rules"]) <= ids, s["id"]


def test_score_labels_steps():
    a = {"deal_state": "ready_to_advance", "next_steps": [
        {"action": "Priya sends the partner hierarchy policy by Oct 6", "why": ""},
        {"action": "Send the recap", "why": ""},
        {"action": "Tell Elena the go-live date is March", "why": ""}]}
    out = ref.score("deal_a", a)
    assert out["must_have_covered"] == ["A-R01"]
    assert [p["label"] for p in out["steps"]] == ["must_have", "routine", "wrong"]
    assert out["wrong_steps"] == [3] and out["routine_only"] == [2]
