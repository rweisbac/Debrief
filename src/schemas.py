"""Pydantic models for every structured step, plus code-side validators.

Rules for these models (they are sent to the model as output schemas):
- every field is required; use empty lists or empty strings, never Optional or unions
- no field named "reasoning"; short justifications go in "why" (max 25 words)
- enum values are compared case-insensitively after parsing
- caps and word limits are enforced by the validators below, not by schema constraints,
  so a violation becomes a retry with feedback instead of a parse crash
"""
from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

MAX_STEPS = 3
MAX_WHY_WORDS = 25
MAX_EXCERPT_WORDS = 30
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _lower(v):
    return v.strip().lower() if isinstance(v, str) else v


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Enums. Each is wrapped in a lowercasing validator so "Open" and "open" both parse.

class DealStateEnum(str, Enum):
    ready_to_advance = "ready_to_advance"
    open_technical_gap = "open_technical_gap"
    missing_stakeholder = "missing_stakeholder"
    competitive_risk = "competitive_risk"
    waiting_on_customer = "waiting_on_customer"
    low_information = "low_information"


class ObjectionStatusEnum(str, Enum):
    resolved = "resolved"
    partially_resolved = "partially_resolved"
    open = "open"


class SideEnum(str, Enum):
    apex = "apex"
    customer = "customer"


class StrengthEnum(str, Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"


class ChecklistFieldEnum(str, Enum):
    dated_next_step = "dated_next_step"
    stakeholder_to_add = "stakeholder_to_add"
    business_outcome = "business_outcome"
    sc_commitment = "sc_commitment"


class ActionTypeEnum(str, Enum):
    send_recap = "send_recap"
    book_meeting = "book_meeting"
    send_material = "send_material"
    route_to_sc = "route_to_sc"
    reach_stakeholder = "reach_stakeholder"
    support_customer_process = "support_customer_process"
    flag_deal_desk = "flag_deal_desk"
    resolve_with_champion = "resolve_with_champion"
    other = "other"


class MapStatusEnum(str, Enum):
    proposed = "proposed"
    agreed = "agreed"


class VerifierCheckEnum(str, Enum):
    quote_supports_claim = "quote_supports_claim"
    commitment_overstated = "commitment_overstated"
    buying_signal_overstated = "buying_signal_overstated"
    email_promises_uncommitted = "email_promises_uncommitted"
    superseded_feature_as_current = "superseded_feature_as_current"
    generic_step = "generic_step"


class ArtifactEnum(str, Enum):
    assessment = "assessment"
    recap_email = "recap_email"
    internal_summary = "internal_summary"
    mutual_action_plan = "mutual_action_plan"


class SeverityEnum(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


DealState = Annotated[DealStateEnum, BeforeValidator(_lower)]
ObjectionStatus = Annotated[ObjectionStatusEnum, BeforeValidator(_lower)]
Side = Annotated[SideEnum, BeforeValidator(_lower)]
Strength = Annotated[StrengthEnum, BeforeValidator(_lower)]
ChecklistField = Annotated[ChecklistFieldEnum, BeforeValidator(_lower)]
ActionType = Annotated[ActionTypeEnum, BeforeValidator(_lower)]
MapStatus = Annotated[MapStatusEnum, BeforeValidator(_lower)]
VerifierCheck = Annotated[VerifierCheckEnum, BeforeValidator(_lower)]
Artifact = Annotated[ArtifactEnum, BeforeValidator(_lower)]
Severity = Annotated[SeverityEnum, BeforeValidator(_lower)]


# Evidence

class EvidenceRef(_Model):
    utterance_id: str
    excerpt: str


# Stage A: extract

class Objection(_Model):
    summary: str
    raised_by: str
    status: ObjectionStatus
    answer_given: str
    evidence: list[EvidenceRef]


class OpenItem(_Model):
    summary: str
    owner: str
    evidence: list[EvidenceRef]


class IntegrationPattern(_Model):
    summary: str
    evidence: list[EvidenceRef]


class Commitment(_Model):
    who: str
    side: Side
    what: str
    by_when: str  # ISO date or empty string
    evidence: list[EvidenceRef]


class Stakeholder(_Model):
    name: str
    title: str
    present: bool
    why_they_matter: str
    evidence: list[EvidenceRef]


class CompetitorMention(_Model):
    competitor: str
    context: str
    evidence: list[EvidenceRef]


class Signal(_Model):
    summary: str
    strength: Strength
    qualifier: str  # what limits the signal, or empty string
    evidence: list[EvidenceRef]


class ExactNumber(_Model):
    value: str  # copied verbatim from the utterance
    what_it_measures: str
    evidence: list[EvidenceRef]


class BusinessOutcome(_Model):
    stated: bool
    summary: str
    evidence: list[EvidenceRef]


class AgreedNextStep(_Model):
    exists: bool
    summary: str
    date: str  # ISO date or empty string
    evidence: list[EvidenceRef]


class CustomerDependency(_Model):
    summary: str
    owner: str
    due: str  # ISO date or empty string
    blocks_progress: bool  # true when Apex cannot move the deal forward until this is done
    evidence: list[EvidenceRef]


class Contradiction(_Model):
    summary: str
    evidence: list[EvidenceRef]


class Correction(_Model):
    original_statement: str
    corrected_statement: str
    evidence: list[EvidenceRef]


class ChecklistMismatch(_Model):
    field: ChecklistField
    logged_value: str
    transcript_says: str
    evidence: list[EvidenceRef]


class ExtractionRecord(_Model):
    business_outcome: BusinessOutcome
    agreed_next_step: AgreedNextStep
    objections: list[Objection]
    open_technical_items: list[OpenItem]
    integration_patterns: list[IntegrationPattern]
    commitments: list[Commitment]
    stakeholders: list[Stakeholder]
    competitor_mentions: list[CompetitorMention]
    buying_signals: list[Signal]
    risk_signals: list[Signal]
    exact_numbers: list[ExactNumber]
    customer_dependencies: list[CustomerDependency]
    contradictions: list[Contradiction]
    corrections: list[Correction]
    checklist_mismatches: list[ChecklistMismatch]


# Stage B: assess and recommend

class NextStep(_Model):
    action: str
    owner: str
    due_by: str  # ISO date or empty string
    playbook_rule_id: str
    release_card_id: str  # empty string when none applies
    action_type: ActionType
    why: str  # why a typical AE might not do this unprompted, max 25 words
    evidence: list[EvidenceRef]


class WatchItem(_Model):
    summary: str
    competitor: str
    release_card_id: str
    evidence: list[EvidenceRef]


class Assessment(_Model):
    deal_state: DealState
    deal_state_why: str
    next_steps: list[NextStep]  # at most 3, ranked, first is most important
    watch_items: list[WatchItem]


# Stage C: drafts

class RecapEmail(_Model):
    subject: str
    body: str
    customer_value_line: str  # ties the technical outcome to the customer's stated outcome, or "not stated"
    evidence: list[EvidenceRef]


class InternalSummary(_Model):
    deal_state_line: str
    customer_value_line: str
    what_we_validated: list[str]
    integration_patterns: list[str]
    objections_and_answers: list[str]
    open_items: list[str]
    commitments: list[str]
    stakeholders: list[str]
    competitive_notes: list[str]
    risks: list[str]
    evidence: list[EvidenceRef]


class MapRow(_Model):
    milestone: str
    customer_owner: str
    apex_owner: str
    target_date: str  # ISO date or empty string
    status: MapStatus
    evidence: list[EvidenceRef]


class MutualActionPlan(_Model):
    customer_value_line: str
    rows: list[MapRow]


# Stage D: verify

class VerifierVerdict(_Model):
    check: VerifierCheck
    artifact: Artifact
    target: str  # the step text or the sentence being judged
    passed: bool
    severity: Severity
    finding: str
    utterance_ids: list[str]


class VerifierReport(_Model):
    verdicts: list[VerifierVerdict]


class JudgeResult(_Model):
    specific: bool
    evidence_tied: bool
    playbook_tied: bool
    actionable_10_min: bool
    non_obvious: bool
    critique: str


# Computed in code (no model call)

class MeddpiccStatusEnum(str, Enum):
    known = "known"
    partial = "partial"
    unknown = "unknown"


class MeddpiccField(_Model):
    status: Annotated[MeddpiccStatusEnum, BeforeValidator(_lower)]
    summary: str
    evidence: list[EvidenceRef]


class MeddpiccView(_Model):
    metrics: MeddpiccField
    economic_buyer: MeddpiccField
    decision_criteria: MeddpiccField
    decision_process: MeddpiccField
    paper_process: MeddpiccField
    pain: MeddpiccField
    champion: MeddpiccField
    competition: MeddpiccField


LLM_OUTPUT_MODELS = [ExtractionRecord, Assessment, RecapEmail, InternalSummary, MutualActionPlan, VerifierReport,
                     JudgeResult]


# Validators. Each returns a list of human readable errors; empty means valid.

def _words(text: str) -> int:
    return len(text.split())


def is_iso_date_or_empty(value: str) -> bool:
    if value == "":
        return True
    if not _ISO_DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _iter_evidence(obj) -> list[EvidenceRef]:
    found: list[EvidenceRef] = []
    if isinstance(obj, EvidenceRef):
        return [obj]
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            found.extend(_iter_evidence(getattr(obj, name)))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_iter_evidence(item))
    return found


def validate_evidence_excerpts(obj: BaseModel) -> list[str]:
    errors = []
    for ref in _iter_evidence(obj):
        if _words(ref.excerpt) > MAX_EXCERPT_WORDS:
            errors.append(f"excerpt for {ref.utterance_id} has {_words(ref.excerpt)} words, max {MAX_EXCERPT_WORDS}")
    return errors


def validate_extraction(rec: ExtractionRecord) -> list[str]:
    errors = validate_evidence_excerpts(rec)
    for c in rec.commitments:
        if not is_iso_date_or_empty(c.by_when):
            errors.append(f"commitment {c.what!r}: by_when {c.by_when!r} is not an ISO date or empty")
    for d in rec.customer_dependencies:
        if not is_iso_date_or_empty(d.due):
            errors.append(f"dependency {d.summary!r}: due {d.due!r} is not an ISO date or empty")
    if not is_iso_date_or_empty(rec.agreed_next_step.date):
        errors.append(f"agreed_next_step.date {rec.agreed_next_step.date!r} is not an ISO date or empty")
    if rec.agreed_next_step.exists and not rec.agreed_next_step.evidence:
        errors.append("agreed_next_step.exists is true but has no evidence")
    if rec.business_outcome.stated and not rec.business_outcome.evidence:
        errors.append("business_outcome.stated is true but has no evidence")
    return errors


def validate_assessment(a: Assessment) -> list[str]:
    errors = validate_evidence_excerpts(a)
    if len(a.next_steps) > MAX_STEPS:
        errors.append(f"{len(a.next_steps)} next steps, max {MAX_STEPS}. Keep only the most important; never pad.")
    if _words(a.deal_state_why) > MAX_WHY_WORDS:
        errors.append(f"deal_state_why has {_words(a.deal_state_why)} words, max {MAX_WHY_WORDS}")
    for i, s in enumerate(a.next_steps, 1):
        if _words(s.why) > MAX_WHY_WORDS:
            errors.append(f"step {i} why has {_words(s.why)} words, max {MAX_WHY_WORDS}")
        if not s.evidence:
            errors.append(f"step {i} has no evidence")
        if not s.playbook_rule_id.strip():
            errors.append(f"step {i} has no playbook_rule_id")
        if not s.owner.strip():
            errors.append(f"step {i} has no owner")
        if not is_iso_date_or_empty(s.due_by):
            errors.append(f"step {i} due_by {s.due_by!r} is not an ISO date or empty")
    return errors


def validate_map(m: MutualActionPlan) -> list[str]:
    errors = validate_evidence_excerpts(m)
    for i, r in enumerate(m.rows, 1):
        if r.status == MapStatusEnum.agreed and not r.evidence:
            errors.append(f"MAP row {i} is marked agreed without evidence")
        if not is_iso_date_or_empty(r.target_date):
            errors.append(f"MAP row {i} target_date {r.target_date!r} is not an ISO date or empty")
    return errors
