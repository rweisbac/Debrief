"""Scripted fake backend and hand-built outputs for offline tests.

These objects are test fixtures written by hand. They are never shown in the app and never
presented as model output. Evidence excerpts are real lines from data/transcripts/deal_a.txt.
"""
from __future__ import annotations

from collections import defaultdict, deque

from pydantic import BaseModel

from src import schemas as S


def ev(uid: str, excerpt: str) -> S.EvidenceRef:
    return S.EvidenceRef(utterance_id=uid, excerpt=excerpt)


def raw_body(obj: BaseModel | str | None, stop: str = "end_turn", usage: dict | None = None,
             stop_details: dict | None = None) -> dict:
    text = obj.model_dump_json() if isinstance(obj, BaseModel) else (obj or "")
    content = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    if text:
        content.append({"type": "text", "text": text})
    return {"id": "msg_fake", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": content, "stop_reason": stop, "stop_sequence": None, "stop_details": stop_details,
            "usage": usage or {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 3000,
                               "cache_creation_input_tokens": 0}}


class FakeBackend:
    """Returns queued raw bodies per output model name. Records every request it receives."""

    def __init__(self):
        self.queues: dict[str, deque] = defaultdict(deque)
        self.requests: list[tuple[str, dict]] = []

    def queue(self, model_name: str, *bodies: dict) -> "FakeBackend":
        self.queues[model_name].extend(bodies)
        return self

    async def send(self, request: dict, output_model: type[BaseModel]):
        self.requests.append((output_model.__name__, request))
        q = self.queues[output_model.__name__]
        if not q:
            raise AssertionError(f"no scripted response left for {output_model.__name__}")
        raw = q.popleft()
        text = "".join(b.get("text", "") for b in raw["content"] if b["type"] == "text")
        try:
            return raw, output_model.model_validate_json(text), ""
        except Exception as e:  # mirrors messages.parse raising on bad JSON
            return raw, None, str(e)

    def count(self, model_name: str) -> int:
        return sum(1 for name, _ in self.requests if name == model_name)


def extraction_a() -> S.ExtractionRecord:
    return S.ExtractionRecord(
        business_outcome=S.BusinessOutcome(stated=True, summary="Catch late loads while dispatch can still reroute",
                                           evidence=[ev("U035", "dispatch can swap drivers or call the consignee")]),
        agreed_next_step=S.AgreedNextStep(exists=True, summary="45 minute session with Elena Varga", date="2026-10-08",
                                          evidence=[ev("U072", "Thursday October 8th, 2pm Central, forty five minutes")]),
        objections=[S.Objection(summary="Hourly sync too slow for dispatch", raised_by="Grace Oyelaran",
                                status="resolved", answer_given="Continuous sync since the August release",
                                evidence=[ev("U009", "Hourly might be tight for us")])],
        open_technical_items=[S.OpenItem(summary="Row level policy for partner hierarchy", owner="Priya Raman",
                                         evidence=[ev("U052", "What I don't know yet is how your partner hierarchy works")])],
        integration_patterns=[S.IntegrationPattern(summary="Existing dbt models run as is",
                                                   evidence=[ev("U025", "No rewrite")])],
        commitments=[S.Commitment(who="Priya Raman", side="apex", what="Build partner hierarchy policy",
                                  by_when="2026-10-06",
                                  evidence=[ev("U054", "I can have that back to you by Tuesday the sixth")])],
        stakeholders=[
            S.Stakeholder(name="Dana Ortiz", title="VP Data", present=True, why_they_matter="champion",
                          evidence=[ev("U060", "I think I've seen what I needed to see")]),
            S.Stakeholder(name="Elena Varga", title="COO", present=False, why_they_matter="owns the budget line",
                          evidence=[ev("U066", "she owns the budget line for this")])],
        competitor_mentions=[],
        buying_signals=[S.Signal(summary="Dana called it the most useful session", strength="moderate", qualifier="",
                                 evidence=[ev("U080", "the most useful vendor session")])],
        risk_signals=[],
        exact_numbers=[S.ExactNumber(value="4.7 billion events a month", what_it_measures="monthly events",
                                     evidence=[ev("U013", "4.7 billion events a month")]),
                       S.ExactNumber(value="38,000 per second", what_it_measures="holiday peak",
                                     evidence=[ev("U013", "peaks around 38,000 per second")])],
        customer_dependencies=[], contradictions=[],
        corrections=[S.Correction(original_statement="hourly batches", corrected_statement="continuous sync",
                                  evidence=[ev("U038", "The warehouse connector does continuous sync now")])],
        checklist_mismatches=[])


def step(action: str, owner: str, due: str, rule: str, kind: str, uid: str, excerpt: str, card: str = "",
         why: str = "Easy to skip because it is not on the default checklist.") -> S.NextStep:
    return S.NextStep(action=action, owner=owner, due_by=due, playbook_rule_id=rule, release_card_id=card,
                      action_type=kind, why=why, evidence=[ev(uid, excerpt)])


def assessment_a(steps: list[S.NextStep] | None = None, state: str = "ready_to_advance") -> S.Assessment:
    if steps is None:
        steps = [
            step("Send Elena a one page brief on late load detection and onboarding before Thursday", "Sam Lee",
                 "2026-10-05", "PB-03", "send_material", "U076", "She is going to ask about time to value"),
            step("Priya delivers the partner hierarchy policy built from Mikkel's sample", "Priya Raman",
                 "2026-10-06", "PB-04", "route_to_sc", "U054", "I can have that back to you by Tuesday the sixth",
                 card="RC-07"),
        ]
    return S.Assessment(deal_state=state, deal_state_why="Champion clear, economic buyer meeting booked.",
                        next_steps=steps, watch_items=[])


def recap_a(body: str | None = None) -> S.RecapEmail:
    body = body or (
        "Hi Dana,\n\nThanks for the time today. We ran the sandbox at your volume of 4.7 billion events a month "
        "and above your peak of 38,000 per second. Your dbt models ran as is, and the warehouse connector now "
        "uses continuous sync. Priya will build the partner hierarchy policy from Mikkel's sample by October 6. "
        "We are set for Thursday October 8 at 2pm Central with Elena, focused on catching late loads while "
        "dispatch can still reroute.\n\nSam")
    return S.RecapEmail(subject="Recap: late load detection validation", body=body,
                        customer_value_line="Fresh data means dispatch can act on a late load while it can still be saved.",
                        evidence=[ev("U013", "4.7 billion events a month")])


def summary_a() -> S.InternalSummary:
    return S.InternalSummary(
        deal_state_line="Ready to advance: champion clear, COO session booked",
        customer_value_line="Catch late loads while dispatch can still reroute.",
        what_we_validated=["Ingest at peak volume", "Existing dbt models", "Late load detection"],
        integration_patterns=["dbt models run as is"], objections_and_answers=["Hourly sync: continuous sync now, resolved"],
        open_items=["Partner hierarchy policy, Priya Raman"], commitments=["Priya Raman: partner policy by 2026-10-06"],
        stakeholders=["Dana Ortiz, champion, present", "Elena Varga, COO, absent"], competitive_notes=[], risks=[],
        evidence=[ev("U066", "she owns the budget line for this")])


def map_a() -> S.MutualActionPlan:
    return S.MutualActionPlan(customer_value_line="Catch late loads while dispatch can still reroute.", rows=[
        S.MapRow(milestone="Partner hierarchy sample", customer_owner="Mikkel Strand", apex_owner="",
                 target_date="2026-10-05", status="agreed", evidence=[ev("U055", "I can send that Monday")]),
        S.MapRow(milestone="Session with Elena Varga", customer_owner="Dana Ortiz", apex_owner="Sam Lee",
                 target_date="2026-10-08", status="agreed",
                 evidence=[ev("U072", "Thursday October 8th, 2pm Central, forty five minutes")]),
        S.MapRow(milestone="Commercial proposal", customer_owner="", apex_owner="Sam Lee", target_date="",
                 status="proposed", evidence=[])])


def clean_report() -> S.VerifierReport:
    return S.VerifierReport(verdicts=[
        S.VerifierVerdict(check="quote_supports_claim", artifact="recap_email", target="whole email", passed=True,
                          severity="low", finding="Quotes support claims.", utterance_ids=["U013"])])


def failing_report(artifact: str = "recap_email") -> S.VerifierReport:
    return S.VerifierReport(verdicts=[
        S.VerifierVerdict(check="email_promises_uncommitted", artifact=artifact,
                          target="We will have nested claims ready next week", passed=False, severity="high",
                          finding="Nobody committed to this.", utterance_ids=["U054"])])


def scripted_clean_run(fb: FakeBackend) -> FakeBackend:
    return (fb.queue("ExtractionRecord", raw_body(extraction_a()))
              .queue("Assessment", raw_body(assessment_a()))
              .queue("RecapEmail", raw_body(recap_a()))
              .queue("InternalSummary", raw_body(summary_a()))
              .queue("MutualActionPlan", raw_body(map_a()))
              .queue("VerifierReport", raw_body(clean_report())))
