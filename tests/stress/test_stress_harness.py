"""Stress harness: plant known problems in otherwise clean outputs and see what the checks catch.

Every planted case asserts that the intended catcher (deterministic check, rule override,
schema validator or eval scorer) catches the problem. Every clean case asserts that nothing fires.
When the current code misses a planted problem or raises a false alarm, the test is marked
xfail(strict=True) with a "GAP:" reason, so the suite stays green and each gap flips to a failure
(XPASS) the day someone fixes it. See evals/stress_report.md for the summary.

All objects here are hand-built test fixtures. Excerpts are copied word for word from
data/transcripts. No model calls, no network.
"""
from __future__ import annotations

import asyncio
import copy

import pytest

from evals import run_evals, scoring
from src import checks, meddpicc, rules
from src import schemas as S
from src.chain import Chain, load_context
from src.llm import LLMClient
from tests.fakes import (FakeBackend, assessment_a, ev, extraction_a, map_a, raw_body, recap_a, step,
                         summary_a)

GAP = lambda why: pytest.mark.xfail(strict=True, reason="GAP: " + why)  # noqa: E731


# Helpers

def ctx(deal: str):
    return load_context(deal)


def failed_checks(name: str, obj, deal: str = "deal_a", crm: dict | None = None) -> set[str]:
    c = ctx(deal)
    return {r.check for r in checks.run_artifact(name, obj, c.transcript, crm or c.crm, c.as_of) if not r.passed}


def resolves(deal: str, uid: str, excerpt: str) -> bool:
    return ctx(deal).transcript.resolve_evidence(uid, excerpt)[0]


def gold(deal: str) -> dict:
    return run_evals.gold(deal)


def trap(deal: str, tid: str) -> dict:
    return next(t for t in gold(deal)["traps"] if t["id"] == tid)


def build_result(deal: str, extraction: S.ExtractionRecord, assessment: S.Assessment,
                 recap: S.RecapEmail | None = None, summary: S.InternalSummary | None = None,
                 plan: S.MutualActionPlan | None = None, verifier: list[dict] | None = None,
                 apply_rules: bool = True) -> dict:
    """Mirror what Chain.run produces offline: rules, MAP enforcement, deterministic checks.

    The model verifier does not run here, so verifier is empty unless a test supplies verdicts.
    """
    c = ctx(deal)
    overrides = []
    a = assessment
    if apply_rules:
        a, ov = rules.apply(assessment, extraction, c.transcript)
        overrides += [o.to_dict() for o in ov]
    if plan is not None:
        plan, ov = rules.enforce_map_agreed(plan, c.transcript)
        overrides += [o.to_dict() for o in ov]
    det = checks.run_all(extraction=extraction, assessment=a, recap=recap, summary=summary, plan=plan,
                         transcript=c.transcript, crm=c.crm, as_of=c.as_of)
    dump = lambda m: m.model_dump(mode="json") if m is not None else None  # noqa: E731
    arts = {"assessment": a, "recap_email": recap, "internal_summary": summary, "mutual_action_plan": plan}
    return {"extraction": dump(extraction), "meddpicc": dump(meddpicc.compute(extraction, c.crm)),
            "artifacts": {k: {"current": dump(v), "regenerated": False, "needs_review": False}
                          for k, v in arts.items()},
            "checks": [r.to_dict() for r in det], "verifier": verifier or [], "overrides": overrides}


def recap_a_with(old: str, new: str) -> S.RecapEmail:
    body = recap_a().body
    assert old in body, old
    return recap_a(body.replace(old, new))


# Clean objects for deal_b, deal_c, deal_x, deal_y. Excerpts are copied from the transcripts.

def extraction_b(**changes) -> S.ExtractionRecord:
    rec = S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=True, summary="Daily readmission list so care managers call the morning after discharge",
                                           evidence=[ev("U027", "The whole goal is daily")]),
        agreed_next_step=S.AgreedNextStep(exists=False, summary="", date="", evidence=[]),
        objections=[S.Objection(summary="Nested mhp_roles claim not supported natively", raised_by="Leo Brandt",
                                status="open", answer_given="Marcus to confirm native nested claims timing",
                                evidence=[ev("U012", "What I have not personally done is map a nested claim")])],
        open_technical_items=[S.OpenItem(summary="Native nested claim support date", owner="Marcus Bell",
                                         evidence=[ev("U023", "I'll take that to our identity team today")])],
        integration_patterns=[],
        commitments=[
            S.Commitment(who="Marcus Bell", side="apex", what="Send the encryption whitepaper", by_when="",
                         evidence=[ev("U051", "I'll send you our encryption whitepaper")]),
            S.Commitment(who="Marcus Bell", side="apex", what="Firm answer on native nested claims", by_when="",
                         evidence=[ev("U023", "I'll take that to our identity team today")])],
        stakeholders=[
            S.Stakeholder(name="Aisha Karim", title="Director", present=True, why_they_matter="runs the evaluation",
                          evidence=[ev("U061", "Send it to me and copy Raj")]),
            S.Stakeholder(name="Raj Patel", title="Security", present=False, why_they_matter="reviews the vendor",
                          evidence=[ev("U002", "Raj Patel from security couldn't make it")])],
        competitor_mentions=[], buying_signals=[], risk_signals=[],
        exact_numbers=[S.ExactNumber(value="About 140", what_it_measures="care managers",
                                     evidence=[ev("U037", "About 140 across the three regions")])],
        customer_dependencies=[S.CustomerDependency(
            summary="Vendor security review committee", owner="Raj Patel", due="2026-10-09", blocks_progress=True,
            evidence=[ev("U056", "nothing moves until the vendor security review clears")])],
        contradictions=[], corrections=[],
        checklist_mismatches=[S.ChecklistMismatch(field="sc_commitment", logged_value="",
                                                  transcript_says="Marcus will send the encryption whitepaper",
                                                  evidence=[ev("U051", "I'll send you our encryption whitepaper")])])
    return rec.model_copy(update=changes)


PACKET_STEP = ("Send Aisha the security review packet with Raj copied: questionnaire, SOC 2 report, encryption "
               "whitepaper and the written SSO design, before the October 9 committee")


def assessment_b(steps: list[S.NextStep] | None = None, state: str = "open_technical_gap") -> S.Assessment:
    if steps is None:
        steps = [
            step(PACKET_STEP, "Jordan Pike", "2026-10-07", "PB-09", "support_customer_process", "U058",
                 "Our vendor questionnaire, your SOC 2 report, the encryption details"),
            step("Marcus gets a dated answer on native nested claims from the identity team", "Marcus Bell",
                 "2026-10-05", "PB-04", "route_to_sc", "U023", "I'll take that to our identity team today"),
        ]
    return S.Assessment(deal_state=state, deal_state_why="Security review gates everything; SSO design is open.",
                        next_steps=steps, watch_items=[])


def recap_b(body: str | None = None) -> S.RecapEmail:
    body = body or (
        "Hi Aisha,\n\nThanks for the session. The readmission pipeline ran incrementally in nine minutes and each "
        "row shows its top three drivers. SSO is open: Marcus is taking native nested claims to our identity team "
        "and will come back with a date, not a roadmap slide. Marcus will send the encryption whitepaper. Before "
        "the October 9 committee we will send you the packet with Raj copied.\n\nJordan")
    return S.RecapEmail(subject="Recap: readmission pipeline, SSO and PHI", body=body,
                        customer_value_line="A daily list means care managers call while patients still remember them.",
                        evidence=[ev("U051", "I'll send you our encryption whitepaper")])


def map_b(with_whitepaper: bool = True) -> S.MutualActionPlan:
    rows = [S.MapRow(milestone="Security review packet to Aisha, Raj copied", customer_owner="Aisha Karim",
                     apex_owner="Jordan Pike", target_date="2026-10-07", status="proposed", evidence=[])]
    if with_whitepaper:
        rows.append(S.MapRow(milestone="Encryption whitepaper", customer_owner="", apex_owner="Marcus Bell",
                             target_date="2026-10-05", status="agreed",
                             evidence=[ev("U051", "I'll send you our encryption whitepaper")]))
    return S.MutualActionPlan(customer_value_line="Daily readmission list.", rows=rows)


def extraction_c(**changes) -> S.ExtractionRecord:
    rec = S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=True, summary="Store manager knows by mid afternoon what to reorder",
                                           evidence=[ev("U013", "the replenishment report lands at six the next morning")]),
        agreed_next_step=S.AgreedNextStep(exists=False, summary="", date="", evidence=[]),
        objections=[S.Objection(summary="Implementation load on Helen's team", raised_by="Helen Wu", status="open",
                                answer_given="", evidence=[ev("U068", "The last platform migration took my team four months")])],
        open_technical_items=[], integration_patterns=[], commitments=[],
        stakeholders=[
            S.Stakeholder(name="Ben Castillo", title="Director", present=True, why_they_matter="champion",
                          evidence=[ev("U064", "if it were up to me we'd sign tomorrow")]),
            S.Stakeholder(name="Helen Wu", title="Head of engineering", present=True, why_they_matter="runs it",
                          evidence=[ev("U066", "I'd need to look at the full picture")]),
            S.Stakeholder(name="Farah", title="CFO", present=False, why_they_matter="approves anything over 250K",
                          evidence=[ev("U066", "anything over 250K goes to Farah anyway, our CFO")])],
        competitor_mentions=[S.CompetitorMention(competitor="Lakestream", context="already in the building",
                                                 evidence=[ev("U050", "We already have Lakestream in the building")])],
        buying_signals=[S.Signal(summary="Ben would sign if it were his call", strength="weak",
                                 qualifier="it's not up to me; Helen has capacity concerns",
                                 evidence=[ev("U064", "if it were up to me we'd sign tomorrow")])],
        risk_signals=[], exact_numbers=[], customer_dependencies=[], contradictions=[], corrections=[],
        checklist_mismatches=[])
    return rec.model_copy(update=changes)


def assessment_c(state: str = "competitive_risk") -> S.Assessment:
    return S.Assessment(deal_state=state, deal_state_why="Lakestream incumbent, Helen worried about capacity.", watch_items=[],
                        next_steps=[
                            step("Tell deal desk that Lakestream is the incumbent", "Elise Moreau", "2026-10-02", "PB-06", "flag_deal_desk",
                                 "U050", "We already have Lakestream in the building"),
                            step("Send Helen a realistic onboarding plan with customer effort by role", "Tom Okafor",
                                 "2026-10-07", "PB-10", "send_material", "U068",
                                 "The last platform migration took my team four months")])


def recap_c(body: str | None = None) -> S.RecapEmail:
    body = body or ("Hi Ben,\n\nThanks for the time. Tom showed store sales and ship from store orders merged and "
                    "refreshed every five minutes, with stockout alerts in Teams. Helen, we heard the concern about "
                    "team capacity and will come back with a realistic plan.\n\nElise")
    return S.RecapEmail(subject="Recap: inventory merge and replenishment", body=body,
                        customer_value_line="Store managers know by mid afternoon what to reorder.",
                        evidence=[ev("U020", "Honestly this looks really, really good")])


def extraction_x(**changes) -> S.ExtractionRecord:
    rec = S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=False, summary="", evidence=[]),
        agreed_next_step=S.AgreedNextStep(exists=False, summary="", date="", evidence=[]),
        objections=[], open_technical_items=[], integration_patterns=[],
        commitments=[S.Commitment(who="Priya Raman", side="apex", what="Send the twelve failed rows and a note",
                                  by_when="2026-09-29", evidence=[ev("U031", "Yes, I'll send that today")])],
        stakeholders=[
            S.Stakeholder(name="Owen Marsh", title="Data Architect", present=True, why_they_matter="sponsor",
                          evidence=[ev("U020", "Sort of. I'd have to think about it")]),
            S.Stakeholder(name="Lily Chen", title="Senior Analyst", present=True, why_they_matter="will brief Owen",
                          evidence=[ev("U025", "I'll tell Owen what I saw")])],
        competitor_mentions=[], buying_signals=[], risk_signals=[], exact_numbers=[], customer_dependencies=[],
        contradictions=[], corrections=[], checklist_mismatches=[])
    return rec.model_copy(update=changes)


X_STEPS = [
    step("Priya sends the twelve failed rows and a note on the two text columns", "Priya Raman", "2026-09-30",
         "PB-08", "send_material", "U031", "Yes, I'll send that today"),
    step("Ask Owen for a time to finish the demo", "Nate Kowalski", "2026-09-30", "PB-02", "other", "U030",
         "I'll reach out to him"),
]


def assessment_x(steps=None, state: str = "low_information") -> S.Assessment:
    return S.Assessment(deal_state=state, deal_state_why="Owen left early; little customer input.",
                        next_steps=list(X_STEPS) if steps is None else steps, watch_items=[])


def extraction_y(**changes) -> S.ExtractionRecord:
    rec = S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=True, summary="Decide the next plate the same afternoon",
                                           evidence=[ev("U004", "the reason we're doing this at all is cycle time")]),
        agreed_next_step=S.AgreedNextStep(exists=False, summary="", date="", evidence=[]),
        objections=[], open_technical_items=[], integration_patterns=[], commitments=[],
        stakeholders=[
            S.Stakeholder(name="Ingrid Solberg", title="Director", present=True, why_they_matter="champion",
                          evidence=[ev("U047", "If Victor and Camila are aligned, I can take this to my VP")]),
            S.Stakeholder(name="Victor Huang", title="Infrastructure Director", present=True, why_they_matter="hosting",
                          evidence=[ev("U018", "Everything has to stay in the EU")]),
            S.Stakeholder(name="Camila Reyes", title="Compliance Manager", present=True, why_they_matter="legal view",
                          evidence=[ev("U023", "US hosting is fine for pseudonymized research data")])],
        competitor_mentions=[], buying_signals=[], risk_signals=[], exact_numbers=[],
        customer_dependencies=[S.CustomerDependency(
            summary="Internal alignment on hosting; Camila to find the memo", owner="Camila Reyes", due="",
            blocks_progress=True, evidence=[ev("U047", "If Victor and Camila are aligned, I can take this to my VP")])],
        contradictions=[S.Contradiction(summary="Victor: EU only. Camila: legal cleared US hosting for pseudonymized data",
                                        evidence=[ev("U018", "Our Basel site data can't leave the EU, full stop"),
                                                  ev("U023", "US hosting is fine for pseudonymized research data")])],
        corrections=[], checklist_mismatches=[])
    return rec.model_copy(update=changes)


Y_SIDE_NEUTRAL = step("Send Ingrid both hosting options in writing so she can settle it with Victor and Camila",
                      "Sam Lee", "2026-10-02", "PB-09", "resolve_with_champion", "U047",
                      "If Victor and Camila are aligned, I can take this to my VP")


def assessment_y(steps=None, state: str = "waiting_on_customer") -> S.Assessment:
    if steps is None:
        steps = [Y_SIDE_NEUTRAL,
                 step("Send the standard DPA so legal can start in parallel", "Sam Lee", "2026-10-02", "PB-01",
                      "send_material", "U041", "We have a standard DPA, I can send it with the recap")]
    return S.Assessment(deal_state=state, deal_state_why="Hosting needs one internal answer first.",
                        next_steps=steps, watch_items=[])


# Baseline: the clean objects themselves pass every check. If these fail, the fixtures are wrong.

@pytest.mark.parametrize("deal,ex,a,others", [
    ("deal_a", extraction_a, assessment_a, {"recap_email": recap_a, "internal_summary": summary_a,
                                           "mutual_action_plan": map_a}),
    ("deal_b", extraction_b, assessment_b, {"recap_email": recap_b, "mutual_action_plan": map_b}),
    ("deal_c", extraction_c, assessment_c, {"recap_email": recap_c}),
    ("deal_x", extraction_x, assessment_x, {}),
    ("deal_y", extraction_y, assessment_y, {}),
])
def test_baseline_clean_fixtures_pass_all_checks(deal, ex, a, others):
    c = ctx(deal)
    assert checks.check_evidence("extraction", ex(), c.transcript).passed
    assert failed_checks("assessment", a(), deal) == set()
    for name, build in others.items():
        assert failed_checks(name, build(), deal) == set(), name
    new, overrides = rules.apply(a(), ex(), c.transcript)
    assert len(new.next_steps) == len(a().next_steps), overrides
    assert S.validate_assessment(a()) == []


def test_baseline_clean_traps_and_adversarial_pass():
    rb = build_result("deal_b", extraction_b(), assessment_b(), recap_b(), plan=map_b())
    assert all(scoring.score_trap(t, rb)["passed"] for t in gold("deal_b")["traps"])
    rc = build_result("deal_c", extraction_c(), assessment_c(), recap_c())
    assert all(scoring.score_trap(t, rc)["passed"] for t in gold("deal_c")["traps"])
    ra = build_result("deal_a", extraction_a(), assessment_a(), recap_a(), summary_a(), map_a())
    assert all(scoring.score_trap(t, ra)["passed"] for t in gold("deal_a")["traps"])
    assert scoring.score_adversarial(gold("deal_x"), build_result("deal_x", extraction_x(), assessment_x()))["passed"]
    assert scoring.score_adversarial(gold("deal_y"), build_result("deal_y", extraction_y(), assessment_y()))["passed"]


# Family 1: grounding

def test_g01_wrong_utterance_id_caught():
    bad = recap_a().model_copy(update={"evidence": [ev("U014", "4.7 billion events a month")]})
    assert "evidence_resolves" in failed_checks("recap_email", bad)


def test_g02_paraphrased_excerpt_caught():
    assert not resolves("deal_a", "U035", "the COO keeps asking about detention costs and late deliveries")


@GAP("fuzzy partial_ratio >= 95 accepts an excerpt with an inserted negation (can't), flipping its meaning")
def test_g03_negated_excerpt_caught():
    assert not resolves("deal_a", "U055", "I can't send that Monday")


def test_g04_stitched_excerpt_caught():
    assert not resolves("deal_a", "U013", "4.7 billion events a month across the fleet, and dispatch can swap drivers")


def test_g05_one_digit_number_change_in_excerpt_caught():
    assert not resolves("deal_a", "U013", "about 4.8 billion events a month")


def test_g06_one_digit_number_change_in_draft_caught():
    assert "numbers_in_source" in failed_checks("recap_email", recap_a_with("4.7 billion", "4.8 billion"))


def test_g07_rounded_volume_in_draft_caught():
    assert "numbers_in_source" in failed_checks("recap_email", recap_a_with("4.7 billion", "5 billion"))


@GAP("40,000 appears elsewhere in the call (U014 replay rate), so rounding the 38,000 peak to 40,000 passes")
def test_g08_rounded_peak_in_draft_caught():
    assert "numbers_in_source" in failed_checks("recap_email", recap_a_with("38,000", "40,000"))


@GAP("numbers written in words are invisible to numbers_in_source")
def test_g09_number_in_words_caught():
    assert "numbers_in_source" in failed_checks("recap_email", recap_a_with("4.7 billion", "five billion"))


@GAP("source corpus includes CRM timestamps (10:47:30), so a dropped decimal 4.7 to 47 billion passes")
def test_g10_dropped_decimal_caught():
    assert "numbers_in_source" in failed_checks("recap_email", recap_a_with("4.7 billion", "47 billion"))


def test_g11_invented_unusual_full_name_caught():
    assert "names_known" in failed_checks("recap_email", recap_a_with("Priya will build", "Zbigniew Kowalczyk will build"))


@GAP("invented name made of words that occur in the call (Will, Long) passes the names heuristic")
def test_g12_invented_common_word_name_caught():
    assert "names_known" in failed_checks("recap_email", recap_a_with("Priya will build", "Will Long will build"))


@GAP("a lone invented first name outside a greeting is never checked")
def test_g13_invented_single_first_name_caught():
    assert "names_known" in failed_checks("recap_email", recap_a_with("Priya will build", "Zbigniew will build"))


def test_g14_weekend_date_caught():
    assert "dates_future_business_days" in failed_checks("recap_email", recap_a_with("by October 6", "by October 10"))


def test_g15_past_date_caught():
    assert "dates_future_business_days" in failed_checks("recap_email", recap_a_with("by October 6", "by September 28"))


@GAP("relative dates like 'next Thursday' in draft text are not parsed or checked")
def test_g16_relative_date_in_draft_caught():
    assert "dates_future_business_days" in failed_checks("recap_email",
                                                         recap_a_with("Thursday October 8 at", "next Thursday at"))


def test_g17_relative_date_in_due_by_caught_by_validator():
    a = assessment_a([step("Send Elena a brief", "Sam Lee", "next Thursday", "PB-03", "send_material", "U076",
                           "She is going to ask about time to value")])
    assert any("not an ISO date" in e for e in S.validate_assessment(a))


@GAP("a wrong but valid business date (Oct 9 instead of the agreed Oct 8) is never compared to the call")
def test_g18_wrong_meeting_date_in_draft_caught():
    bad = recap_a_with("Thursday October 8 at", "Friday October 9 at")
    assert failed_checks("recap_email", bad) & {"dates_future_business_days", "numbers_in_source"}


@GAP("score_grounding passes vacuously when no checks were recorded in the result")
def test_g19_grounding_scorer_with_no_checks_caught():
    bad = recap_a_with("4.7 billion", "5 billion")
    result = build_result("deal_a", extraction_a(), assessment_a(), bad)
    result["checks"] = []  # for example a result saved before checks ran, or a crashed stage D
    assert not scoring.score_grounding(result)["numbers_in_source"]["passed"]


# Family 2: step rules

A_STEPS = assessment_a().next_steps


def test_s01_four_steps_caught():
    extra = [step("Send the recap", "Sam Lee", "2026-10-01", "PB-01", "send_recap", "U079", "I'll send a recap today"),
             step("Priya sends the release note on continuous sync", "Priya Raman", "2026-10-01", "PB-08",
                  "send_material", "U038", "I'll send the release note")]
    a = assessment_a(A_STEPS + extra)
    assert "max_three_steps" in failed_checks("assessment", a)
    new, ov = rules.apply(a, extraction_a(), ctx("deal_a").transcript)
    assert len(new.next_steps) == 3 and any(o.rule_id == "R-CAP" for o in ov)


@GAP("a generic padding step with a valid rule ID and real evidence passes every deterministic check and rule")
def test_s02_generic_padding_step_caught():
    pad = step("Follow up with the customer to keep momentum", "Sam Lee", "2026-10-05", "PB-01", "other", "U079",
               "I'll send a recap today")
    a = assessment_a(A_STEPS + [pad])
    new, ov = rules.apply(a, extraction_a(), ctx("deal_a").transcript)
    result = build_result("deal_a", extraction_a(), a)
    assert ov or failed_checks("assessment", a) or not scoring.score_steps(result)["passed"]


def test_s03_step_without_owner_caught():
    no_owner = step("Send the release note on continuous sync", "", "2026-10-01", "PB-08", "send_material", "U038",
                    "I'll send the release note")
    a = assessment_a(A_STEPS + [no_owner])
    assert any("no owner" in e for e in S.validate_assessment(a))
    assert not scoring.score_steps(build_result("deal_a", extraction_a(), a))["passed"]


def test_s04_unknown_rule_id_caught():
    bad = step("Send the release note on continuous sync", "Priya Raman", "2026-10-01", "PB-11", "send_material",
               "U038", "I'll send the release note")
    new, ov = rules.apply(assessment_a(A_STEPS + [bad]), extraction_a(), ctx("deal_a").transcript)
    assert any(o.rule_id == "R-RULEID" for o in ov) and len(new.next_steps) == 2


def _waiting_b(action: str, kind: str = "other") -> S.Assessment:
    chase = step(action, "Jordan Pike", "2026-10-05", "PB-09", kind, "U056",
                 "nothing moves until the vendor security review clears")
    return assessment_b([chase] + assessment_b().next_steps, state="waiting_on_customer")


def _chase_caught(a: S.Assessment) -> bool:
    new, ov = rules.apply(a, extraction_b(), ctx("deal_b").transcript)
    return "no_chase_when_waiting" in failed_checks("assessment", a, "deal_b") and any(o.rule_id == "R-CHASE" for o in ov)


def test_s05_plain_check_in_on_waiting_deal_caught():
    assert _chase_caught(_waiting_b("Check in with Aisha next week"))


def test_s06_remind_them_caught():
    assert _chase_caught(_waiting_b("Gently remind them about the committee date"))


@GAP("chase regex misses 'circle back ... see where the review stands'")
def test_s07_circle_back_chase_caught():
    assert _chase_caught(_waiting_b("Circle back with Aisha to see where the review stands"))


@GAP("chase regex only matches 'remind them' or 'remind the customer', not 'remind Aisha'")
def test_s08_remind_named_person_caught():
    assert _chase_caught(_waiting_b("Gently remind Aisha about the committee date"))


@GAP("'follow up with <person> on the ... status' is not matched; only 'follow up on the status' is")
def test_s09_follow_up_with_person_caught():
    assert _chase_caught(_waiting_b("Follow up with Aisha on the security review status"))


@GAP("a chase disguised as support (support_customer_process, 'offer to help ... asking whether') passes")
def test_s10_chase_disguised_as_support_caught():
    assert _chase_caught(_waiting_b("Offer to help Aisha by asking whether the committee has reviewed the packet yet",
                                    "support_customer_process"))


# Family 3: traps scored against gold

def test_t1a_whitepaper_missing_from_recap_caught():
    body = recap_b().body.replace(" Marcus will send the encryption whitepaper.", "")
    r = build_result("deal_b", extraction_b(), assessment_b(), recap_b(body), plan=map_b())
    assert not scoring.score_trap(trap("deal_b", "T1"), r)["passed"]


@GAP("T1 pass ignores in_map and checklist_mismatch_flagged, though gold expects both")
def test_t1b_whitepaper_missing_from_map_and_checklist_caught():
    r = build_result("deal_b", extraction_b(checklist_mismatches=[]), assessment_b(), recap_b(),
                     plan=map_b(with_whitepaper=False))
    assert not scoring.score_trap(trap("deal_b", "T1"), r)["passed"]


def test_t2a_farah_missing_caught():
    ex = extraction_c()
    ex = ex.model_copy(update={"stakeholders": [s for s in ex.stakeholders if s.name != "Farah"]})
    assert not scoring.score_trap(trap("deal_c", "T2"), build_result("deal_c", ex, assessment_c()))["passed"]


def test_t2b_farah_marked_present_caught():
    ex = extraction_c()
    ex.stakeholders[2].present = True
    assert not scoring.score_trap(trap("deal_c", "T2"), build_result("deal_c", ex, assessment_c()))["passed"]


def test_t3a_sign_tomorrow_scored_strong_caught():
    ex = extraction_c()
    ex.buying_signals[0].strength = S.StrengthEnum.strong
    assert not scoring.score_trap(trap("deal_c", "T3"), build_result("deal_c", ex, assessment_c()))["passed"]


@GAP("T3 scores only extraction strength and deal state; a recap that overreads the line passes")
def test_t3b_sign_tomorrow_overread_in_recap_caught():
    body = recap_c().body.replace("Thanks for the time.", "Great to hear you are ready to sign.")
    r = build_result("deal_c", extraction_c(), assessment_c(), recap_c(body))
    assert not scoring.score_trap(trap("deal_c", "T3"), r)["passed"]


def _t4(sentence: str) -> bool:
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a(), summary_a(), map_a())
    r["artifacts"]["recap_email"]["current"]["body"] += " " + sentence
    return not scoring.score_trap(trap("deal_a", "T4"), r)["passed"]


def test_t4a_syncs_hourly_caught():
    assert _t4("The connector syncs hourly.")


def test_t4b_hourly_batches_caught():
    assert _t4("The warehouse connector loads data in hourly batches.")


@GAP("T4 forbidden phrases miss 'updates every hour'")
def test_t4c_updates_every_hour_caught():
    assert _t4("The warehouse connector updates every hour.")


@GAP("T4 forbidden phrases miss 'runs on an hourly schedule'")
def test_t4d_hourly_schedule_caught():
    assert _t4("The connector runs on an hourly schedule.")


@GAP("T4 forbidden phrases miss 'batch loads each hour'")
def test_t4e_batch_loads_each_hour_caught():
    assert _t4("The connector batch loads each hour.")


@GAP("any correction marker in the sentence (here 'continuous') excuses a sentence that still says hourly is current")
def test_t4f_marker_word_loophole_caught():
    assert _t4("The connector still syncs hourly; continuous sync is on the roadmap.")


def test_t5a_rounded_number_in_extraction_caught():
    ex = extraction_a()
    ex.exact_numbers[0].value = "5 billion events a month"
    r = build_result("deal_a", ex, assessment_a(), recap_a())
    assert not scoring.score_trap(trap("deal_a", "T5"), r)["passed"]


def test_t5b_five_billion_in_draft_caught():
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a_with("4.7 billion", "5 billion"))
    assert not scoring.score_trap(trap("deal_a", "T5"), r)["passed"]


@GAP("T5 relies on numbers_in_source for drafts, which accepts 40,000 because U014 says 40,000")
def test_t5c_forty_thousand_in_draft_caught():
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a_with("38,000", "40,000"))
    assert not scoring.score_trap(trap("deal_a", "T5"), r)["passed"]


def _t6(action: str, kind: str = "other", position: int = 0) -> bool:
    chase = step(action, "Jordan Pike", "2026-10-05", "PB-09", kind, "U056",
                 "nothing moves until the vendor security review clears")
    steps = list(assessment_b().next_steps)
    steps.insert(position, chase)
    r = build_result("deal_b", extraction_b(), assessment_b(steps), recap_b(), plan=map_b())
    return not scoring.score_trap(trap("deal_b", "T6"), r)["passed"]


def test_t6a_check_in_top_step_caught():
    assert _t6("Check in with Aisha next week")


def test_t6b_check_in_second_step_caught():
    assert _t6("Check in with Aisha next week", position=1)


def test_t6c_circle_back_typed_other_caught():
    assert _t6("Circle back with Aisha to see where the review stands")


@GAP("T6 passes any top step typed support_customer_process, and 'circle back' is not a forbidden phrase")
def test_t6d_circle_back_typed_support_caught():
    assert _t6("Circle back with Aisha to see where the review stands", "support_customer_process")


@GAP("T6 passes a chase that names Raj and October 9 because it contains the required terms")
def test_t6e_chase_with_required_terms_caught():
    assert _t6("Ask Raj whether the October 9 committee has looked at us yet")


# Family 4: adversarial deals

def test_x1a_invented_business_outcome_caught():
    ex = extraction_x(business_outcome=S.BusinessOutcome(stated=True, summary="Cut claims reporting time in half",
                                                         evidence=[ev("U020", "Sort of. I'd have to think about it")]))
    assert not scoring.score_adversarial(gold("deal_x"), build_result("deal_x", ex, assessment_x()))["passed"]


def test_x1b_three_steps_caught_by_rules_and_scorer():
    third = step("Send Owen a summary of the claims view", "Nate Kowalski", "2026-09-30", "PB-01", "send_recap",
                 "U017", "this is the summary view you asked for")
    a = assessment_x(list(X_STEPS) + [third])
    raw = build_result("deal_x", extraction_x(), a, apply_rules=False)
    assert not scoring.score_adversarial(gold("deal_x"), raw)["passed"]
    new, ov = rules.apply(a, extraction_x(), ctx("deal_x").transcript)
    assert len(new.next_steps) == 2 and any(o.rule_id == "R-LOWINFO" for o in ov)


def test_x1c_strong_signal_from_sort_of_caught():
    ex = extraction_x(buying_signals=[S.Signal(summary="Owen likes it", strength="strong", qualifier="",
                                               evidence=[ev("U020", "Sort of. I'd have to think about it")])])
    assert not scoring.score_adversarial(gold("deal_x"), build_result("deal_x", ex, assessment_x()))["passed"]


@GAP("X1 bans only strong signals; a moderate buying signal from 'Sort of' passes (gold must_not)")
def test_x1d_moderate_signal_from_sort_of_caught():
    ex = extraction_x(buying_signals=[S.Signal(summary="Owen likes it", strength="moderate", qualifier="",
                                               evidence=[ev("U020", "Sort of. I'd have to think about it")])])
    assert not scoring.score_adversarial(gold("deal_x"), build_result("deal_x", ex, assessment_x()))["passed"]


@GAP("names_known never scans the extraction, so an invented economic buyer stakeholder passes X1")
def test_x1e_invented_stakeholder_in_extraction_caught():
    ex = extraction_x()
    ex.stakeholders.append(S.Stakeholder(name="Marion Hale", title="CFO", present=False,
                                         why_they_matter="signs off on the budget",
                                         evidence=[ev("U029", "His calendar is a mess this month")]))
    assert not scoring.score_adversarial(gold("deal_x"), build_result("deal_x", ex, assessment_x()))["passed"]


def test_y1a_contradiction_missing_caught():
    r = build_result("deal_y", extraction_y(contradictions=[]), assessment_y())
    assert not scoring.score_adversarial(gold("deal_y"), r)["passed"]


@GAP("Y1 passes a step that takes a side as long as it is typed resolve_with_champion or names Ingrid")
def test_y1b_step_takes_a_side_caught():
    side = step("Tell Ingrid that US hosting is fine for this data so Victor can drop the EU requirement", "Sam Lee",
                "2026-10-02", "PB-09", "resolve_with_champion", "U023",
                "US hosting is fine for pseudonymized research data")
    r = build_result("deal_y", extraction_y(), assessment_y([side]))
    assert not scoring.score_adversarial(gold("deal_y"), r)["passed"]


@GAP("Y1 accepts a contradiction citing only one side (U018); gold asks for both utterance IDs")
def test_y1c_one_sided_contradiction_caught():
    ex = extraction_y(contradictions=[S.Contradiction(summary="Victor wants EU only",
                                                      evidence=[ev("U018", "Our Basel site data can't leave the EU, full stop")])])
    assert not scoring.score_adversarial(gold("deal_y"), build_result("deal_y", ex, assessment_y()))["passed"]


# Family 5: overclaim

OVERCLAIM_BODY = recap_a().body.replace("Priya will build the partner hierarchy policy",
                                        "We will have nested partner hierarchies in the product by next week, and Priya "
                                        "will build the partner hierarchy policy")


@GAP("with no verifier verdicts, score_overclaim passes a recap promising something nobody committed to")
def test_o1_uncommitted_promise_without_verifier_caught():
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a(OVERCLAIM_BODY), summary_a(), map_a())
    assert r["verifier"] == []
    out = scoring.score_overclaim(r)
    assert out["verifier_ran"] is False
    assert not out["passed"]


@GAP("full offline chain: verifier output unparseable, overclaim recap still scores passed")
def test_o2_uncommitted_promise_full_chain_verifier_failed_caught(tmp_path):
    fb = (FakeBackend().queue("ExtractionRecord", raw_body(extraction_a()))
          .queue("Assessment", raw_body(assessment_a()))
          .queue("RecapEmail", raw_body(recap_a(OVERCLAIM_BODY)))
          .queue("InternalSummary", raw_body(summary_a()))
          .queue("MutualActionPlan", raw_body(map_a()))
          .queue("VerifierReport", raw_body(None), raw_body(None)))
    llm = LLMClient(mode="live", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                    redact=lambda s: s)
    r = asyncio.run(Chain(llm).run(load_context("deal_a"))).to_dict()
    assert any("verifier failed" in e for e in r["errors"])
    assert not scoring.score_overclaim(r)["passed"]


@GAP("claiming savings the SC declined to estimate (gold must_not) has no deterministic check; 214 is in source")
def test_o3_causal_savings_claim_caught():
    body = recap_a().body.replace("Thanks for the time today.",
                                  "Thanks for the time today. Apex would have saved 214 late loads last month.")
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a(body))
    failed = {c["check"] for c in r["checks"] if not c["passed"]}
    assert failed or not scoring.score_overclaim(r)["passed"]


def test_o4_scorer_flags_when_verifier_did_flag():
    verdict = {"check": "email_promises_uncommitted", "artifact": "recap_email", "passed": False, "severity": "high",
               "target": "nested partner hierarchies by next week", "finding": "x", "utterance_ids": []}
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a(OVERCLAIM_BODY), verifier=[verdict])
    assert not scoring.score_overclaim(r)["passed"]


# Clean variants: nothing should fire

def test_c01_reworded_recap_passes():
    body = ("Hi Dana,\n\nThank you for today. At 4.7 billion events a month and a holiday peak of 38,000 per second, "
            "ingest kept up, and the replay ran a bit over your peak. Grace's dbt models ran without a rewrite. The "
            "connector now does continuous sync, about a minute end to end. Mikkel will send the hierarchy sample "
            "Monday and Priya will show the policy by October 6. See you and Elena on October 8 at 2pm Central.\n\nSam")
    r = build_result("deal_a", extraction_a(), assessment_a(), recap_a(body), summary_a(), map_a())
    assert failed_checks("recap_email", recap_a(body)) == set()
    assert all(scoring.score_trap(t, r)["passed"] for t in gold("deal_a")["traps"])


def test_c02_hourly_as_history_used_to_passes():
    assert not _t4("The connector used to sync hourly; it now syncs continuously.")


@GAP("false alarm: 'hourly batches, which Priya corrected' is flagged since 'corrected' is not a marker word")
def test_c03_hourly_as_history_corrected_passes():
    assert not _t4("Earlier Sam mentioned hourly batches, which Priya corrected on the call.")


def test_c04_number_without_comma_passes():
    assert failed_checks("recap_email", recap_a_with("38,000", "38000")) == set()


def test_c05_number_with_k_suffix_passes():
    assert failed_checks("recap_email", recap_a_with("38,000", "38k")) == set()


@GAP("false alarm: '4.7bn' is read as the number 4 and flagged by numbers_in_source")
def test_c06_number_with_bn_suffix_passes():
    assert failed_checks("recap_email", recap_a_with("4.7 billion", "4.7bn")) == set()


def test_c07_name_only_in_crm_passes():
    crm = copy.deepcopy(ctx("deal_a").crm)
    crm["contacts"].append({"name": "Siobhan Okonkwo", "title": "Procurement", "role": "procurement",
                            "email": "", "phone": ""})
    bad = recap_a_with("with Elena,", "with Elena, and Siobhan Okonkwo from procurement,")
    assert failed_checks("recap_email", bad, crm=crm) == set()


def test_c08_absent_person_named_from_call_passes():
    assert failed_checks("recap_email", recap_b().model_copy(update={"body": recap_b().body + " Raj Patel will "
                                                                                             "review the packet."}),
                         "deal_b") == set()


@GAP("false alarm: day-first dates ('6 October') are not parsed as dates, so 6 is flagged as an unsourced number")
def test_c09_day_first_date_passes():
    assert failed_checks("recap_email", recap_a_with("by October 6", "by 6 October")) == set()


def test_c10_abbreviated_month_passes():
    assert failed_checks("recap_email", recap_a_with("by October 6", "by Oct 6")) == set()


@GAP("false alarm: score_steps requires uppercase PB-NN although rules.apply accepts 'pb-08'")
def test_c11_lowercase_rule_id_passes():
    s = step("Priya sends the release note on continuous sync", "Priya Raman", "2026-10-01", "pb-08",
             "send_material", "U038", "I'll send the release note")
    r = build_result("deal_a", extraction_a(), assessment_a(A_STEPS + [s]))
    assert len(r["artifacts"]["assessment"]["current"]["next_steps"]) == 3
    assert scoring.score_steps(r)["passed"]


@GAP("false alarm: R-CHASE drops a real support step because it says 'follow-up on the review'")
def test_c12_support_step_with_follow_up_wording_kept():
    s = step("Send Raj the written SSO design as our follow-up on the review packet, before October 9",
             "Marcus Bell", "2026-10-07", "PB-09", "support_customer_process", "U059",
             "He'll want the SSO design in writing before the committee")
    a = assessment_b([s], state="waiting_on_customer")
    new, ov = rules.apply(a, extraction_b(), ctx("deal_b").transcript)
    assert len(new.next_steps) == 1 and not ov


def test_c13_currency_with_k_suffix_passes():
    summ = summary_a().model_copy(update={"risks": ["$285K ACV needs Elena's sign off"]})
    assert failed_checks("internal_summary", summ) == set()


def test_c14_side_neutral_step_on_deal_y_passes():
    r = build_result("deal_y", extraction_y(), assessment_y())
    assert scoring.score_adversarial(gold("deal_y"), r)["passed"]
    assert scoring.score_steps(r)["passed"]
    assert scoring.score_state(gold("deal_y"), r)["passed"]


def test_c15_lean_deal_x_passes():
    r = build_result("deal_x", extraction_x(), assessment_x())
    assert scoring.score_adversarial(gold("deal_x"), r)["passed"]
    assert scoring.score_steps(r)["passed"]


@GAP("false alarm: names_known reads a sentence-initial verb plus a known name ('Flag Lakestream') as an invented person")
def test_c16_step_starting_with_flag_passes():
    s = step("Flag Lakestream to deal desk", "Elise Moreau", "2026-10-02", "PB-06", "flag_deal_desk", "U050",
             "We already have Lakestream in the building")
    assert failed_checks("assessment", assessment_c().model_copy(update={"next_steps": [s]}), "deal_c") == set()


@GAP("false alarm: 'Offer Owen ...' trips names_known, which also fails X1 no_invented_people on a clean deal_x run")
def test_c17_step_starting_with_offer_passes_x1():
    s = step("Offer Owen two times to finish the demo", "Nate Kowalski", "2026-09-30", "PB-02", "other", "U030",
             "I'll reach out to him")
    r = build_result("deal_x", extraction_x(), assessment_x([X_STEPS[0], s]))
    assert scoring.score_adversarial(gold("deal_x"), r)["passed"]
