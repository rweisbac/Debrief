import pytest

from src.adapters import FileCRMSource, FileGongSource, FileNotifier


def test_crm_and_gong_round_trip():
    crm, gong = FileCRMSource(), FileGongSource()
    assert crm.list_deals()[:3] == ["deal_a", "deal_b", "deal_c"] and len(crm.list_deals()) == 12
    deal = crm.deal("deal_a")
    assert deal["account"] == "Halvorsen Freight"
    assert gong.transcript("deal_a").utterances[0].id == "U001"
    assert gong.activity("deal_a")["call_id"] == deal["demo"]["call_id"]


def test_notifier_writes_internal_only(tmp_path):
    n = FileNotifier(tmp_path / "outbox.jsonl")
    n.send("Sam Lee", "ae", "deal_a", "nudge", {"text": "hi"})
    assert n.read_all()[0]["recipient"] == "Sam Lee"
    with pytest.raises(ValueError):
        n.send("dana.ortiz@halvorsen.example", "customer", "deal_a", "recap", {})
