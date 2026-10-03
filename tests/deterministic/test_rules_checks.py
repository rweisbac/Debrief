from datetime import date

from src import checks, meddpicc, rules
from src.schemas import CustomerDependency, MapRow, MutualActionPlan
from src.transcript import load_transcript
from tests.fakes import assessment_a, ev, extraction_a, map_a, recap_a, step

T_A = load_transcript("deal_a")
T_X = load_transcript("deal_x")
CRM_A = __import__("src.adapters", fromlist=["FileCRMSource"]).FileCRMSource().deal("deal_a")
AS_OF = date(2026, 9, 30)


def ids(overrides):
    return [o.rule_id for o in overrides]


def test_clean_assessment_untouched():
    a, ov = rules.apply(assessment_a(), extraction_a(), T_A)
    assert ov == [] and len(a.next_steps) == 2


def test_unknown_rule_dropped_and_card_blanked():
    steps = [step("Do a thing", "Sam Lee", "", "PB-99", "other", "U054", "I can send that"),
             step("Send policy", "Priya Raman", "", "PB-04", "route_to_sc", "U054", "back to you by Tuesday",
                  card="RC-99")]
    a, ov = rules.apply(assessment_a(steps), extraction_a(), T_A)
    assert len(a.next_steps) == 1 and a.next_steps[0].release_card_id == ""
    assert ids(ov).count("R-RULEID") == 2


def test_step_without_valid_evidence_dropped():
    steps = [step("Invented", "Sam Lee", "", "PB-01", "other", "U054", "we will sign next week")]
    a, ov = rules.apply(assessment_a(steps), extraction_a(), T_A)
    assert a.next_steps == [] and "R-NOEVID" in ids(ov)


def test_low_information_forced_and_capped():
    steps = [step(f"Step {i}", "Nate Kowalski", "", "PB-01", "other", "U030", "I'll reach out to him") for i in range(3)]
    a, ov = rules.apply(assessment_a(steps), extraction_a(), T_X)
    assert a.deal_state.value == "low_information" and len(a.next_steps) == 2
    assert ids(ov).count("R-LOWINFO") == 2


def test_waiting_forced_and_chase_dropped():
    x = extraction_a()
    x.open_technical_items = []  # Apex owes nothing, so the blocker forces waiting (D-15)
    x.customer_dependencies = [CustomerDependency(summary="Security review must finish", owner="Raj", due="",
                                                  blocks_progress=True, evidence=[ev("U054", "I can send that")])]
    steps = [step("Check in with Dana on the review", "Sam Lee", "", "PB-09", "other", "U054", "back to you by Tuesday"),
             step("Book a meeting", "Sam Lee", "", "PB-02", "book_meeting", "U054", "back to you by Tuesday"),
             step("Send the security packet", "Sam Lee", "", "PB-09", "support_customer_process", "U054",
                  "back to you by Tuesday")]
    a, ov = rules.apply(assessment_a(steps), x, T_A)
    assert a.deal_state.value == "waiting_on_customer"
    assert [s.action for s in a.next_steps] == ["Send the security packet"]
    assert ids(ov) == ["R-WAIT", "R-CHASE", "R-CHASE"]


def test_dated_dependency_does_not_force_waiting():
    x = extraction_a()
    x.customer_dependencies = [CustomerDependency(summary="Committee", owner="Raj", due="2026-10-09",
                                                  blocks_progress=True, evidence=[ev("U054", "I can send that")])]
    a, ov = rules.apply(assessment_a(), x, T_A)
    assert a.deal_state.value == "ready_to_advance" and "R-WAIT" not in ids(ov)


def test_cap_at_three():
    steps = [step(f"Step {i}", "Sam Lee", "", "PB-01", "other", "U054", "back to you by Tuesday") for i in range(5)]
    a, ov = rules.apply(assessment_a(steps), extraction_a(), T_A)
    assert len(a.next_steps) == 3 and "R-CAP" in ids(ov)


def test_map_agreed_without_evidence_downgraded():
    m = MutualActionPlan(customer_value_line="x", rows=[MapRow(milestone="Legal", customer_owner="", apex_owner="",
                                                               target_date="", status="agreed", evidence=[])])
    p, ov = rules.enforce_map_agreed(m, T_A)
    assert p.rows[0].status.value == "proposed" and ids(ov) == ["R-MAP"]


# Deterministic checks

def failed(results):
    return {r.check for r in results if not r.passed}


def test_clean_artifacts_pass():
    res = checks.run_all(extraction=extraction_a(), assessment=assessment_a(), recap=recap_a(), summary=None,
                         plan=map_a(), transcript=T_A, crm=CRM_A, as_of=AS_OF)
    assert failed(res) == set(), [r for r in res if not r.passed]


def test_changed_number_caught():
    bad = recap_a(body="Hi Dana, you ingest 5 billion events a month and peak at 38,000 per second. Sam")
    assert "numbers_in_source" in failed(checks.run_artifact("recap_email", bad, T_A, CRM_A, AS_OF))


def test_k_suffix_number_matches_crm_or_transcript():
    ok = recap_a(body="Hi Dana, peaks of 38,000 per second, about 38K. Sam")
    assert "numbers_in_source" not in failed(checks.run_artifact("recap_email", ok, T_A, CRM_A, AS_OF))


def test_weekend_and_past_dates_caught():
    bad = recap_a(body="Hi Dana, let's meet October 10 or September 28. Sam")
    r = [c for c in checks.run_artifact("recap_email", bad, T_A, CRM_A, AS_OF) if c.check == "dates_future_business_days"][0]
    assert not r.passed and any("weekend" in x for x in r.locations) and any("not after" in x for x in r.locations)


def test_invented_person_caught():
    bad = recap_a(body="Hi Dana, I spoke with Gregory Thornton about it. Sam")
    r = [c for c in checks.run_artifact("recap_email", bad, T_A, CRM_A, AS_OF) if c.check == "names_known"][0]
    assert not r.passed and {"Gregory", "Thornton"} <= set(r.locations)


def test_bad_evidence_caught():
    a = assessment_a([step("x", "Sam Lee", "", "PB-01", "other", "U013", "5 billion events a month")])
    assert "evidence_resolves" in failed(checks.run_artifact("assessment", a, T_A, CRM_A, AS_OF))


def test_step_due_today_fails_strictly_after():
    a = assessment_a([step("x", "Sam Lee", "2026-09-30", "PB-01", "other", "U054", "back to you by Tuesday")])
    assert "dates_future_business_days" in failed(checks.run_artifact("assessment", a, T_A, CRM_A, AS_OF))


def test_four_steps_and_chase_caught():
    s = [step("Check in on the review", "Sam Lee", "", "PB-09", "other", "U054", "back to you by Tuesday")] * 4
    res = checks.run_artifact("assessment", assessment_a(s, state="waiting_on_customer"), T_A, CRM_A, AS_OF)
    assert {"max_three_steps", "no_chase_when_waiting"} <= failed(res)


# MEDDPICC

def test_meddpicc_deal_a():
    v = meddpicc.compute(extraction_a(), CRM_A)
    assert v.economic_buyer.status.value == "known" and "Elena" in v.economic_buyer.summary
    assert v.champion.status.value == "known"
    assert v.metrics.status.value == "known"
    assert v.competition.status.value == "unknown" and v.competition.summary == "Unknown after TV demo"
    assert "competition" in meddpicc.gaps(v)


def test_meddpicc_partial_eb_when_only_in_call():
    crm = dict(CRM_A, economic_buyer="")
    v = meddpicc.compute(extraction_a(), crm)
    assert v.economic_buyer.status.value == "partial"


def test_quoted_text_must_be_in_transcript():
    ok = recap_a(body='Hi Dana, as you said, "dispatch can swap drivers or call the consignee". Sam')
    bad = recap_a(body='Hi Dana, as you said, "we will sign the contract this quarter". Sam')
    assert "quotes_in_transcript" not in failed(checks.run_artifact("recap_email", ok, T_A, CRM_A, AS_OF))
    assert "quotes_in_transcript" in failed(checks.run_artifact("recap_email", bad, T_A, CRM_A, AS_OF))
