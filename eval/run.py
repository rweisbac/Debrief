"""Run Debrief, the plain baseline, and the blind claim judge on the eval transcripts.

Synthetic data, fictional companies.

  python eval/run.py debrief   [--cases e01,e02]   Debrief chain, record mode (fixtures in eval/fixtures/replay)
  python eval/run.py baseline  [--cases ...]       one plain Claude call per transcript, generic prompt
  python eval/run.py judge     [--cases ...]       claim judge on both outputs, same prompt, system name hidden

Raw outputs go to eval/outputs/<system>/<case>.json. Reruns reuse saved outputs and fixtures, so a
second run costs nothing. Delete an output file to rerun that case.

Exception to CLAUDE.md hard rule 1: the baseline is the control arm, so it calls the SDK directly with
no schema, no effort setting and no Debrief guardrails. Debrief and the judge go through src/llm.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEBRIEF_DB", str(ROOT / "eval" / "outputs" / "llm_calls.sqlite3"))

from src import config  # noqa: E402
from src.adapters import FileCRMSource, FileGongSource  # noqa: E402
from src.chain import Chain, load_context  # noqa: E402
from src.llm import LLMClient  # noqa: E402

EVAL = ROOT / "eval"
DATA = EVAL / "data"
OUT = EVAL / "outputs"
FIXTURES = EVAL / "fixtures" / "replay"
CASES = sorted(p.stem for p in (DATA / "transcripts").glob("*.txt"))
BASELINE_MAX_TOKENS = 8000
config.STEP_SETTINGS["claim_judge"] = {"effort": "medium", "max_tokens": 16000}


def save(system: str, case: str, obj: dict) -> None:
    (OUT / system).mkdir(parents=True, exist_ok=True)
    (OUT / system / f"{case}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n", encoding="utf-8")


def load(system: str, case: str) -> dict | None:
    p = OUT / system / f"{case}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def context(case: str):
    return load_context(case, FileGongSource(DATA), FileCRMSource(DATA))


# Debrief

async def run_debrief_case(case: str, sem: asyncio.Semaphore, mode: str) -> None:
    if load("debrief", case):
        print(f"debrief {case}: saved output exists, skipped")
        return
    async with sem:
        t0 = time.perf_counter()
        llm = LLMClient(mode=mode, replay_dir=FIXTURES)
        try:
            result = await Chain(llm).run(context(case))
            r = result.to_dict()
            r["wall_clock_s"] = round(time.perf_counter() - t0, 1)
            r["status"] = "ran"
        except Exception as e:  # recorded, never hidden
            r = {"deal_id": case, "status": "error", "error": f"{type(e).__name__}: {e}"}
        save("debrief", case, r)
        print(f"debrief {case}: {r['status']} errors={r.get('errors')} cost=${r.get('cost_usd', 0):.3f}")


# Baseline

def baseline_prompt(case: str) -> str:
    rules = (EVAL / "prompts" / "baseline_v1.md").read_text(encoding="utf-8").strip()
    transcript = (DATA / "transcripts" / f"{case}.txt").read_text(encoding="utf-8")
    crm = (DATA / "crm" / f"{case}.json").read_text(encoding="utf-8")
    return f"{rules}\n\n<transcript>\n{transcript}\n</transcript>\n\n<crm>\n{crm}\n</crm>"


async def run_baseline_case(case: str, sem: asyncio.Semaphore, client) -> None:
    if load("baseline", case):
        print(f"baseline {case}: saved output exists, skipped")
        return
    async with sem:
        t0 = time.perf_counter()
        try:
            msg = await client.messages.create(model=config.MODEL, max_tokens=BASELINE_MAX_TOKENS,
                                               messages=[{"role": "user", "content": baseline_prompt(case)}])
            text = "".join(b.text for b in msg.content if b.type == "text")
            u = msg.usage
            r = {"deal_id": case, "status": "ran", "model": config.MODEL, "prompt": "baseline_v1",
                 "stop_reason": msg.stop_reason, "text": text,
                 "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
                 "cost_usd": config.cost_usd(config.MODEL, u.input_tokens, u.output_tokens),
                 "wall_clock_s": round(time.perf_counter() - t0, 1),
                 "recorded_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            r = {"deal_id": case, "status": "error", "error": f"{type(e).__name__}: {e}"}
        save("baseline", case, r)
        print(f"baseline {case}: {r['status']} {r.get('stop_reason', r.get('error', ''))}")


# Rendering Debrief's user-facing output as plain text, the way a rep reads it

def render_debrief(r: dict) -> str:
    art = r.get("artifacts") or {}
    cur = lambda k: (art.get(k) or {}).get("current")  # noqa: E731
    lines = []
    a = cur("assessment")
    if a:
        lines.append(f"Deal state: {a['deal_state']}. {a['deal_state_why']}")
        lines.append("Next steps:")
        for i, s in enumerate(a["next_steps"], 1):
            lines.append(f"{i}. {s['action']} (owner {s['owner']}, due {s['due_by'] or 'no date'}). Why: {s['why']}")
        for w in a["watch_items"]:
            lines.append(f"Watch: {w['summary']}")
    rec = cur("recap_email")
    if rec:
        lines += ["", "Recap email draft:", f"Subject: {rec['subject']}", rec["body"]]
    s = cur("internal_summary")
    if s:
        lines += ["", "Internal summary:", s["deal_state_line"], f"Customer value: {s['customer_value_line']}"]
        for key in ("what_we_validated", "integration_patterns", "objections_and_answers", "open_items",
                    "commitments", "stakeholders", "competitive_notes", "risks"):
            for v in s[key]:
                lines.append(f"{key.replace('_', ' ').capitalize()}: {v}")
    m = cur("mutual_action_plan")
    if m:
        lines += ["", "Mutual action plan:"]
        for row in m["rows"]:
            lines.append(f"- {row['milestone']} | customer: {row['customer_owner'] or 'none'} | apex: "
                         f"{row['apex_owner'] or 'none'} | {row['target_date'] or 'no date'} | {row['status']}")
    blocked = [k for k, v in art.items() if v.get("needs_review")]
    if blocked:
        lines += ["", "Needs review before approval: " + ", ".join(blocked)]
    return "\n".join(lines)


def render_extraction(r: dict) -> str:
    """The full call record the SC sees, used only for the full-record recall view."""
    ex = r.get("extraction") or {}
    lines = []
    for key, val in ex.items():
        items = val if isinstance(val, list) else [val]
        for it in items:
            body = {k: v for k, v in it.items() if k != "evidence"}
            lines.append(f"{key.replace('_', ' ').capitalize()}: " + "; ".join(f"{k} {v}" for k, v in body.items()))
    return "\n".join(lines)


# Judge

def _lower(v):
    return v.strip().lower() if isinstance(v, str) else v


class ClaimCategoryEnum(str, Enum):
    concern = "concern"
    risk = "risk"
    commitment = "commitment"
    next_step = "next_step"
    other = "other"


class JudgedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    category: Annotated[ClaimCategoryEnum, BeforeValidator(_lower)]
    supported: bool
    utterance_ids: list[str]
    overstated_commitment: bool
    flagged_uncertain: bool
    why: str


class ClaimReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[JudgedClaim]


def output_text(system: str, r: dict) -> str:
    return render_debrief(r) if system == "debrief" else r["text"]


async def judge_case(case: str, system: str, sem: asyncio.Semaphore, mode: str) -> None:
    key = f"judge_{system}"
    if load(key, case):
        print(f"{key} {case}: saved output exists, skipped")
        return
    r = load(system, case)
    if not r or r.get("status") != "ran":
        print(f"{key} {case}: no {system} output, skipped")
        return
    ctx = context(case)
    block = ctx.context_block()
    block = {"type": "text", "text": block["text"] + f"\n<output>\n{output_text(system, r)}\n</output>"}
    rules = (EVAL / "prompts" / "claim_judge_v1.md").read_text(encoding="utf-8").strip()
    async with sem:
        llm = LLMClient(mode=mode, replay_dir=FIXTURES)
        res = await llm.acall(step="claim_judge", output_model=ClaimReport, step_rules=rules,
                              prompt_version="eval-claim-judge-v1", user_blocks=[block], debrief_id=f"{key}-{case}")
    out = {"deal_id": case, "system": system, "status": "ran" if res.parsed else "error",
           "claims": [c.model_dump(mode="json") for c in res.parsed.claims] if res.parsed else [],
           "stop_reason": res.stop_reason, "refused": res.refused, "error": res.parse_error,
           "cost_usd": res.cost_usd}
    save(key, case, out)
    print(f"{key} {case}: {out['status']} {len(out['claims'])} claims")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["debrief", "baseline", "judge"])
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--mode", default="record", choices=["record", "replay", "live"])
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    cases = args.cases.split(",")
    sem = asyncio.Semaphore(args.concurrency)
    if args.what == "debrief":
        await asyncio.gather(*(run_debrief_case(c, sem, args.mode) for c in cases))
    elif args.what == "baseline":
        import anthropic
        config.apply_api_key_alias()
        client = anthropic.AsyncAnthropic(max_retries=2, timeout=600)
        await asyncio.gather(*(run_baseline_case(c, sem, client) for c in cases))
    else:
        await asyncio.gather(*(judge_case(c, s, sem, args.mode) for c in cases for s in ("debrief", "baseline")))


if __name__ == "__main__":
    asyncio.run(main())
