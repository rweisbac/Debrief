"""Build the hand-written sample debriefs used by `make demo` before any real recording exists.

These outputs are written by hand to show the layout. They are NOT model output, and every place that
shows them says so. They still go through the real chain code (rules, MAP enforcement, deterministic
checks) via a scripted backend, so the card shows what the code does with them. Excerpts are copied word
for word from the transcripts.

Run: python scripts/build_samples.py   (writes fixtures/samples/<deal>.json)
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel  # noqa: E402

from src import schemas as S  # noqa: E402
from src.chain import Chain, load_context  # noqa: E402
from src.llm import LLMClient  # noqa: E402

OUT = ROOT / "fixtures" / "samples"
SAMPLE_LABEL = ("Sample card written by hand to show the layout. Not generated from the call. "
                "See the README to generate real debriefs.")


def ev(uid, excerpt):
    return S.EvidenceRef(utterance_id=uid, excerpt=excerpt)


class SampleBackend:
    """Returns the hand-written object for each output model, in order. Offline only."""

    def __init__(self, outputs: dict[str, list[BaseModel]]):
        self.queues = defaultdict(deque, {k: deque(v) for k, v in outputs.items()})

    async def send(self, request, output_model):
        q = self.queues[output_model.__name__]
        if not q:
            raise RuntimeError(f"sample has no {output_model.__name__} left; a check probably failed on the sample")
        obj = q.popleft()
        raw = {"content": [{"type": "text", "text": obj.model_dump_json()}], "stop_reason": "end_turn",
               "usage": {"input_tokens": 0, "output_tokens": 0}}
        return raw, obj, ""


def verdicts(*artifacts: str) -> S.VerifierReport:
    return S.VerifierReport(verdicts=[S.VerifierVerdict(check="quote_supports_claim", artifact=a, target="all",
                                                        passed=True, severity="low", finding="Sample: no issues.",
                                                        utterance_ids=[]) for a in artifacts])


def deal_a() -> dict[str, list[BaseModel]]:
    x = S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=True, summary="Catch a late load while dispatch can still reroute it, not the next morning",
                                           evidence=[ev("U035", "dispatch can swap drivers or call the consignee")]),
        agreed_next_step=S.AgreedNextStep(exists=True, summary="45 minute session with Elena Varga on late load detection and commercials",
                                          date="2026-10-08", evidence=[ev("U072", "Thursday October 8th, 2pm Central, forty five minutes")]),
        objections=[
            S.Objection(summary="Hourly connector sync too slow for dispatch dashboards", raised_by="Grace Oyelaran", status="resolved",
                        answer_given="The connector does continuous sync since the August release", evidence=[ev("U009", "Hourly might be tight for us")]),
            S.Objection(summary="Elena will question time to value after a slow past project", raised_by="Dana Ortiz", status="open",
                        answer_given="Bring a realistic onboarding plan to the Elena session", evidence=[ev("U076", "She got burned on the last platform project")])],
        open_technical_items=[S.OpenItem(summary="Row level access for partners with sub carriers", owner="Priya Raman",
                                         evidence=[ev("U052", "What I don't know yet is how your partner hierarchy works")])],
        integration_patterns=[S.IntegrationPattern(summary="Existing dbt models run as is; two macros move to a seed table",
                                                   evidence=[ev("U027", "move that lookup into a seed table or a pre-hook")])],
        commitments=[
            S.Commitment(who="Priya Raman", side="apex", what="Build the partner hierarchy policy in the sandbox", by_when="2026-10-06",
                         evidence=[ev("U054", "I can have that back to you by Tuesday the sixth")]),
            S.Commitment(who="Mikkel Strand", side="customer", what="Send a sample of the partner hierarchy table", by_when="2026-10-05",
                         evidence=[ev("U055", "I can send that Monday")]),
            S.Commitment(who="Priya Raman", side="apex", what="Send the release note on continuous sync", by_when="",
                         evidence=[ev("U038", "I'll send the release note")]),
            S.Commitment(who="Sam Lee", side="apex", what="Send the recap today", by_when="2026-09-30",
                         evidence=[ev("U079", "I'll send a recap today")])],
        stakeholders=[
            S.Stakeholder(name="Dana Ortiz", title="VP Data", present=True, why_they_matter="champion",
                          evidence=[ev("U060", "I think I've seen what I needed to see")]),
            S.Stakeholder(name="Mikkel Strand", title="Data Platform Lead", present=True, why_they_matter="platform owner",
                          evidence=[ev("U061", "Not from the platform side")]),
            S.Stakeholder(name="Grace Oyelaran", title="Analytics Engineering Manager", present=True, why_they_matter="owns dbt models",
                          evidence=[ev("U062", "The macro thing is on us")]),
            S.Stakeholder(name="Elena Varga", title="Chief Operating Officer", present=False, why_they_matter="owns the budget line",
                          evidence=[ev("U066", "she owns the budget line for this")])],
        competitor_mentions=[],
        buying_signals=[S.Signal(summary="Dana called it the most useful vendor session this quarter", strength="moderate",
                                 qualifier="Champion, not the budget owner", evidence=[ev("U080", "the most useful vendor session")])],
        risk_signals=[S.Signal(summary="Time to value is the COO's main concern", strength="moderate", qualifier="",
                               evidence=[ev("U076", "She is going to ask about time to value")])],
        exact_numbers=[S.ExactNumber(value="4.7 billion events a month", what_it_measures="fleet events",
                                     evidence=[ev("U013", "4.7 billion events a month")]),
                       S.ExactNumber(value="38,000 per second", what_it_measures="holiday peak",
                                     evidence=[ev("U013", "peaks around 38,000 per second")])],
        customer_dependencies=[], contradictions=[],
        corrections=[S.Correction(original_statement="The warehouse connector syncs in hourly batches",
                                  corrected_statement="The warehouse connector does continuous sync, about a minute end to end",
                                  evidence=[ev("U038", "The warehouse connector does continuous sync now")])],
        checklist_mismatches=[])
    a = S.Assessment(
        deal_state="ready_to_advance", deal_state_why="Technical fit is clear and the COO session is booked; one open item on partner access.",
        next_steps=[
            S.NextStep(action="Send Elena a one page brief on late load detection and a realistic onboarding plan before Thursday",
                       owner="Sam Lee", due_by="2026-10-06", playbook_rule_id="PB-03", release_card_id="", action_type="send_material",
                       why="Elena missed the demo and was burned by a slow project; reps usually walk in cold.",
                       evidence=[ev("U076", "She got burned on the last platform project")]),
            S.NextStep(action="Make sure Mikkel's hierarchy sample reaches Priya Monday so the partner policy is ready Tuesday",
                       owner="Priya Raman", due_by="2026-10-06", playbook_rule_id="PB-04", release_card_id="RC-07", action_type="route_to_sc",
                       why="The open item depends on a customer file nobody tracks internally.",
                       evidence=[ev("U054", "I can have that back to you by Tuesday the sixth")]),
            S.NextStep(action="Send Mikkel the continuous sync release note Priya promised",
                       owner="Priya Raman", due_by="2026-10-01", playbook_rule_id="PB-08", release_card_id="RC-12", action_type="send_material",
                       why="Promised in passing while correcting the deck; not in the checklist.",
                       evidence=[ev("U038", "I'll send the release note")])],
        watch_items=[])
    recap = S.RecapEmail(subject="Recap: late load detection validation and Thursday with Elena", body=(
        "Hi Dana,\n\nThanks for the time today, and to Mikkel and Grace. A quick recap.\n\n"
        "- Ingest kept up at your volume of 4.7 billion events a month, with lag under four seconds at p95 when we "
        "replayed above your 38,000 per second peak.\n"
        "- Your dbt models ran without a rewrite. Two use a macro that calls an external API at compile time; Grace's "
        "team will move that lookup into a seed table.\n"
        "- The warehouse connector now uses continuous sync, about a minute end to end.\n\n"
        "Open item: row level access for partners with sub carriers. Mikkel will send a sample of the hierarchy table "
        "on Monday, and Priya will show the policy working by Tuesday, October 6. Priya will also send the release note "
        "on continuous sync.\n\n"
        "We are set for Thursday, October 8 at 2pm Central with Elena, focused on catching a late load while dispatch "
        "can still reroute it. We will bring a realistic onboarding plan.\n\nSam"),
        customer_value_line="Fresh data lets dispatch act on a late load while it can still be saved.",
        evidence=[ev("U013", "4.7 billion events a month"), ev("U072", "Thursday October 8th, 2pm Central, forty five minutes")])
    summary = S.InternalSummary(
        deal_state_line="Ready to advance: champion clear, COO session booked for 2026-10-08",
        customer_value_line="Catch a late load while dispatch can still reroute it.",
        what_we_validated=["Ingest at peak volume", "Existing dbt models run as is", "Late load detection on streaming data"],
        integration_patterns=["dbt models run as is; two macros move to a seed table"],
        objections_and_answers=["Hourly sync too slow: continuous sync since August (resolved)",
                                "Time to value for Elena: bring a realistic onboarding plan (open)"],
        open_items=["Partner hierarchy row level policy, Priya Raman"],
        commitments=["Priya Raman: partner policy by 2026-10-06", "Mikkel Strand: hierarchy sample by 2026-10-05",
                     "Priya Raman: continuous sync release note"],
        stakeholders=["Dana Ortiz, champion, present", "Elena Varga, COO, budget owner, absent"],
        competitive_notes=[], risks=["Elena was burned by a slow past project"],
        evidence=[ev("U066", "she owns the budget line for this")])
    plan = S.MutualActionPlan(customer_value_line="Catch a late load while dispatch can still reroute it.", rows=[
        S.MapRow(milestone="Partner hierarchy sample to Priya", customer_owner="Mikkel Strand", apex_owner="Priya Raman",
                 target_date="2026-10-05", status="agreed", evidence=[ev("U055", "I can send that Monday")]),
        S.MapRow(milestone="Partner policy shown in sandbox", customer_owner="Mikkel Strand", apex_owner="Priya Raman",
                 target_date="2026-10-06", status="agreed", evidence=[ev("U054", "I can have that back to you by Tuesday the sixth")]),
        S.MapRow(milestone="Late load session with Elena Varga", customer_owner="Dana Ortiz", apex_owner="Sam Lee",
                 target_date="2026-10-08", status="agreed", evidence=[ev("U072", "Thursday October 8th, 2pm Central, forty five minutes")]),
        S.MapRow(milestone="Commercial proposal", customer_owner="Elena Varga", apex_owner="Sam Lee", target_date="",
                 status="proposed", evidence=[])])
    return {"ExtractionRecord": [x], "Assessment": [a], "RecapEmail": [recap], "InternalSummary": [summary],
            "MutualActionPlan": [plan],
            "VerifierReport": [verdicts("assessment", "recap_email", "internal_summary", "mutual_action_plan")]}


def deal_b() -> dict[str, list[BaseModel]]:
    x = S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=True, summary="A daily readmission list so care managers call while patients still remember them",
                                           evidence=[ev("U027", "The whole goal is daily")]),
        agreed_next_step=S.AgreedNextStep(exists=False, summary="none; Aisha will decide on a meeting after the SSO answer", date="",
                                          evidence=[ev("U075", "Let's see what the answer is first")]),
        objections=[
            S.Objection(summary="SSO: roles arrive in a nested custom claim; Apex maps flat claims today", raised_by="Leo Brandt", status="open",
                        answer_given="Marcus will get a firm answer on native nested claims from the identity team",
                        evidence=[ev("U012", "What I have not personally done is map a nested claim")]),
            S.Objection(summary="Where PHI sits and who holds keys", raised_by="Nora Fitzgerald", status="partially_resolved",
                        answer_given="Dedicated tenant in a US region; customer managed keys available",
                        evidence=[ev("U051", "It sits in your dedicated tenant in a US region")])],
        open_technical_items=[S.OpenItem(summary="Native nested claim support and a date", owner="Marcus Bell",
                                         evidence=[ev("U072", "I need a date I can put in front of Raj")])],
        integration_patterns=[],
        commitments=[
            S.Commitment(who="Marcus Bell", side="apex", what="Send the encryption whitepaper", by_when="",
                         evidence=[ev("U051", "I'll send you our encryption whitepaper")]),
            S.Commitment(who="Marcus Bell", side="apex", what="Get a firm answer on native nested claims", by_when="2026-10-01",
                         evidence=[ev("U023", "I'll take that to our identity team today")]),
            S.Commitment(who="Aisha Karim", side="customer", what="Have procurement send the vendor questionnaire", by_when="",
                         evidence=[ev("U063", "I'll have procurement send it")])],
        stakeholders=[
            S.Stakeholder(name="Aisha Karim", title="Director of Data Engineering", present=True, why_they_matter="champion",
                          evidence=[ev("U056", "I'll be direct about where we are")]),
            S.Stakeholder(name="Leo Brandt", title="Identity and Access Engineer", present=True, why_they_matter="owns the identity layer",
                          evidence=[ev("U009", "We have our own, built about six years ago")]),
            S.Stakeholder(name="Raj Patel", title="Security Architect", present=False, why_they_matter="runs the vendor security committee",
                          evidence=[ev("U059", "He'll want the SSO design in writing before the committee")])],
        competitor_mentions=[], buying_signals=[],
        risk_signals=[S.Signal(summary="Token service change would take six to eight weeks", strength="moderate", qualifier="",
                               evidence=[ev("U021", "six to eight weeks, minimum")])],
        exact_numbers=[S.ExactNumber(value="About 140", what_it_measures="care managers",
                                     evidence=[ev("U037", "About 140 across the three regions")])],
        customer_dependencies=[S.CustomerDependency(summary="Vendor security review committee must approve first", owner="Raj Patel",
                                                    due="2026-10-09", blocks_progress=True,
                                                    evidence=[ev("U056", "nothing moves until the vendor security review clears")])],
        contradictions=[], corrections=[],
        checklist_mismatches=[S.ChecklistMismatch(field="sc_commitment", logged_value="",
                                                  transcript_says="Marcus will send the encryption whitepaper",
                                                  evidence=[ev("U051", "I'll send you our encryption whitepaper")])])
    a = S.Assessment(
        deal_state="open_technical_gap", deal_state_why="Nested SSO claim is unresolved and the security committee meets October 9.",
        next_steps=[
            S.NextStep(action="Send Aisha the security packet with Raj copied: SOC 2, encryption whitepaper and a written SSO design",
                       owner="Jordan Pike", due_by="2026-10-06", playbook_rule_id="PB-09", release_card_id="RC-11",
                       action_type="support_customer_process",
                       why="Missing the committee date pushes the deal a month; reps tend to wait for the questionnaire.",
                       evidence=[ev("U058", "Our vendor questionnaire, your SOC 2 report, the encryption details")]),
            S.NextStep(action="Get Leo a dated answer on native nested claims that he can show Raj",
                       owner="Marcus Bell", due_by="2026-10-02", playbook_rule_id="PB-04", release_card_id="RC-09",
                       action_type="route_to_sc", why="Leo asked for a date, not a roadmap slide.",
                       evidence=[ev("U072", "I need a date I can put in front of Raj")]),
            S.NextStep(action="Send Nora the encryption whitepaper Marcus promised",
                       owner="Marcus Bell", due_by="2026-10-02", playbook_rule_id="PB-08", release_card_id="RC-11",
                       action_type="send_material", why="Said in passing and missing from the checklist.",
                       evidence=[ev("U051", "I'll send you our encryption whitepaper")])],
        watch_items=[])
    recap = S.RecapEmail(subject="Recap: readmission pipeline, SSO and PHI", body=(
        "Hi Aisha,\n\nThanks for the session, and to Leo and Nora. A quick recap.\n\n"
        "- The readmission pipeline ran incrementally; last night's run took nine minutes, and each row shows its top "
        "three drivers.\n"
        "- SSO is open. Your identity layer sends roles in a nested claim, and today we map flat claims. Marcus is "
        "taking native nested claims to our identity team and will come back with a date Leo can show Raj.\n"
        "- Data sits in your dedicated tenant in a US region. Marcus will send our encryption whitepaper.\n\n"
        "For the October 9 committee, we will send you the packet with Raj copied: our SOC 2 report, the encryption "
        "details and a written SSO design, plus your questionnaire once procurement sends it.\n\nJordan"),
        customer_value_line="A daily list means care managers call while patients still remember who we are.",
        evidence=[ev("U051", "I'll send you our encryption whitepaper")])
    summary = S.InternalSummary(
        deal_state_line="Open technical gap: nested SSO claim, security committee on 2026-10-09",
        customer_value_line="A daily readmission list so care managers call the morning after discharge.",
        what_we_validated=["Incremental readmission pipeline", "Top three drivers per patient"],
        integration_patterns=[],
        objections_and_answers=["Nested SSO claim: Marcus to get a date from identity team (open)",
                                "PHI location and keys: US tenant, customer managed keys (partially resolved)"],
        open_items=["Native nested claim date, Marcus Bell"],
        commitments=["Marcus Bell: encryption whitepaper", "Marcus Bell: nested claim answer",
                     "Aisha Karim: procurement sends questionnaire"],
        stakeholders=["Aisha Karim, champion, present", "Raj Patel, security committee, absent"],
        competitive_notes=[], risks=["Token service change would take six to eight weeks"],
        evidence=[ev("U056", "nothing moves until the vendor security review clears")])
    plan = S.MutualActionPlan(customer_value_line="A daily readmission list for care managers.", rows=[
        S.MapRow(milestone="Encryption whitepaper to Nora", customer_owner="Nora Fitzgerald", apex_owner="Marcus Bell",
                 target_date="", status="agreed", evidence=[ev("U051", "I'll send you our encryption whitepaper")]),
        S.MapRow(milestone="Security packet to Aisha, Raj copied", customer_owner="Aisha Karim", apex_owner="Jordan Pike",
                 target_date="2026-10-06", status="proposed", evidence=[]),
        S.MapRow(milestone="Vendor security committee", customer_owner="Raj Patel", apex_owner="",
                 target_date="2026-10-09", status="agreed", evidence=[ev("U056", "they meet October 9th")])])
    return {"ExtractionRecord": [x], "Assessment": [a], "RecapEmail": [recap], "InternalSummary": [summary],
            "MutualActionPlan": [plan],
            "VerifierReport": [verdicts("assessment", "recap_email", "internal_summary", "mutual_action_plan")]}


SAMPLES = {"deal_a": deal_a, "deal_b": deal_b}


def build(deal: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        llm = LLMClient(mode="live", backend=SampleBackend(SAMPLES[deal]()), db_path=Path(tmp) / "s.sqlite3",
                        replay_dir=Path(tmp) / "rp", redact=lambda s: s)
        result = asyncio.run(Chain(llm).run(load_context(deal)))
    payload = result.to_dict()
    payload.update({"source": "sample", "sample_label": SAMPLE_LABEL, "cost_usd": None, "latency_ms": None})
    failing = [c for c in payload["checks"] if not c["passed"]]
    if failing or payload["errors"]:
        raise SystemExit(f"{deal} sample fails its own checks: {failing or payload['errors']}")
    return payload


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for deal in SAMPLES:
        (OUT / f"{deal}.json").write_text(json.dumps(build(deal), indent=1) + "\n", encoding="utf-8")
        print(f"wrote fixtures/samples/{deal}.json")
