"""The debrief chain: 4 stages, 7 model calls on the normal path.

A. extract, extract_b       2 calls  -> ExtractionPartA, ExtractionPartB, merged into ExtractionRecord
   (code) MEDDPICC view and gaps
B. assess_and_recommend    1 call   -> Assessment, then deterministic overrides (rules.py)
C. drafts                  3 calls in parallel -> RecapEmail, InternalSummary, MutualActionPlan
D. verify                  deterministic checks, then 1 skeptical verifier call.
   High severity failures: regenerate that artifact once with the findings, re-check it, and
   re-verify it. If it still fails it is marked needs review. The original is always kept.
"""
from __future__ import annotations

import asyncio
import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from pydantic import BaseModel

from src import checks, meddpicc, prompts, rules
from src.adapters import CRMSource, FileCRMSource, FileGongSource, GongSource
from src.llm import CallResult, LLMClient
from src.schemas import (Assessment, ExtractionPartA, ExtractionPartB, ExtractionRecord, InternalSummary,
                         MutualActionPlan, RecapEmail, VerifierReport, empty_part_a, empty_part_b, validate_assessment, validate_evidence_excerpts, validate_extraction,
                         validate_map)
from src.transcript import Transcript

DRAFT_STEPS = {
    "recap_email": ("draft_recap_email", RecapEmail),
    "internal_summary": ("draft_internal_summary", InternalSummary),
    "mutual_action_plan": ("draft_mutual_action_plan", MutualActionPlan),
}
MAX_RECAP_WORDS = 180


@dataclass
class DealContext:
    deal_id: str
    transcript: Transcript
    crm: dict
    activity: dict
    as_of: date

    def context_block(self) -> dict:
        """Identical for every step of one deal, so it sits in the cached prefix."""
        crm = {k: v for k, v in self.crm.items() if not k.startswith("_")}
        text = (
            f"<as_of>{self.as_of.isoformat()} ({self.as_of.strftime('%A')}), the day of the demo</as_of>\n"
            f"<crm>\n{json.dumps(crm, indent=1, sort_keys=True)}\n</crm>\n"
            f"<transcript>\n{self.transcript.render_for_model()}\n</transcript>")
        return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


@dataclass
class ArtifactState:
    current: BaseModel | None
    original: BaseModel | None
    regenerated: bool = False
    needs_review: bool = False
    flagged: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    refused: bool = False
    refusal: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        dump = lambda m: m.model_dump(mode="json") if m is not None else None  # noqa: E731
        return {"current": dump(self.current), "original": dump(self.original), "regenerated": self.regenerated,
                "needs_review": self.needs_review, "flagged": self.flagged, "findings": self.findings,
                "refused": self.refused, "refusal": self.refusal, "error": self.error}


@dataclass
class DebriefResult:
    debrief_id: str
    deal_id: str
    as_of: str
    mode: str
    model: str
    extraction: ExtractionRecord | None = None
    meddpicc: BaseModel | None = None
    assessment_raw: Assessment | None = None
    artifacts: dict[str, ArtifactState] = field(default_factory=dict)
    overrides: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    verifier: list[dict] = field(default_factory=list)
    prompt_versions: dict[str, str] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def assessment(self) -> Assessment | None:
        state = self.artifacts.get("assessment")
        return state.current if state else None

    @property
    def cost_usd(self) -> float:
        return round(sum(c["cost_usd"] for c in self.calls), 6)

    @property
    def latency_ms(self) -> int:
        return sum(c["latency_ms"] for c in self.calls)

    def to_dict(self) -> dict:
        dump = lambda m: m.model_dump(mode="json") if m is not None else None  # noqa: E731
        return {"debrief_id": self.debrief_id, "deal_id": self.deal_id, "as_of": self.as_of, "mode": self.mode,
                "model": self.model, "extraction": dump(self.extraction), "meddpicc": dump(self.meddpicc),
                "assessment_raw": dump(self.assessment_raw),
                "artifacts": {k: v.to_dict() for k, v in self.artifacts.items()},
                "overrides": self.overrides, "checks": self.checks, "verifier": self.verifier,
                "prompt_versions": self.prompt_versions, "calls": self.calls, "errors": self.errors,
                "cost_usd": self.cost_usd, "latency_ms": self.latency_ms}


def load_context(deal_id: str, gong: GongSource | None = None, crm_source: CRMSource | None = None) -> DealContext:
    gong = gong or FileGongSource()
    crm_source = crm_source or FileCRMSource()
    crm = crm_source.deal(deal_id)
    as_of = datetime.fromisoformat(crm["demo"]["actual_end"]).date()
    return DealContext(deal_id, gong.transcript(deal_id), crm, gong.activity(deal_id), as_of)


def _json_block(tag: str, obj) -> dict:
    payload = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    return {"type": "text", "text": f"<{tag}>\n{json.dumps(payload, indent=1, sort_keys=True)}\n</{tag}>"}


def _resolve_errors(obj: BaseModel, transcript: Transcript) -> list[str]:
    errors = []
    for ref in checks._evidence(obj):
        ok, reason = transcript.resolve_evidence(ref.utterance_id, ref.excerpt)
        if not ok:
            errors.append(f"evidence {ref.utterance_id} {ref.excerpt!r}: {reason}. Copy the excerpt word for word.")
    return errors


class Chain:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def _call(self, result: DebriefResult, step: str, model: type[BaseModel], user_blocks: list[dict],
                    validator=None) -> CallResult:
        rules_text, version = prompts.load(step)
        res = await self.llm.acall(step=step, output_model=model, step_rules=rules_text, prompt_version=version,
                                   user_blocks=user_blocks, debrief_id=result.debrief_id, validator=validator)
        result.prompt_versions[step] = res.prompt_version
        result.calls.append({"step": step, "attempts": res.attempts, "stop_reason": res.stop_reason,
                             "refused": res.refused, "cost_usd": res.cost_usd, "latency_ms": res.latency_ms,
                             "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                             "cache_read_input_tokens": res.cache_read_input_tokens,
                             "cache_creation_input_tokens": res.cache_creation_input_tokens,
                             "validator_errors": res.validator_errors, "keys": res.keys})
        return res

    # Stage A. Two calls (A then B, so the second reads the cached prefix); merged in code.
    async def extract(self, ctx: DealContext, result: DebriefResult) -> CallResult:
        def validator_a(part: ExtractionPartA) -> list[str]:
            rec = ExtractionRecord.from_parts(part, empty_part_b())
            return validate_extraction(rec) + _resolve_errors(part, ctx.transcript)

        def validator_b(part: ExtractionPartB) -> list[str]:
            rec = ExtractionRecord.from_parts(empty_part_a(), part)
            return validate_extraction(rec) + _resolve_errors(part, ctx.transcript)

        a = await self._call(result, "extract", ExtractionPartA, [ctx.context_block()], validator_a)
        if a.parsed is None:
            return a
        b = await self._call(result, "extract_b", ExtractionPartB, [ctx.context_block()], validator_b)
        if b.parsed is None:
            return b
        merged = copy.copy(b)
        merged.parsed = ExtractionRecord.from_parts(a.parsed, b.parsed)
        merged.validator_errors = list(a.validator_errors) + list(b.validator_errors)
        return merged

    # Stage B
    async def assess(self, ctx: DealContext, result: DebriefResult, extraction: ExtractionRecord,
                     gaps: list[str], findings: list[str] | None = None) -> CallResult:
        rule_ids, card_ids = prompts.playbook_rule_ids(), prompts.release_card_ids()

        def validator(a: Assessment) -> list[str]:
            errors = validate_assessment(a) + _resolve_errors(a, ctx.transcript)
            for i, s in enumerate(a.next_steps, 1):
                if s.playbook_rule_id.strip().upper() not in rule_ids:
                    errors.append(f"step {i} cites unknown rule {s.playbook_rule_id!r}")
                if s.release_card_id and s.release_card_id.strip().upper() not in card_ids:
                    errors.append(f"step {i} cites unknown release card {s.release_card_id!r}")
            return errors

        blocks = [ctx.context_block(), _json_block("extraction", extraction),
                  _json_block("meddpicc_gaps", {"unknown_after_tv_demo": gaps})]
        if findings:
            blocks.append(_json_block("reviewer_findings_to_fix", findings))
        return await self._call(result, "assess_and_recommend", Assessment, blocks, validator)

    # Stage C
    async def draft(self, ctx: DealContext, result: DebriefResult, name: str, extraction: ExtractionRecord,
                    assessment: Assessment, findings: list[str] | None = None) -> CallResult:
        step, model = DRAFT_STEPS[name]

        def validator(obj: BaseModel) -> list[str]:
            errors = validate_evidence_excerpts(obj) + _resolve_errors(obj, ctx.transcript)
            if isinstance(obj, RecapEmail) and len(obj.body.split()) > MAX_RECAP_WORDS:
                errors.append(f"recap body has {len(obj.body.split())} words, max {MAX_RECAP_WORDS}")
            if isinstance(obj, MutualActionPlan):
                errors += validate_map(obj)
            return errors

        blocks = [ctx.context_block(), _json_block("extraction", extraction), _json_block("assessment", assessment)]
        if findings:
            blocks.append(_json_block("reviewer_findings_to_fix", findings))
        return await self._call(result, step, model, blocks, validator)

    # Stage D, model part
    async def verify(self, ctx: DealContext, result: DebriefResult, artifacts: dict[str, BaseModel]) -> CallResult:
        blocks = [ctx.context_block()] + [_json_block(name, obj) for name, obj in artifacts.items() if obj is not None]
        return await self._call(result, "verify", VerifierReport, blocks)

    async def run(self, ctx: DealContext) -> DebriefResult:
        result = DebriefResult(debrief_id=f"{ctx.deal_id}-{uuid.uuid4().hex[:8]}", deal_id=ctx.deal_id,
                               as_of=ctx.as_of.isoformat(), mode=self.llm.mode, model=self.llm.model)

        # A
        ex = await self.extract(ctx, result)
        if ex.parsed is None:
            result.errors.append("extract failed: " + (f"refused {ex.refusal}" if ex.refused else ex.parse_error))
            return result
        extraction: ExtractionRecord = ex.parsed
        if ex.validator_errors:
            result.errors.append("extract still has validator errors after retry: " + "; ".join(ex.validator_errors))
        result.extraction = extraction
        view = meddpicc.compute(extraction, ctx.crm)
        result.meddpicc = view

        # B
        asr = await self.assess(ctx, result, extraction, meddpicc.gaps(view))
        if asr.parsed is None:
            result.artifacts["assessment"] = ArtifactState(None, None, needs_review=True, refused=asr.refused,
                                                           refusal=asr.refusal, error=asr.parse_error)
            result.errors.append("assess_and_recommend failed")
            return result
        result.assessment_raw = asr.parsed
        assessment, overrides = rules.apply(asr.parsed, extraction, ctx.transcript)
        result.overrides += [o.to_dict() for o in overrides]
        result.artifacts["assessment"] = ArtifactState(assessment, assessment)

        # C
        names = list(DRAFT_STEPS)
        drafted = await asyncio.gather(*(self.draft(ctx, result, n, extraction, assessment) for n in names))
        for name, res in zip(names, drafted):
            obj = res.parsed
            if isinstance(obj, MutualActionPlan):
                obj, map_overrides = rules.enforce_map_agreed(obj, ctx.transcript)
                result.overrides += [o.to_dict() for o in map_overrides]
            result.artifacts[name] = ArtifactState(obj, obj, refused=res.refused, refusal=res.refusal,
                                                   error=res.parse_error, needs_review=obj is None)

        # D
        await self._verify_and_repair(ctx, result, extraction, view)
        return result

    def _det_checks(self, ctx: DealContext, result: DebriefResult, extraction: ExtractionRecord) -> list[checks.CheckResult]:
        a = result.artifacts
        return checks.run_all(extraction=extraction, assessment=a["assessment"].current,
                              recap=a["recap_email"].current, summary=a["internal_summary"].current,
                              plan=a["mutual_action_plan"].current, transcript=ctx.transcript,
                              crm=ctx.crm, as_of=ctx.as_of)

    @staticmethod
    def _high_failures(det: list[checks.CheckResult], report: VerifierReport | None) -> dict[str, list[str]]:
        failing: dict[str, list[str]] = {}
        for c in det:
            if not c.passed and c.severity == "high" and c.artifact != "extraction":
                failing.setdefault(c.artifact, []).append(f"[{c.check}] {c.detail}: {', '.join(c.locations)}")
        if report:
            for v in report.verdicts:
                if not v.passed and v.severity.value == "high":
                    failing.setdefault(v.artifact.value, []).append(
                        f"[{v.check.value}] {v.finding} (target: {v.target}; lines {', '.join(v.utterance_ids)})")
        return failing

    async def _verify_and_repair(self, ctx: DealContext, result: DebriefResult, extraction: ExtractionRecord,
                                 view) -> None:
        det = self._det_checks(ctx, result, extraction)
        live = {k: v.current for k, v in result.artifacts.items() if v.current is not None}
        vr = await self.verify(ctx, result, live)
        report: VerifierReport | None = vr.parsed
        if report is None:
            result.errors.append("verifier failed: " + (f"refused {vr.refusal}" if vr.refused else vr.parse_error))
        result.checks = [c.to_dict() for c in det]
        result.verifier = [v.model_dump(mode="json") for v in report.verdicts] if report else []
        failing = self._high_failures(det, report)

        for name, findings in failing.items():
            state = result.artifacts.get(name)
            if state is None or state.current is None:
                continue
            state.findings = findings
            if name == "assessment":
                res = await self.assess(ctx, result, extraction, meddpicc.gaps(view), findings)
                new = None
                if res.parsed is not None:
                    new, overrides = rules.apply(res.parsed, extraction, ctx.transcript)
                    result.overrides += [o.to_dict() for o in overrides]
            else:
                res = await self.draft(ctx, result, name, extraction, result.assessment, findings)
                new = res.parsed
                if isinstance(new, MutualActionPlan):
                    new, map_overrides = rules.enforce_map_agreed(new, ctx.transcript)
                    result.overrides += [o.to_dict() for o in map_overrides]
            if new is None:
                state.needs_review = True
                state.flagged = findings
                state.error = "regeneration failed: " + (f"refused {res.refusal}" if res.refused else res.parse_error)
                continue
            state.current, state.regenerated = new, True
            recheck = checks.run_artifact(name, new, ctx.transcript, ctx.crm, ctx.as_of)
            rv = await self.verify(ctx, result, {name: new})
            still = self._high_failures(recheck, rv.parsed)
            result.checks += [dict(c.to_dict(), after_regeneration=True) for c in recheck]
            if rv.parsed:
                result.verifier += [dict(v.model_dump(mode="json"), after_regeneration=True) for v in rv.parsed.verdicts]
            if rv.parsed is None:
                # The rewritten draft was never cleared by the verifier, so it cannot be one-tap approved.
                still.setdefault(name, []).append(
                    "[verifier] the rewritten draft could not be re-checked: "
                    + (f"refused {rv.refusal}" if rv.refused else rv.parse_error or "no output"))
            if still.get(name):
                state.needs_review = True
                state.flagged = still[name]


async def arun_debrief(deal_id: str, llm: LLMClient | None = None) -> DebriefResult:
    llm = llm or LLMClient()
    return await Chain(llm).run(load_context(deal_id))


def run_debrief(deal_id: str, llm: LLMClient | None = None) -> DebriefResult:
    return asyncio.run(arun_debrief(deal_id, llm))
