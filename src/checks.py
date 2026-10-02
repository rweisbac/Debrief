"""Deterministic verifier checks (stage D, part 1). No model calls.

Each check returns a CheckResult per artifact. High severity failures trigger one regeneration
of that artifact; if it still fails, the artifact is marked needs review.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from pydantic import BaseModel

from src.rules import is_chase
from src.schemas import (Assessment, DealStateEnum, EvidenceRef, ExtractionRecord, InternalSummary,
                         MapStatusEnum, MutualActionPlan, RecapEmail)
from src.transcript import Transcript

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTH_DAY_RE = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) +
                          r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUMBER_RE = re.compile(r"(?<![\w.])\$?(\d+(?:[.,]\d+)*)\s*([kKmM])?(?![\w])")
NAME_PAIR_RE = re.compile(r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?) ([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b")
GREETING_RE = re.compile(r"\b(?:Hi|Hello|Dear|Thanks|Thank you),? ([A-Z][a-z]+)\b")
NOT_NAMES = {"Apex", "Thanks", "Best", "Regards", "Hi", "Hello", "Dear", "Team", "Monday", "Tuesday",
             "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "The", "This", "Next", "Our", "Your",
             "We", "If", "And", "For", "With", "Central", "Eastern", "Pacific", "Mutual", "Action", "Plan",
             "Security", "Review", "Recap", "Customer", "Open", "Items", "Next Steps", "Phase", "Kind"}


@dataclass
class CheckResult:
    check: str
    artifact: str
    passed: bool
    severity: str
    detail: str
    locations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ID and date fields are checked elsewhere; scanning them for numbers would read PB-03 as "03".
SKIP_FIELDS = {"playbook_rule_id", "release_card_id", "utterance_ids", "due_by", "target_date", "date", "by_when",
               "due", "action_type", "status", "deal_state", "check", "artifact", "severity"}


def _strings(obj) -> list[str]:
    """All free text in a model, excluding evidence excerpts (checked against the transcript) and ID fields."""
    out: list[str] = []
    if isinstance(obj, EvidenceRef):
        return out
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            if name in SKIP_FIELDS:
                continue
            out.extend(_strings(getattr(obj, name)))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_strings(item))
    elif isinstance(obj, str):
        out.append(obj)
    return out


def _evidence(obj) -> list[EvidenceRef]:
    if isinstance(obj, EvidenceRef):
        return [obj]
    out: list[EvidenceRef] = []
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            out.extend(_evidence(getattr(obj, name)))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_evidence(item))
    return out


def source_corpus(transcript: Transcript, crm: dict) -> str:
    return transcript.full_text() + "\n" + json.dumps(crm, ensure_ascii=False)


def _norm_number(raw: str, suffix: str | None) -> set[str]:
    base = raw.replace(",", "")
    forms = {base}
    if suffix:
        mult = 1000 if suffix.lower() == "k" else 1_000_000
        try:
            forms.add(str(int(float(base) * mult)))
        except ValueError:
            pass
        forms.add(base + suffix.lower())
    return forms


def _numbers_in(text: str) -> list[tuple[str, set[str]]]:
    text = ISO_RE.sub(" ", text)
    text = MONTH_DAY_RE.sub(" ", text)
    return [(m.group(0).strip(), _norm_number(m.group(1), m.group(2))) for m in NUMBER_RE.finditer(text)]


def _source_numbers(corpus: str) -> set[str]:
    found: set[str] = set()
    for _, forms in _numbers_in(corpus):
        found |= forms
    return found


def check_evidence(artifact: str, obj: BaseModel, transcript: Transcript) -> CheckResult:
    bad = []
    for ref in _evidence(obj):
        ok, reason = transcript.resolve_evidence(ref.utterance_id, ref.excerpt)
        if not ok:
            bad.append(f"{ref.utterance_id}: {reason}")
    return CheckResult("evidence_resolves", artifact, not bad, "high",
                       "all evidence matches the transcript" if not bad else f"{len(bad)} evidence refs do not match",
                       bad)


def check_numbers(artifact: str, obj: BaseModel, corpus: str) -> CheckResult:
    allowed = _source_numbers(corpus)
    bad = []
    for text in _strings(obj):
        for shown, forms in _numbers_in(text):
            if not forms & allowed:
                bad.append(shown)
    return CheckResult("numbers_in_source", artifact, not bad, "high",
                       "every number appears in the transcript or CRM" if not bad
                       else "numbers not found in transcript or CRM: " + ", ".join(sorted(set(bad))), sorted(set(bad)))


def _dates_in(text: str, year: int) -> list[tuple[str, date | None]]:
    out = []
    for m in ISO_RE.finditer(text):
        try:
            out.append((m.group(0), date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            out.append((m.group(0), None))
    for m in MONTH_DAY_RE.finditer(text):
        month = MONTHS[m.group(1).lower()]
        try:
            out.append((m.group(0), date(year, month, int(m.group(2)))))
        except ValueError:
            out.append((m.group(0), None))
    return out


DATE_FIELDS = {"due_by", "target_date", "date", "by_when", "due"}


def _date_field_values(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, BaseModel) and not isinstance(obj, EvidenceRef):
        for name in type(obj).model_fields:
            value = getattr(obj, name)
            if name in DATE_FIELDS and isinstance(value, str) and value:
                out.append(value)
            else:
                out.extend(_date_field_values(value))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_date_field_values(item))
    return out


def check_dates(artifact: str, obj: BaseModel, as_of: date, strictly_after: bool) -> CheckResult:
    bad = []
    for text in _strings(obj) + _date_field_values(obj):
        for shown, d in _dates_in(text, as_of.year):
            if d is None:
                bad.append(f"{shown} (not a real date)")
            elif d.weekday() >= 5:
                bad.append(f"{shown} (weekend)")
            elif d < as_of or (strictly_after and d == as_of):
                bad.append(f"{shown} (not after {as_of.isoformat()})")
    return CheckResult("dates_future_business_days", artifact, not bad, "medium",
                       "dates are future business days" if not bad else "bad dates: " + ", ".join(bad), bad)


def known_people(transcript: Transcript, crm: dict) -> set[str]:
    names = {p.name for p in transcript.participants}
    names |= {c["name"] for c in crm.get("contacts", [])}
    names |= {crm.get("owner_ae", ""), crm.get("sc", "")}
    tokens = set()
    for n in names:
        tokens |= set(n.split())
    return tokens


def check_names(artifact: str, obj: BaseModel, transcript: Transcript, crm: dict) -> CheckResult:
    """Heuristic: a capitalized word pair or a greeting name must appear in the transcript, CRM or roster."""
    corpus_words = set(re.findall(r"[a-z]+", source_corpus(transcript, crm).lower()))
    roster = known_people(transcript, crm)
    bad = []
    for text in _strings(obj):
        candidates = [m.group(0) for m in NAME_PAIR_RE.finditer(text)] + [m.group(1) for m in GREETING_RE.finditer(text)]
        for cand in candidates:
            words = [w for w in cand.split() if w not in NOT_NAMES]
            if not words:
                continue
            # A word passes if it is a known person token or appears anywhere in the source text,
            # so sentence-initial verbs like "Send" pass. Invented names that are also common
            # English words can slip through; this check is a heuristic.
            if all(w in roster or w.lower() in corpus_words for w in words):
                continue
            bad.append(cand)
    return CheckResult("names_known", artifact, not bad, "high",
                       "every named person appears in the transcript or CRM (heuristic)" if not bad
                       else "names not found in transcript or CRM: " + ", ".join(sorted(set(bad))), sorted(set(bad)))


def check_step_cap(a: Assessment) -> CheckResult:
    n = len(a.next_steps)
    return CheckResult("max_three_steps", "assessment", n <= 3, "high", f"{n} steps")


def check_no_chase(a: Assessment) -> CheckResult:
    if a.deal_state != DealStateEnum.waiting_on_customer:
        return CheckResult("no_chase_when_waiting", "assessment", True, "high", "deal is not waiting on customer")
    bad = [s.action for s in a.next_steps if is_chase(s.action, s.action_type.value)]
    return CheckResult("no_chase_when_waiting", "assessment", not bad, "high",
                       "no chase steps" if not bad else "chase steps on a waiting deal", bad)


def check_map_agreed(m: MutualActionPlan) -> CheckResult:
    bad = [r.milestone for r in m.rows if r.status == MapStatusEnum.agreed and not r.evidence]
    return CheckResult("map_agreed_has_evidence", "mutual_action_plan", not bad, "medium",
                       "agreed rows have evidence" if not bad else "agreed rows without evidence", bad)


def run_artifact(artifact: str, obj: BaseModel, transcript: Transcript, crm: dict, as_of: date) -> list[CheckResult]:
    corpus = source_corpus(transcript, crm)
    results = [check_evidence(artifact, obj, transcript), check_numbers(artifact, obj, corpus),
               check_dates(artifact, obj, as_of, strictly_after=(artifact == "assessment")),
               check_names(artifact, obj, transcript, crm)]
    if isinstance(obj, Assessment):
        results += [check_step_cap(obj), check_no_chase(obj)]
    if isinstance(obj, MutualActionPlan):
        results.append(check_map_agreed(obj))
    return results


def run_all(*, extraction: ExtractionRecord, assessment: Assessment, recap: RecapEmail | None,
            summary: InternalSummary | None, plan: MutualActionPlan | None, transcript: Transcript,
            crm: dict, as_of: date) -> list[CheckResult]:
    results = [check_evidence("extraction", extraction, transcript)]
    results += run_artifact("assessment", assessment, transcript, crm, as_of)
    for name, obj in (("recap_email", recap), ("internal_summary", summary), ("mutual_action_plan", plan)):
        if obj is not None:
            results += run_artifact(name, obj, transcript, crm, as_of)
    return results
