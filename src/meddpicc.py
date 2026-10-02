"""MEDDPICC view computed in code from the extraction record and CRM. No model call.

Mapping rules (kept simple so a rep can see why a field is known or not):
- metrics: known when a business outcome was stated in the call and a number was said; partial with one.
- economic_buyer: known when someone in the call was described as signing or owning budget and the CRM
  names the same person; partial when only one source has them; unknown otherwise.
- decision_criteria: known with 2 or more resolved objections or agreed integration patterns; partial with 1.
- decision_process: known when the call produced an agreed next step or a dated customer dependency;
  partial when either the call or CRM describes the process; unknown otherwise.
- paper_process: partial when security, legal, procurement or contract steps came up; known if one has a date.
- pain: known when the customer stated the outcome in the call; partial from risk signals or CRM pains.
- champion: known when the CRM champion was present in the call; partial when named but absent.
- competition: known when a competitor was named in the call; partial when only the CRM lists one.
"""
from __future__ import annotations

import re

from src.schemas import EvidenceRef, ExtractionRecord, MeddpiccField, MeddpiccView

UNKNOWN_LABEL = "Unknown after TV demo"
EB_RE = re.compile(r"\b(sign|signs|budget|approv|economic buyer|cfo|coo|ceo|vp)\w*", re.I)
PAPER_RE = re.compile(r"\b(security|legal|procurement|contract|questionnaire|dpa|baa|soc 2|memo|vendor review)\b", re.I)


def _f(status: str, summary: str, evidence: list[EvidenceRef] | None = None) -> MeddpiccField:
    return MeddpiccField(status=status, summary=summary if status != "unknown" else UNKNOWN_LABEL,
                         evidence=(evidence or [])[:2])


def compute(x: ExtractionRecord, crm: dict) -> MeddpiccView:
    # metrics
    if x.business_outcome.stated and x.exact_numbers:
        metrics = _f("known", f"{x.business_outcome.summary} Numbers said: " +
                     ", ".join(n.value for n in x.exact_numbers[:3]), x.business_outcome.evidence)
    elif x.business_outcome.stated or x.exact_numbers:
        ev = x.business_outcome.evidence or x.exact_numbers[0].evidence
        metrics = _f("partial", x.business_outcome.summary or "Numbers said, no stated outcome", ev)
    else:
        metrics = _f("unknown", "")

    # economic buyer
    crm_eb = crm.get("economic_buyer", "")
    in_call = [s for s in x.stakeholders if EB_RE.search(s.why_they_matter + " " + s.title)
               and not re.search(r"\b(security|engineer|analyst)\b", s.title, re.I)]
    named = [s for s in in_call if crm_eb and (s.name in crm_eb or crm_eb in s.name)]
    if named:
        economic_buyer = _f("known", f"{named[0].name}, {named[0].why_they_matter}", named[0].evidence)
    elif in_call:
        economic_buyer = _f("partial", f"{in_call[0].name}: {in_call[0].why_they_matter}", in_call[0].evidence)
    elif crm_eb:
        economic_buyer = _f("partial", f"{crm_eb} (CRM only, not discussed in the call)")
    else:
        economic_buyer = _f("unknown", "")

    # decision criteria
    resolved = [o for o in x.objections if o.status.value == "resolved"]
    crit = len(resolved) + len(x.integration_patterns)
    crit_ev = [e for o in resolved for e in o.evidence] + [e for p in x.integration_patterns for e in p.evidence]
    if crit >= 2:
        decision_criteria = _f("known", f"{crit} items validated or agreed", crit_ev)
    elif crit == 1:
        decision_criteria = _f("partial", "1 item validated or agreed", crit_ev)
    else:
        decision_criteria = _f("unknown", "")

    # decision process
    dated_dep = [d for d in x.customer_dependencies if d.due]
    crm_dp = (crm.get("discovery_notes") or {}).get("decision_process", "")
    crm_dp_real = bool(crm_dp) and not crm_dp.lower().startswith("not ")
    if x.agreed_next_step.exists or dated_dep:
        ev = x.agreed_next_step.evidence if x.agreed_next_step.exists else dated_dep[0].evidence
        summary = x.agreed_next_step.summary if x.agreed_next_step.exists else dated_dep[0].summary
        decision_process = _f("known", summary, ev)
    elif x.customer_dependencies or crm_dp_real:
        ev = x.customer_dependencies[0].evidence if x.customer_dependencies else []
        decision_process = _f("partial", x.customer_dependencies[0].summary if x.customer_dependencies
                              else f"{crm_dp} (CRM only)", ev)
    else:
        decision_process = _f("unknown", "")

    # paper process
    paper = [d for d in x.customer_dependencies if PAPER_RE.search(d.summary)]
    paper_objs = [o for o in x.objections if PAPER_RE.search(o.summary)]
    if any(d.due for d in paper):
        d = next(d for d in paper if d.due)
        paper_process = _f("known", f"{d.summary} (due {d.due})", d.evidence)
    elif paper or paper_objs:
        item = paper[0] if paper else paper_objs[0]
        paper_process = _f("partial", item.summary, item.evidence)
    else:
        paper_process = _f("unknown", "")

    # pain
    crm_pains = (crm.get("discovery_notes") or {}).get("pains", [])
    if x.business_outcome.stated:
        pain = _f("known", x.business_outcome.summary, x.business_outcome.evidence)
    elif x.risk_signals or crm_pains:
        pain = _f("partial", x.risk_signals[0].summary if x.risk_signals else f"{crm_pains[0]} (CRM only)",
                  x.risk_signals[0].evidence if x.risk_signals else [])
    else:
        pain = _f("unknown", "")

    # champion
    crm_champ = crm.get("champion", "")
    present = [s for s in x.stakeholders if crm_champ and s.name == crm_champ and s.present]
    if present:
        champion = _f("known", f"{crm_champ}, present in the call", present[0].evidence)
    elif crm_champ:
        champion = _f("partial", f"{crm_champ} (CRM), not confirmed in the call")
    else:
        champion = _f("unknown", "")

    # competition
    if x.competitor_mentions:
        names = sorted({c.competitor for c in x.competitor_mentions})
        competition = _f("known", ", ".join(names), x.competitor_mentions[0].evidence)
    elif crm.get("competitors"):
        competition = _f("partial", ", ".join(crm["competitors"]) + " (CRM only)")
    else:
        competition = _f("unknown", "")

    return MeddpiccView(metrics=metrics, economic_buyer=economic_buyer, decision_criteria=decision_criteria,
                        decision_process=decision_process, paper_process=paper_process, pain=pain,
                        champion=champion, competition=competition)


def gaps(view: MeddpiccView) -> list[str]:
    return [name for name in type(view).model_fields if getattr(view, name).status.value == "unknown"]
