"""R-01 (DECISIONS D-06): fuzzy evidence matching accepted a changed number."""
from src.transcript import load_transcript


def test_changed_number_rejected_on_real_utterance():
    t = load_transcript("deal_a")
    ok, reason = t.resolve_evidence("U013", "5 billion events a month")
    assert not ok and "number" in reason


def test_changed_peak_rejected():
    t = load_transcript("deal_a")
    ok, _ = t.resolve_evidence("U013", "peaks around 36,000 per second")
    assert not ok


def test_exact_numbers_still_pass():
    t = load_transcript("deal_a")
    assert t.resolve_evidence("U013", "4.7 billion events a month")[0]
    assert t.resolve_evidence("U013", "peaks around 38,000 per second")[0]
