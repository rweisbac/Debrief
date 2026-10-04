"""Next step comparison: does Debrief's top 3 beat a raw Claude call's top 3?

Synthetic data, fictional companies. Run 2, added on 2026-10-04 after run 1 (eval/results.md). Debrief is unchanged;
its next steps come from the run 1 outputs in eval/outputs/debrief/.

  python eval/next_steps.py top3      raw Claude asked for the 3 most important next steps (prompts/baseline_top3_v1.md)
  python eval/next_steps.py rubric    judge v2 (prompts/judge/v2.md, 8 best practice criteria) on every step
  python eval/next_steps.py pairwise  blind A/B on each case, both orders, 2 opponents
  python eval/next_steps.py report    writes eval/next_steps_results.md

Opponents for Debrief's steps:
- raw_top3: a plain call asked directly for a ranked top 3 (the fair opponent)
- baseline_top3: the first 3 numbered steps from run 1's generic summarize-and-draft output

Every step is judged as plain text: action, owner, timing and why. Debrief's citations and rule IDs are removed
so the judge cannot favor them. The pairwise judge sees A and B in both orders; a case counts as a win only when
both orders agree, otherwise it is a tie.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run import CASES, DATA, EVAL, FIXTURES, OUT, context, load, save  # noqa: E402
from eval.score import section  # noqa: E402
from evals.judges import ACCEPTABLE_V2, CRITERIA_V2, STRONG_V2  # noqa: E402
from src import config, prompts  # noqa: E402
from src.llm import LLMClient  # noqa: E402
from src.schemas import JudgeResultV2  # noqa: E402

config.STEP_SETTINGS["pairwise"] = {"effort": "medium", "max_tokens": 6000}
SOURCES = ("debrief", "raw_top3", "baseline_top3")
OPPONENTS = ("raw_top3", "baseline_top3", "raw_matched")  # raw_matched is a post hoc control added after the first report
ITEM = re.compile(r"^\s*(?:#+\s*)?(?:\*\*)?\s*(\d)[.)]\s*(.*)$")


def _lower(v):
    return v.strip().lower() if isinstance(v, str) else v


class ABEnum(str, Enum):
    a = "a"
    b = "b"
    tie = "tie"


class Pairwise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    winner: Annotated[ABEnum, BeforeValidator(_lower)]
    top_step_winner: Annotated[ABEnum, BeforeValidator(_lower)]
    why: str


def numbered_items(lines: list[str], n: int = 3) -> list[str]:
    """Top-level items numbered 1 to n, with their continuation lines."""
    items: list[str] = []
    for line in lines:
        m = ITEM.match(line)
        if m and int(m.group(1)) == len(items) + 1:
            if len(items) == n:
                break
            items.append(m.group(2).strip())
        elif items and line.strip() and not set(line.strip()) <= set("|-: "):
            items[-1] += " " + line.strip()
    return items[:n]


def table_items(lines: list[str], n: int = 3) -> list[str]:
    rows = [l for l in lines if l.strip().startswith("|") and not set(l.strip()) <= set("|-: ")]
    return [" ".join(c.strip() for c in r.strip("|").split("|")) for r in rows[1:n + 1]]  # skip header


def steps_for(source: str, case: str) -> list[str]:
    if source == "debrief":
        r = load("debrief", case)
        return [f"{s['action']} (owner {s['owner']}, due {s['due_by'] or 'no date'}). Why: {s['why']}"
                for s in r["artifacts"]["assessment"]["current"]["next_steps"]]
    if source == "raw_top3":
        return numbered_items(load("raw_top3", case)["text"].splitlines())
    if source == "raw_matched":  # post hoc control: raw top 3 cut to as many steps as Debrief gave on this case
        return steps_for("raw_top3", case)[:len(steps_for("debrief", case))]
    lines = section(load("baseline", case)["text"], "next step")
    return numbered_items(lines) or table_items(lines)


def render(steps: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


async def run_top3(cases: list[str]) -> None:
    import anthropic
    from eval.run import baseline_prompt
    config.apply_api_key_alias()
    client = anthropic.AsyncAnthropic(max_retries=2, timeout=600)
    rules = (EVAL / "prompts" / "baseline_top3_v1.md").read_text(encoding="utf-8").strip()
    general = (EVAL / "prompts" / "baseline_v1.md").read_text(encoding="utf-8").strip()

    async def one(case):
        if load("raw_top3", case):
            return
        prompt = baseline_prompt(case).replace(general, rules)
        msg = await client.messages.create(model=config.MODEL, max_tokens=4000,
                                           messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        save("raw_top3", case, {"deal_id": case, "status": "ran", "prompt": "baseline_top3_v1",
                                "stop_reason": msg.stop_reason, "text": text,
                                "cost_usd": config.cost_usd(config.MODEL, msg.usage.input_tokens,
                                                            msg.usage.output_tokens)})
        print(f"raw_top3 {case}: {msg.stop_reason}, {len(numbered_items(text.splitlines()))} steps parsed")
    await asyncio.gather(*(one(c) for c in cases))


async def run_rubric(cases: list[str]) -> None:
    text, version = prompts.load("judge", 2)
    sem = asyncio.Semaphore(6)

    async def one(source, case):
        key = f"rubric_{source}"
        if load(key, case):
            return
        steps = steps_for(source, case)
        out = []
        async with sem:
            llm = LLMClient(mode="record", replay_dir=FIXTURES)
            for i, s in enumerate(steps, 1):
                block = {"type": "text", "text": f"<step_to_judge>\n{s}\n</step_to_judge>"}
                res = await llm.acall(step="judge", output_model=JudgeResultV2, step_rules=text, prompt_version=version,
                                      user_blocks=[context(case).context_block(), block],
                                      debrief_id=f"{key}-{case}-{i}")
                out.append({"rank": i, "step": s, "judge": res.parsed.model_dump(mode="json") if res.parsed else None,
                            "error": res.parse_error, "cost_usd": res.cost_usd})
        save(key, case, {"deal_id": case, "source": source, "steps": out})
        print(f"{key} {case}: {len(out)} steps judged")
    await asyncio.gather(*(one(s, c) for c in cases for s in SOURCES))


async def run_pairwise(cases: list[str]) -> None:
    rules = (EVAL / "prompts" / "pairwise_v1.md").read_text(encoding="utf-8").strip()
    sem = asyncio.Semaphore(6)

    async def one(opponent, case):
        key = f"pairwise_{opponent}"
        if load(key, case):
            return
        d, o = steps_for("debrief", case), steps_for(opponent, case)
        verdicts = []
        async with sem:
            llm = LLMClient(mode="record", replay_dir=FIXTURES)
            for order, (a, b) in (("debrief_is_a", (d, o)), ("debrief_is_b", (o, d))):
                block = {"type": "text", "text": f"<list_a>\n{render(a)}\n</list_a>\n<list_b>\n{render(b)}\n</list_b>"}
                res = await llm.acall(step="pairwise", output_model=Pairwise, step_rules=rules,
                                      prompt_version="eval-pairwise-v1", user_blocks=[context(case).context_block(), block],
                                      debrief_id=f"{key}-{case}-{order}")
                p = res.parsed
                to_name = lambda v: "tie" if v == "tie" else ("debrief" if (v == "a") == (order == "debrief_is_a") else opponent)  # noqa: E731
                verdicts.append({"order": order, "winner": to_name(p.winner.value) if p else "error",
                                 "top_step_winner": to_name(p.top_step_winner.value) if p else "error",
                                 "why": p.why if p else res.parse_error, "cost_usd": res.cost_usd})
        save(key, case, {"deal_id": case, "opponent": opponent, "debrief_steps": d, "opponent_steps": o,
                         "verdicts": verdicts})
        print(f"{key} {case}: {[v['winner'] for v in verdicts]}")
    await asyncio.gather(*(one(op, c) for c in cases for op in OPPONENTS))


def agreed(verdicts: list[dict], field: str) -> str:
    vals = {v[field] for v in verdicts}
    return vals.pop() if len(vals) == 1 else "tie"


def report() -> None:
    L = ["# Next step comparison: Debrief vs raw Claude", "",
         "Synthetic data, fictional companies. Generated by `eval/next_steps.py report`. Run 2, added after run 1; Debrief unchanged.", "",
         "- Debrief's steps come from run 1. Opponents: `raw_top3`, a plain call asked for the 3 most important ranked next steps "
         "(`prompts/baseline_top3_v1.md`), and `baseline_top3`, the first 3 numbered steps from run 1's generic output.",
         "- Steps are judged as plain text. Debrief's citations and rule IDs are removed.",
         "- Rubric: judge v2 (`prompts/judge/v2.md`), 8 criteria from the best practice research. Acceptable = R1, R2, R4, R5, R6 pass. "
         "Strong = acceptable plus R3 and R7. Uncalibrated.",
         "- `raw_matched` is a post hoc control added after the first report: raw_top3 cut to as many steps as Debrief gave on each case, to separate step quality from list length.",
         "- Pairwise: blind A/B, run in both orders. A case is a win only when both orders agree; otherwise a tie. Uncalibrated.", ""]
    L += ["## Head to head", "", "| Debrief vs | Debrief wins | Ties or split | Opponent wins | First step: Debrief better | First step: opponent better |",
          "|---|---|---|---|---|---|"]
    detail = []
    for op in OPPONENTS:
        res = [load(f"pairwise_{op}", c) for c in CASES]
        res = [r for r in res if r]
        w = [agreed(r["verdicts"], "winner") for r in res]
        t = [agreed(r["verdicts"], "top_step_winner") for r in res]
        L.append(f"| {op} | {w.count('debrief')} | {w.count('tie')} | {w.count(op)} | {t.count('debrief')} | {t.count(op)} |")
        for r, wi in zip(res, w):
            detail.append(f"| {r['deal_id']} | {op} | {wi} | " + " / ".join(v["why"].replace("|", "/") for v in r["verdicts"]) + " |")
    L += ["", "## Rubric, per step", "",
          "| Source | Steps | Acceptable | Strong | " + " | ".join(c.split("_", 1)[0].upper() for c in CRITERIA_V2) + " |",
          "|---|---|---|---|---|" + "---|" * (len(CRITERIA_V2) - 1)]
    for src in SOURCES:
        steps = [s for c in CASES if (r := load(f"rubric_{src}", c)) for s in r["steps"] if s["judge"]]
        n = len(steps)
        acc = sum(all(s["judge"][k] for k in ACCEPTABLE_V2) for s in steps)
        strong = sum(all(s["judge"][k] for k in STRONG_V2) for s in steps)
        per = " | ".join(str(sum(s["judge"][k] for s in steps)) for k in CRITERIA_V2)
        L.append(f"| {src} | {n} | {acc} | {strong} | {per} |")
    L += ["", "First-ranked step only:", "", "| Source | Cases | Acceptable | Strong |", "|---|---|---|---|"]
    for src in SOURCES:
        firsts = [r["steps"][0] for c in CASES if (r := load(f"rubric_{src}", c)) and r["steps"] and r["steps"][0]["judge"]]
        L.append(f"| {src} | {len(firsts)} | {sum(all(s['judge'][k] for k in ACCEPTABLE_V2) for s in firsts)} | "
                 f"{sum(all(s['judge'][k] for k in STRONG_V2) for s in firsts)} |")
    L += ["", "## Per case verdicts (both orders)", "", "| Case | Opponent | Agreed winner | Why (order 1 / order 2) |", "|---|---|---|---|"] + detail
    cost = sum(s.get("cost_usd", 0) for src in SOURCES for c in CASES if (r := load(f"rubric_{src}", c)) for s in r["steps"])
    cost += sum(v.get("cost_usd", 0) for op in OPPONENTS for c in CASES
                if (r := load(f"pairwise_{op}", c)) for v in r["verdicts"])
    cost += sum((load("raw_top3", c) or {}).get("cost_usd", 0) for c in CASES)
    L += ["", f"Cost of this run: ${cost:.2f}.", "",
          "## Limits", "", "- 15 synthetic cases, 1 run, uncalibrated judges from the same model family.",
          "- Debrief was capped at 2 steps on 6 cases by its low-information rule (see `hand_review.md`).", ""]
    (EVAL / "next_steps_results.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:30]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["top3", "rubric", "pairwise", "report"])
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    cases = a.cases.split(",")
    if a.what == "report":
        report()
    else:
        asyncio.run({"top3": run_top3, "rubric": run_rubric, "pairwise": run_pairwise}[a.what](cases))


if __name__ == "__main__":
    main()
