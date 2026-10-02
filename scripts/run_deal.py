"""Run one deal (or all) end to end and print a short text card.

  python scripts/run_deal.py deal_a                 uses DEBRIEF_MODE (default replay)
  python scripts/run_deal.py --all --mode record    calls the API and saves replay fixtures
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, record_store  # noqa: E402
from src.chain import Chain, load_context  # noqa: E402
from src.llm import LLMClient, ReplayMiss  # noqa: E402

DEALS = ["deal_a", "deal_b", "deal_c", "deal_x", "deal_y"]


def card(result, ctx) -> str:
    out = [f"== {ctx.crm['account']} ({result.deal_id}) | Synthetic data, fictional company."]
    a = result.assessment
    if a is None:
        out.append("No assessment: " + "; ".join(result.errors))
        return "\n".join(out)
    out.append(f"Deal state: {a.deal_state.value}. {a.deal_state_why}")
    for i, s in enumerate(a.next_steps, 1):
        tag = "MOST IMPORTANT" if i == 1 else f"Step {i}"
        out.append(f"\n[{tag}] {s.action}")
        out.append(f"  Owner: {s.owner}  Due: {s.due_by or 'no date'}  Rule: {s.playbook_rule_id}"
                   + (f"  Card: {s.release_card_id}" if s.release_card_id else ""))
        out.append(f"  Why: {s.why}")
        for e in s.evidence:
            q = ctx.transcript.render_quote(e.utterance_id)  # quote text comes from the transcript, not the model
            out.append(f"  > [{q['timestamp']}] {q['speaker']}: \"{q['text']}\"")
    for w in a.watch_items:
        out.append(f"\nWatch: {w.summary}" + (f" (use {w.release_card_id})" if w.release_card_id else ""))
    out.append("")
    for name, st in result.artifacts.items():
        if name == "assessment":
            continue
        flag = "NEEDS REVIEW" if st.needs_review else ("regenerated after check" if st.regenerated else "ok")
        out.append(f"Draft {name}: {flag}" + (f" ({'; '.join(st.flagged)[:200]})" if st.flagged else ""))
    if result.overrides:
        out.append("Rule overrides: " + "; ".join(f"{o['rule_id']} {o['target'][:40]}" for o in result.overrides))
    reads = sum(c["cache_read_input_tokens"] for c in result.calls)
    out.append(f"\nCost for this debrief: ${result.cost_usd:.4f} | model time {result.latency_ms / 1000:.1f}s | "
               f"cache read tokens {reads} | mode {result.mode}")
    return "\n".join(out)


async def run(deal: str, mode: str) -> int:
    ctx = load_context(deal)
    try:
        result = await Chain(LLMClient(mode=mode)).run(ctx)
    except ReplayMiss as e:
        print(f"{deal}: {e}", file=sys.stderr)
        return 2
    payload = result.to_dict()
    record_store.save_debrief(result.debrief_id, deal, result.prompt_versions, payload)
    out = ROOT / "var" / "debriefs" / f"{deal}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(card(result, ctx))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("deal", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--mode", default=None, choices=["live", "record", "replay"])
    args = ap.parse_args()
    deals = DEALS if args.all else [args.deal]
    if not deals or deals == [None]:
        ap.error("give a deal id or --all")
    codes = [asyncio.run(run(d, args.mode or config.MODE)) for d in deals]
    raise SystemExit(max(codes))


if __name__ == "__main__":
    main()
