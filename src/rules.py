"""Deterministic overrides applied after the assess_and_recommend call.

Each rule returns Override entries so every change is logged and visible in the UI.
Order matters: drop invalid steps first, then set the deal state, then filter and cap.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from src import config
from src.prompts import playbook_rule_ids, release_card_ids
from src.schemas import (Assessment, DealStateEnum, ExtractionRecord, MapStatusEnum, MutualActionPlan,
                         ActionTypeEnum)
from src.transcript import Transcript

CHASE_RE = re.compile(
    r"\b(check(ing)?[ -]in|follow(ing)?[ -]up (on|about) (the )?(status|progress|review|decision)|nudge|"
    r"chase|chasing|ping|touch base|push(ing)? for|remind (them|the customer))\b", re.I)


@dataclass
class Override:
    rule_id: str
    target: str
    before: str
    after: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def is_chase(text: str, action_type: str) -> bool:
    return action_type == ActionTypeEnum.book_meeting.value or bool(CHASE_RE.search(text))


def apply(assessment: Assessment, extraction: ExtractionRecord, transcript: Transcript) -> tuple[Assessment, list[Override]]:
    a = assessment.model_copy(deep=True)
    overrides: list[Override] = []
    rules, cards = playbook_rule_ids(), release_card_ids()

    # R-RULEID: unknown playbook rule drops the step; unknown release card is blanked.
    kept = []
    for s in a.next_steps:
        if s.playbook_rule_id.strip().upper() not in rules:
            overrides.append(Override("R-RULEID", s.action, s.playbook_rule_id, "dropped",
                                      "step cites a playbook rule that does not exist"))
            continue
        if s.release_card_id and s.release_card_id.strip().upper() not in cards:
            overrides.append(Override("R-RULEID", s.action, s.release_card_id, "",
                                      "release card does not exist, removed"))
            s.release_card_id = ""
        kept.append(s)
    a.next_steps = kept

    # R-NOEVID: unresolvable evidence is removed; a step with no evidence left is dropped.
    kept = []
    for s in a.next_steps:
        good = [e for e in s.evidence if transcript.resolve_evidence(e.utterance_id, e.excerpt)[0]]
        if len(good) < len(s.evidence):
            overrides.append(Override("R-NOEVID", s.action, str(len(s.evidence)), str(len(good)),
                                      "removed evidence that does not match the transcript"))
        if not good:
            overrides.append(Override("R-NOEVID", s.action, "step", "dropped", "step has no valid evidence"))
            continue
        s.evidence = good
        kept.append(s)
    a.next_steps = kept

    # R-LOWINFO: too few substantive customer utterances.
    substantive = len(transcript.substantive_customer_utterances())
    if substantive < config.LOW_INFO_MIN_CUSTOMER_UTTERANCES:
        if a.deal_state != DealStateEnum.low_information:
            overrides.append(Override("R-LOWINFO", "deal_state", a.deal_state.value, "low_information",
                                      f"only {substantive} substantive customer utterances"))
            a.deal_state = DealStateEnum.low_information
        if len(a.next_steps) > config.LOW_INFO_MAX_STEPS:
            cut = a.next_steps[config.LOW_INFO_MAX_STEPS:]
            overrides.append(Override("R-LOWINFO", "next_steps", str(len(a.next_steps)),
                                      str(config.LOW_INFO_MAX_STEPS),
                                      "low information call, cut: " + "; ".join(s.action for s in cut)))
            a.next_steps = a.next_steps[:config.LOW_INFO_MAX_STEPS]

    # R-WAIT: a customer-owned blocker with no date means we wait and support.
    blockers = [d for d in extraction.customer_dependencies if d.blocks_progress and not d.due]
    if blockers and a.deal_state not in (DealStateEnum.waiting_on_customer, DealStateEnum.low_information):
        overrides.append(Override("R-WAIT", "deal_state", a.deal_state.value, "waiting_on_customer",
                                  f"customer dependency with no date: {blockers[0].summary}"))
        a.deal_state = DealStateEnum.waiting_on_customer

    # R-CHASE: no chasing while waiting on the customer.
    if a.deal_state == DealStateEnum.waiting_on_customer:
        kept = []
        for s in a.next_steps:
            if is_chase(s.action, s.action_type.value):
                overrides.append(Override("R-CHASE", s.action, "step", "dropped",
                                          "chase step on a waiting_on_customer deal"))
                continue
            kept.append(s)
        a.next_steps = kept

    # R-CAP: never more than 3.
    if len(a.next_steps) > 3:
        cut = a.next_steps[3:]
        overrides.append(Override("R-CAP", "next_steps", str(len(a.next_steps)), "3",
                                  "cut: " + "; ".join(s.action for s in cut)))
        a.next_steps = a.next_steps[:3]

    return a, overrides


def enforce_map_agreed(plan: MutualActionPlan, transcript: Transcript) -> tuple[MutualActionPlan, list[Override]]:
    """R-MAP: a row may be agreed only with evidence that resolves."""
    p = plan.model_copy(deep=True)
    overrides = []
    for row in p.rows:
        if row.status == MapStatusEnum.agreed:
            valid = [e for e in row.evidence if transcript.resolve_evidence(e.utterance_id, e.excerpt)[0]]
            if not valid:
                overrides.append(Override("R-MAP", row.milestone, "agreed", "proposed",
                                          "agreed row has no evidence that matches the transcript"))
                row.status = MapStatusEnum.proposed
    return p, overrides
