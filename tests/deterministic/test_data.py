import json
import re

import pytest

from src.config import ROOT
from src.transcript import load_transcript, normalize

DATA = ROOT / "data"
CORE = ["deal_a", "deal_b", "deal_c"]
ALL = CORE + ["deal_x", "deal_y"]
CRM_KEYS = {"account", "acv_usd", "stage", "close_date", "contacts", "champion", "discovery_notes",
            "prior_call_notes", "competitors", "pod", "tv_entered_at", "demo", "close_the_demo"}


def gold(deal):
    return json.loads((DATA / "gold" / f"{deal}.json").read_text())


def crm(deal):
    return json.loads((DATA / "crm" / f"{deal}.json").read_text())


@pytest.mark.parametrize("deal", CORE)
def test_core_transcripts_size_and_cast(deal):
    t = load_transcript(deal)
    assert 1500 <= t.word_count <= 2500
    customers = [p for p in t.participants if p.side == "customer"]
    apex_titles = {p.title for p in t.participants if p.side == "apex"}
    assert 2 <= len(customers) <= 4
    assert {"Account Executive", "Solutions Consultant"} <= apex_titles


def test_adversarial_sizes():
    assert load_transcript("deal_x").word_count <= 500
    assert 800 <= load_transcript("deal_y").word_count <= 2000


@pytest.mark.parametrize("deal", ALL)
def test_crm_shape(deal):
    c = crm(deal)
    assert CRM_KEYS <= set(c)
    assert 100_000 <= c["acv_usd"] <= 500_000
    assert set(c["close_the_demo"]) >= {"dated_next_step", "stakeholder_to_add", "business_outcome", "sc_commitment"}


def _anchors(obj):
    if isinstance(obj, dict):
        if "utterance_id" in obj and "anchor" in obj:
            yield obj
        for v in obj.values():
            yield from _anchors(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _anchors(v)


@pytest.mark.parametrize("deal", ALL)
def test_gold_anchors_resolve(deal):
    t = load_transcript(deal)
    refs = list(_anchors(gold(deal)))
    assert refs
    for ref in refs:
        u = t.get(ref["utterance_id"])
        assert u is not None, ref
        assert normalize(ref["anchor"]) in normalize(u.text), ref


def test_each_trap_labeled_once():
    ids = [t["id"] for d in ALL for t in gold(d)["traps"]]
    assert sorted(ids) == ["T1", "T2", "T3", "T4", "T5", "T6"]


def test_adversarial_labels_present():
    assert gold("deal_x")["expected_deal_state"] == "low_information"
    assert gold("deal_y")["contradictions"]


@pytest.mark.parametrize("deal", ALL)
def test_gold_expected_state_is_valid(deal):
    from src.schemas import DealStateEnum
    g = gold(deal)
    valid = {s.value for s in DealStateEnum}
    assert g["expected_deal_state"] in valid
    assert set(g["accepted_deal_states"]) <= valid and g["expected_deal_state"] in g["accepted_deal_states"]


def test_playbook_ids_unique_and_complete():
    ids = re.findall(r"^## (PB-\d{2}):", (DATA / "playbook.md").read_text(), flags=re.M)
    assert ids == [f"PB-{i:02d}" for i in range(1, 11)]


def test_release_card_ids_unique():
    cards = json.loads((DATA / "release_cards.json").read_text())["cards"]
    ids = [c["id"] for c in cards]
    assert len(ids) == len(set(ids)) and "RC-12" in ids


def test_gold_release_cards_exist():
    ids = {c["id"] for c in json.loads((DATA / "release_cards.json").read_text())["cards"]}
    for d in ALL:
        assert set(gold(d)["relevant_release_cards"]) <= ids


def test_synthetic_label_present():
    assert "fictional" in (DATA / "playbook.md").read_text().lower()
    for d in ALL:
        assert "Synthetic data, fictional company" in crm(d)["_note"]
