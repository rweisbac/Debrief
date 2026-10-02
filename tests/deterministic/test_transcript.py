import pytest

from src.transcript import TranscriptError, load_transcript, normalize, parse_transcript

SAMPLE = """PARTICIPANTS
Sam Lee | Account Executive | apex
Dana Ortiz | VP Data | customer
---
[00:04] Sam Lee: Hello there.
[01:15] Dana Ortiz: We ingest about 4.7 billion events a month,
and peaks around 38,000 per second.
[02:00] Sam Lee: Got it.
"""


def test_ids_sides_and_continuation():
    t = parse_transcript(SAMPLE, "t")
    assert [u.id for u in t.utterances] == ["U001", "U002", "U003"]
    assert t.utterances[1].side == "customer"
    assert t.utterances[1].text.endswith("38,000 per second.")
    assert t.get("u002").speaker == "Dana Ortiz"
    assert t.get("U999") is None


def test_render_format_is_exact():
    t = parse_transcript(SAMPLE, "t")
    line = t.render_for_model().splitlines()[1]
    assert line.startswith("[U002 | 01:15 | Dana Ortiz, VP Data (customer)] We ingest")


def test_unknown_speaker_raises():
    bad = SAMPLE.replace("[02:00] Sam Lee", "[02:00] Someone Else")
    with pytest.raises(TranscriptError):
        parse_transcript(bad, "t")


def test_missing_separator_raises():
    with pytest.raises(TranscriptError):
        parse_transcript("PARTICIPANTS\nSam Lee | AE | apex\n[00:01] Sam Lee: hi", "t")


@pytest.mark.parametrize("excerpt", [
    "4.7 billion events a month",
    "  WE INGEST about 4.7   billion events ",
    "peaks around 38,000 per second",
])
def test_evidence_resolves(excerpt):
    t = parse_transcript(SAMPLE, "t")
    ok, reason = t.resolve_evidence("U002", excerpt)
    assert ok, reason


def test_evidence_near_miss_fuzzy_passes():
    t = parse_transcript(SAMPLE, "t")
    ok, reason = t.resolve_evidence("U002", "We ingest about 4.7 billion event a month")
    assert ok and reason.startswith("fuzzy")


@pytest.mark.parametrize("uid,excerpt", [
    ("U009", "4.7 billion events a month"),          # wrong id
    ("U002", "5 billion events a month"),            # changed number
    ("U002", "we will sign the contract next week"),  # invented
    ("U001", "4.7 billion events a month"),          # right text, wrong utterance
    ("U002", "   "),                                 # empty
])
def test_evidence_fails(uid, excerpt):
    t = parse_transcript(SAMPLE, "t")
    ok, _ = t.resolve_evidence(uid, excerpt)
    assert not ok


def test_render_quote_comes_from_table():
    t = parse_transcript(SAMPLE, "t")
    q = t.render_quote("U002")
    assert q["text"] == t.utterances[1].text and q["timestamp"] == "01:15"
    with pytest.raises(TranscriptError):
        t.render_quote("U404")


def test_normalize_handles_curly_quotes():
    assert normalize("“It’s fine.”") == "it's fine"


@pytest.mark.parametrize("deal", ["deal_a", "deal_b", "deal_c", "deal_x", "deal_y"])
def test_real_transcripts_parse_with_increasing_timestamps(deal):
    t = load_transcript(deal)
    secs = [int(m) * 60 + int(s) for m, s in (u.start_timestamp.split(":") for u in t.utterances)]
    assert secs == sorted(secs) and len(set(secs)) == len(secs)
