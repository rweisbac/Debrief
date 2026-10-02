import json

import pytest
from pydantic import ValidationError

from src import schemas as S


def ev(uid="U001", excerpt="hello there"):
    return S.EvidenceRef(utterance_id=uid, excerpt=excerpt)


def step(**kw):
    base = dict(action="Send recap", owner="AE", due_by="2026-10-05", playbook_rule_id="PB-01",
                release_card_id="", action_type="send_recap", why="Short reason.", evidence=[ev()])
    base.update(kw)
    return S.NextStep(**base)


def assessment(n_steps=1, **kw):
    base = dict(deal_state="ready_to_advance", deal_state_why="Clear champion.",
                next_steps=[step() for _ in range(n_steps)], watch_items=[])
    base.update(kw)
    return S.Assessment(**base)


def test_every_field_required():
    with pytest.raises(ValidationError):
        S.EvidenceRef(utterance_id="U001")
    with pytest.raises(ValidationError):
        S.NextStep(action="x", owner="AE")


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        S.EvidenceRef(utterance_id="U001", excerpt="x", quote="made up")


@pytest.mark.parametrize("raw", ["Ready_To_Advance", "READY_TO_ADVANCE", " ready_to_advance "])
def test_enum_case_insensitive(raw):
    a = assessment(deal_state=raw)
    assert a.deal_state == S.DealStateEnum.ready_to_advance


def test_bad_enum_rejected():
    with pytest.raises(ValidationError):
        assessment(deal_state="hot_deal")


def _all_models():
    return [m for m in vars(S).values() if isinstance(m, type) and issubclass(m, S.BaseModel) and m not in (S.BaseModel, S._Model)]


def test_no_reasoning_field_anywhere():
    for m in _all_models():
        assert "reasoning" not in m.model_fields, m.__name__


@pytest.mark.parametrize("model", S.LLM_OUTPUT_MODELS)
def test_output_schemas_have_no_optional_or_union(model):
    schema = json.dumps(model.model_json_schema())
    assert "anyOf" not in schema and "oneOf" not in schema and '"null"' not in schema
    for name, f in model.model_fields.items():
        assert f.is_required(), f"{model.__name__}.{name} is optional"


def test_three_step_cap():
    assert S.validate_assessment(assessment(3)) == []
    errors = S.validate_assessment(assessment(4))
    assert any("max 3" in e for e in errors)


def test_fewer_than_three_is_fine():
    assert S.validate_assessment(assessment(0)) == []


def test_why_word_limit():
    long_why = " ".join(["word"] * 26)
    errors = S.validate_assessment(assessment(next_steps=[step(why=long_why)]))
    assert any("why has 26 words" in e for e in errors)


def test_step_needs_evidence_owner_rule():
    errors = S.validate_assessment(assessment(next_steps=[step(evidence=[], owner=" ", playbook_rule_id="")]))
    assert any("no evidence" in e for e in errors)
    assert any("no owner" in e for e in errors)
    assert any("no playbook_rule_id" in e for e in errors)


def test_excerpt_word_limit():
    long_excerpt = " ".join(["w"] * 31)
    errors = S.validate_assessment(assessment(next_steps=[step(evidence=[ev(excerpt=long_excerpt)])]))
    assert any("31 words" in e for e in errors)


@pytest.mark.parametrize("value,ok", [("", True), ("2026-10-08", True), ("2026-02-30", False), ("Oct 8", False), ("next week", False)])
def test_iso_date_or_empty(value, ok):
    assert S.is_iso_date_or_empty(value) is ok


def test_map_agreed_needs_evidence():
    row = S.MapRow(milestone="Security review", customer_owner="Raj", apex_owner="Marcus",
                   target_date="2026-10-09", status="Agreed", evidence=[])
    errors = S.validate_map(S.MutualActionPlan(customer_value_line="not stated", rows=[row]))
    assert any("agreed without evidence" in e for e in errors)
