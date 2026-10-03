"""Deterministic verifier checks (stage D, part 1). No model calls.

Each check returns a CheckResult per artifact. High severity failures trigger one regeneration
of that artifact; if it still fails, the artifact is marked needs review.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

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


# Numbers. A draft number must (1) exist in the transcript or CRM and (2) not look swapped: if the
# words around it match a different number with the same unit better than any occurrence of the
# same number, it is probably a misquote (38,000 peak written as 40,000 because 40,000 was said
# elsewhere). Timestamps, phone numbers, IDs and dates are removed first so they cannot vouch for a
# number (stress gap G10: "47 billion" passed because of a CRM time 10:47:30).

NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
NUM_WORDS.update({w: (i + 2) * 10 for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})
MAGNITUDES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
SUFFIX_MULT = {"k": 1_000, "m": 1_000_000, "mm": 1_000_000, "bn": 1_000_000_000, "b": 1_000_000_000}
STOPWORDS = set("""a an the and or but of to in on at by for with from as is are was were be been it its this that
these those we you your our they their he she his her i me my us them there here so if then than about into over
under up out not no yes do does did have has had will would can could should just also very really around per
""".split())
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" +
                          "|".join(sorted({"january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december", "jan", "feb", "mar",
                                           "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"},
                                          key=len, reverse=True)) + r")\b", re.I)
NOISE_RES = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:[+-]\d{2}:\d{2}|Z)?)?"),  # ISO dates and datetimes
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"),                             # clock times
    re.compile(r"\+?\d{1,3}(?:[ -]\d{2,4}){2,4}\b"),                           # phone numbers
    re.compile(r"\b[A-Za-z]+[-_]?[A-Za-z]*-?\d+[\w-]*\b"),                     # ids like U014, PB-03, gong-a-0930
]
TOKEN_RE = re.compile(r"\$?\d+(?:[.,]\d+)*(?:bn|mm|[kKmMbB])?(?![\w])|[A-Za-z]+")


@dataclass
class NumberMention:
    shown: str
    value: float
    unit: str
    context: set[str]


def _stem(word: str) -> str:
    w = word.lower()
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _clean_for_numbers(text: str) -> str:
    text = MONTH_DAY_RE.sub(" DATE ", text)
    text = DAY_MONTH_RE.sub(" DATE ", text)
    for rx in NOISE_RES:
        text = rx.sub(" ", text)
    return text


def number_mentions(text: str, window: int = 6) -> list[NumberMention]:
    tokens = TOKEN_RE.findall(_clean_for_numbers(text))
    out: list[NumberMention] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        value, start = None, i
        if tok[0] == "$" or tok[0].isdigit():
            m = re.match(r"\$?(\d+(?:[.,]\d+)*)([a-zA-Z]*)$", tok)
            digits, suffix = m.group(1), m.group(2).lower()
            try:
                value = float(digits.replace(",", "")) if not re.search(r"\d,\d{1,2}$", digits) else float(digits.replace(",", "."))
            except ValueError:
                value = None
            if value is not None:
                value *= SUFFIX_MULT.get(suffix, 1)
                i += 1
        elif low in NUM_WORDS:
            total, current = 0, 0
            while i < len(tokens) and (tokens[i].lower() in NUM_WORDS or tokens[i].lower() in MAGNITUDES
                                       or tokens[i].lower() == "and" and i + 1 < len(tokens)
                                       and tokens[i + 1].lower() in NUM_WORDS):
                w = tokens[i].lower()
                if w in NUM_WORDS:
                    current += NUM_WORDS[w]
                elif w == "hundred":
                    current *= 100
                elif w in MAGNITUDES:
                    total += current * MAGNITUDES[w]
                    current = 0
                i += 1
            value = float(total + current)
        else:
            i += 1
            continue
        if value is None:
            continue
        while i < len(tokens) and tokens[i].lower() in MAGNITUDES:  # "4.7 billion"
            value *= MAGNITUDES[tokens[i].lower()]
            i += 1
        unit_tokens = [t.lower() for t in tokens[i:i + 2] if t[0].isalpha()]
        unit = " ".join(unit_tokens)
        before = tokens[max(0, start - window):start]
        after = tokens[i + len(unit_tokens):i + len(unit_tokens) + window]
        context = {_stem(t) for t in before + after if t[0].isalpha() and t.lower() not in STOPWORDS
                   and t.lower() not in MAGNITUDES and t.lower() not in NUM_WORDS}
        out.append(NumberMention(" ".join(tokens[start:i]), value, unit, context))
    return out


def _key(value: float) -> float:
    return float(f"{value:.6g}")


def _source_strings(transcript: Transcript, crm: dict) -> list[str]:
    out = [u.text for u in transcript.utterances]

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append(f"{k.replace('_', ' ')} {v}")
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            out.append(o)
    walk({k: v for k, v in crm.items() if not k.startswith("_")})
    return out


def check_evidence(artifact: str, obj: BaseModel, transcript: Transcript) -> CheckResult:
    bad = []
    for ref in _evidence(obj):
        ok, reason = transcript.resolve_evidence(ref.utterance_id, ref.excerpt)
        if not ok:
            bad.append(f"{ref.utterance_id}: {reason}")
    return CheckResult("evidence_resolves", artifact, not bad, "high",
                       "all evidence matches the transcript" if not bad else f"{len(bad)} evidence refs do not match",
                       bad)


def check_numbers(artifact: str, obj: BaseModel, transcript: Transcript, crm: dict) -> CheckResult:
    source = [m for text in _source_strings(transcript, crm) for m in number_mentions(text)]
    by_value: dict[float, list[NumberMention]] = {}
    for m in source:
        by_value.setdefault(_key(m.value), []).append(m)
    bad = []
    for text in _strings(obj):
        for m in number_mentions(text):
            same = by_value.get(_key(m.value))
            if not same:
                bad.append(f"{m.shown} (not in transcript or CRM)")
                continue
            if not m.unit:
                continue
            best_same = max(len(m.context & s.context) for s in same)
            rivals = [s for s in source if s.unit == m.unit and _key(s.value) != _key(m.value)]
            if rivals:
                best_rival = max(rivals, key=lambda s: len(m.context & s.context))
                if len(m.context & best_rival.context) > best_same:
                    bad.append(f"{m.shown} {m.unit} (the call says {best_rival.shown} {m.unit} in this context)")
    return CheckResult("numbers_in_source", artifact, not bad, "high",
                       "every number appears in the transcript or CRM in a matching context" if not bad
                       else "numbers not grounded: " + "; ".join(sorted(set(bad))), sorted(set(bad)))


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
    for m in DAY_MONTH_RE.finditer(text):
        month = MONTHS[m.group(2).lower()[:3] if m.group(2).lower() != "sept" else "sep"]
        try:
            out.append((m.group(0), date(year, month, int(m.group(1)))))
        except ValueError:
            out.append((m.group(0), None))
    return out


DATE_FIELDS = {"due_by", "target_date", "date", "by_when", "due"}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ORDINALS = {w: i for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth "
    "fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(), 1)}
ORDINALS.update({"twenty first": 21, "twenty second": 22, "twenty third": 23, "twenty fourth": 24,
                 "twenty fifth": 25, "twenty sixth": 26, "twenty seventh": 27, "twenty eighth": 28,
                 "twenty ninth": 29, "thirtieth": 30, "thirty first": 31})
WEEKDAY_ORDINAL_RE = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\s+the\s+(" +
                                "|".join(sorted(ORDINALS, key=len, reverse=True)) + r")\b", re.I)
WEEKDAY_RE = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b", re.I)
RELATIVE_RE = re.compile(r"\b(?:next|this|coming)\s+(?:" + "|".join(WEEKDAYS) + r"|week)\b", re.I)
# Drafts that must only repeat dates said in the call. Steps and MAP rows may propose new dates.
DATES_FROM_CALL_ONLY = {"recap_email", "internal_summary"}


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


def call_dates(transcript: Transcript, as_of: date) -> set[date]:
    """Dates said in the call: explicit dates, 'Thursday the eighth', and bare weekdays resolved to the
    next occurrence after the demo date."""
    found = {as_of, as_of + timedelta(days=1)}
    for u in transcript.utterances:
        found |= {d for _, d in _dates_in(u.text, as_of.year) if d}
        for m in WEEKDAY_ORDINAL_RE.finditer(u.text):
            day = ORDINALS[" ".join(m.group(2).lower().split())]
            for months_ahead in range(0, 3):
                y, mo = as_of.year + (as_of.month + months_ahead - 1) // 12, (as_of.month + months_ahead - 1) % 12 + 1
                try:
                    d = date(y, mo, day)
                except ValueError:
                    continue
                if d >= as_of:
                    found.add(d)
                    break
        for m in WEEKDAY_RE.finditer(u.text):
            target = WEEKDAYS.index(m.group(1).lower())
            delta = (target - as_of.weekday()) % 7 or 7
            found.add(as_of + timedelta(days=delta))
    return found


def check_dates(artifact: str, obj: BaseModel, as_of: date, strictly_after: bool,
                transcript: Transcript | None = None) -> CheckResult:
    """Dates must be real future business days. In the recap and internal summary they must also be
    dates said in the call (stress gap G18: a meeting moved from Oct 8 to Oct 9 passed), and relative
    dates like "next Thursday" are flagged because the reader cannot tell which day is meant."""
    bad = []
    said = call_dates(transcript, as_of) if transcript is not None and artifact in DATES_FROM_CALL_ONLY else None
    for text in _strings(obj) + _date_field_values(obj):
        for shown, d in _dates_in(text, as_of.year):
            if d is None:
                bad.append(f"{shown} (not a real date)")
            elif d.weekday() >= 5:
                bad.append(f"{shown} (weekend)")
            elif d < as_of or (strictly_after and d == as_of):
                bad.append(f"{shown} (not after {as_of.isoformat()})")
            elif said is not None and d not in said:
                bad.append(f"{shown} (not a date said in the call)")
        for m in RELATIVE_RE.finditer(text):
            bad.append(f"{m.group(0)} (relative date; write the actual date)")
    # High where dates must come from the call: a date nobody said misleads the rep or the customer (deal_c, D-15).
    severity = "high" if artifact in DATES_FROM_CALL_ONLY else "medium"
    return CheckResult("dates_future_business_days", artifact, not bad, severity,
                       "dates are future business days" if not bad else "bad dates: " + ", ".join(bad), bad)


# Names. Any capitalized word must be explained: a known person or proper noun from the transcript,
# CRM or reference material, a word on the allow list, or (at the start of a sentence) an ordinary word.
# A capitalized word in the middle of a sentence that is an ordinary English word ("Will Long") cannot
# be told apart from a name by code; the verifier is the second line for those.

COMMON_STARTERS = set("""send share flag offer ask book confirm bring give get schedule route draft prepare reach loop
invite tell propose follow check circle remind set build deliver update add call email introduce walk review run map
escalate align resolve provide attach request plan log note close thank thanks hi hello dear best regards cheers
sounds great looking happy please here there after before once when while as at by in on to of all both each every
no not open risk risks objection objections stakeholder stakeholders commitment commitments competitive notes items
milestone status proposed agreed ready waiting missing low champion economic buyer decision criteria process paper
pain metrics competition recap summary next steps step owner due why watch we our your you i they he she it this
that these those the a an and but or so if for with from about also then now today tomorrow let use keep make ask
""".split())
NOT_NAMES = {"Apex", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Central",
             "Eastern", "Pacific", "January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug",
             "Sep", "Sept", "Oct", "Nov", "Dec", "I"}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?:;])\s+|\n+|\s+-\s+|^\s*-\s*")
_CAP_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:'s)?\b")


_ENGLISH: set[str] | None = None


def english_words() -> set[str]:
    """Top 30,000 English words (wordfreq). Used only for capitalized words at the start of a sentence,
    so "Easy to miss" or "Fresh data" are not read as names. Falls back to a short allow list."""
    global _ENGLISH
    if _ENGLISH is None:
        try:
            from wordfreq import top_n_list
            _ENGLISH = set(top_n_list("en", 30000))
        except ImportError:
            _ENGLISH = set()
    return _ENGLISH


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]


def _reference_text() -> str:
    from src.prompts import stable_reference
    return stable_reference()[0]


def known_people(transcript: Transcript, crm: dict) -> set[str]:
    names = {p.name for p in transcript.participants} | {p.title for p in transcript.participants}
    names |= {c["name"] for c in crm.get("contacts", [])} | {c.get("title", "") for c in crm.get("contacts", [])}
    names |= {crm.get("owner_ae", ""), crm.get("sc", ""), crm.get("account", "")}
    tokens = set()
    for n in names:
        tokens |= set(n.split())
    return tokens


def _proper_nouns(texts: list[str]) -> set[str]:
    """Capitalized words that appear mid-sentence in the sources, so they are real proper nouns there."""
    found: set[str] = set()
    for text in texts:
        for sentence in _sentences(text):
            for i, m in enumerate(_CAP_RE.finditer(sentence)):
                if m.start() > 0 and sentence[:m.start()].strip():
                    found.add(m.group(0).removesuffix("'s"))
    return found


def check_names(artifact: str, obj: BaseModel, transcript: Transcript, crm: dict) -> CheckResult:
    sources = _source_strings(transcript, crm) + [_reference_text()]
    vocab = set(re.findall(r"[a-z]+", "\n".join(sources).lower())) | COMMON_STARTERS
    known = known_people(transcript, crm) | _proper_nouns(sources) | NOT_NAMES
    bad = []
    for text in _strings(obj):
        for sentence in _sentences(text):
            first = True
            for m in _CAP_RE.finditer(sentence):
                word = m.group(0).removesuffix("'s")
                initial = first and not sentence[:m.start()].strip()
                first = False
                if word in known or word.isupper():
                    continue
                if word.lower() in vocab:
                    continue  # appears in the sources or the allow list
                if initial and word.lower() in english_words():
                    continue  # ordinary word starting a sentence
                bad.append(word)
    return CheckResult("names_known", artifact, not bad, "high",
                       "every name or proper noun appears in the transcript, CRM or reference (heuristic)" if not bad
                       else "not found in transcript, CRM or reference: " + ", ".join(sorted(set(bad))),
                       sorted(set(bad)))


# Claims the call cannot support: counterfactual savings, guarantees, ROI. The SC in deal A explicitly
# declined to estimate savings, so a recap that claims them is an overclaim (stress gap O3).
UNSUPPORTED_CLAIM_RE = re.compile(
    r"\b(would have (?:saved|prevented|avoided|cut|reduced|caught)|will (?:save|cut|reduce|eliminate|prevent)|"
    r"guarantee(?:d|s)?|return on investment|\bROI\b|pay(?:s)? for itself)\b", re.I)


def check_unsupported_claims(artifact: str, obj: BaseModel) -> CheckResult:
    bad = [m.group(0) for text in _strings(obj) for m in UNSUPPORTED_CLAIM_RE.finditer(text)]
    return CheckResult("no_unsupported_claims", artifact, not bad, "high",
                       "no savings, guarantee or ROI claims" if not bad
                       else "claims the call does not support: " + ", ".join(sorted(set(bad))), sorted(set(bad)))


# Quoted text in drafts. The model writes the drafts, so any span it puts in quotation marks must be words
# a person actually said (reviewer finding R13). Spans under 3 words ("ready") are ignored.
QUOTE_RE = re.compile(r"[\"\u201c]([^\"\u201c\u201d]{3,300})[\"\u201d]")


def check_quotes(artifact: str, obj: BaseModel, transcript: Transcript) -> CheckResult:
    bad = []
    for text in _strings(obj):
        for m in QUOTE_RE.finditer(text):
            span = m.group(1).strip()
            if len(span.split()) < 3:
                continue
            if not any(transcript.resolve_evidence(u.id, span)[0] for u in transcript.utterances):
                bad.append(span[:80])
    return CheckResult("quotes_in_transcript", artifact, not bad, "high",
                       "quoted text matches the transcript" if not bad
                       else "quoted text not found in the transcript: " + "; ".join(bad), bad)


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
    results = [check_evidence(artifact, obj, transcript), check_numbers(artifact, obj, transcript, crm),
               check_dates(artifact, obj, as_of, strictly_after=(artifact == "assessment"), transcript=transcript),
               check_names(artifact, obj, transcript, crm)]
    if artifact in {"recap_email", "internal_summary"}:
        results.append(check_unsupported_claims(artifact, obj))
    if artifact in {"recap_email", "internal_summary", "mutual_action_plan"}:
        results.append(check_quotes(artifact, obj, transcript))
    if isinstance(obj, Assessment):
        results += [check_step_cap(obj), check_no_chase(obj)]
    if isinstance(obj, MutualActionPlan):
        results.append(check_map_agreed(obj))
    return results


def run_all(*, extraction: ExtractionRecord, assessment: Assessment, recap: RecapEmail | None,
            summary: InternalSummary | None, plan: MutualActionPlan | None, transcript: Transcript,
            crm: dict, as_of: date) -> list[CheckResult]:
    # Extraction: quotes must resolve and named people must exist (stress gap X1e: an invented
    # stakeholder in the extraction was never checked).
    results = [check_evidence("extraction", extraction, transcript),
               check_names("extraction", extraction, transcript, crm)]
    results += run_artifact("assessment", assessment, transcript, crm, as_of)
    for name, obj in (("recap_email", recap), ("internal_summary", summary), ("mutual_action_plan", plan)):
        if obj is not None:
            results += run_artifact(name, obj, transcript, crm, as_of)
    return results
