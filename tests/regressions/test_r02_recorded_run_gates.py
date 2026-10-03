"""R-02 (DECISIONS D-15): gaps found in the first recorded run.

- deal_b: R-WAIT forced waiting_on_customer while Apex still owed the SSO design.
- deal_c: the verifier rated an uncommitted promise in the recap medium, so the recap stayed one-tap approvable.
- deal_c: the rewritten internal summary kept a date nobody said, and the date check was only medium.
"""
from datetime import date

from src import checks, rules
from src.chain import Chain
from src.schemas import CustomerDependency, VerifierReport, VerifierVerdict
from src.transcript import load_transcript
from tests.fakes import assessment_a, ev, extraction_a, recap_a, summary_a

T_A = load_transcript("deal_a")
AS_OF = date(2026, 9, 30)


def test_wait_not_forced_when_apex_owes_open_item():
    x = extraction_a()
    assert any(i.owner == "Priya Raman" for i in x.open_technical_items)
    x.customer_dependencies = [CustomerDependency(summary="Procurement sends the questionnaire", owner="Raj", due="",
                                                  blocks_progress=True, evidence=[ev("U054", "I can send that")])]
    a, ov = rules.apply(assessment_a(), x, T_A)
    assert a.deal_state.value == "ready_to_advance"
    assert "R-WAIT" not in [o.rule_id for o in ov]


def _verdict(check: str, artifact: str, severity: str) -> VerifierVerdict:
    return VerifierVerdict(check=check, artifact=artifact, target="We will come back with a plan", passed=False,
                           severity=severity, finding="Nobody committed to a plan.", utterance_ids=["U079"])


def test_medium_uncommitted_promise_in_recap_blocks():
    report = VerifierReport(verdicts=[_verdict("email_promises_uncommitted", "recap_email", "medium")])
    assert "recap_email" in Chain._high_failures([], report)


def test_medium_finding_elsewhere_still_does_not_block():
    report = VerifierReport(verdicts=[_verdict("commitment_overstated", "internal_summary", "medium"),
                                      _verdict("commitment_overstated", "recap_email", "low")])
    assert Chain._high_failures([], report) == {}


def test_unsaid_date_in_summary_is_high():
    s = summary_a()
    s.commitments = ["Priya Raman: partner policy by 2026-10-07"]
    c = checks.check_dates("internal_summary", s, AS_OF, strictly_after=False, transcript=T_A)
    assert not c.passed and c.severity == "high" and "not a date said in the call" in c.detail


def test_said_date_in_recap_passes():
    c = checks.check_dates("recap_email", recap_a(), AS_OF, strictly_after=False, transcript=T_A)
    assert c.passed


def _check(artifact: str, passed: bool, after: bool = False) -> dict:
    c = {"check": "numbers_in_source", "artifact": artifact, "passed": passed, "severity": "high",
         "detail": "numbers not grounded: twelve nine", "locations": []}
    return dict(c, after_regeneration=True) if after else c


def test_final_grounding_uses_rewrite_and_counts_blocked():
    from evals import scoring
    arts = {"internal_summary": {"needs_review": False}, "recap_email": {"needs_review": True}}
    fixed = {"checks": [_check("internal_summary", False), _check("internal_summary", True, after=True)],
             "artifacts": arts}
    assert scoring.score_grounding_final(fixed)["status"] == "pass"
    blocked = {"checks": [_check("recap_email", False)], "artifacts": arts}
    assert scoring.score_grounding_final(blocked)["status"] == "blocked"
    shipped = {"checks": [_check("internal_summary", False)], "artifacts": arts}
    assert scoring.score_grounding_final(shipped)["status"] == "fail"
