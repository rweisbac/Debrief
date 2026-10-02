"""LLM judge for next step quality, with calibration against hand labels.

Criteria (binary each): specific, evidence_tied, playbook_tied, actionable_10_min, non_obvious.
A step passes only if every criterion passes.

Calibration protocol:
- data/labels/candidates.csv has 30 candidate steps: 10 dev, 20 test, fixed split.
- Iterate on the judge prompt with dev only:   python evals/judges.py dev
- Freeze the prompt before looking at test:    python evals/judges.py freeze
- Score test once:                             python evals/judges.py test
  This refuses to run if the judge prompt changed after the freeze.
- Test items are never put in the judge prompt. The prompt has no examples at all.
Until test labels exist and the judge is frozen, every judge result is reported as "uncalibrated".
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import prompts  # noqa: E402
from src.chain import load_context  # noqa: E402
from src.llm import LLMClient  # noqa: E402
from src.schemas import JudgeResult  # noqa: E402

CANDIDATES = ROOT / "data" / "labels" / "candidates.csv"
FREEZE = ROOT / "evals" / "judge_freeze.json"
CRITERIA = ["specific", "evidence_tied", "playbook_tied", "actionable_10_min", "non_obvious"]


def judge_prompt_hash() -> tuple[str, str]:
    text, version = prompts.load("judge")
    return version, hashlib.sha256(text.encode()).hexdigest()


def overall(j: JudgeResult) -> bool:
    return all(getattr(j, c) for c in CRITERIA)


async def judge_step(llm: LLMClient, deal_id: str, step: dict, debrief_id: str):
    ctx = load_context(deal_id)
    text, version = prompts.load("judge")
    quotes = []
    for e in step.get("evidence", []):
        u = ctx.transcript.get(e["utterance_id"])
        quotes.append({"utterance_id": e["utterance_id"], "line": u.text if u else "(no such line)"})
    payload = {"step": {k: step.get(k, "") for k in ("action", "owner", "due_by", "playbook_rule_id",
                                                       "release_card_id", "action_type", "why")},
               "cited_lines": quotes}
    block = {"type": "text", "text": "<step_to_judge>\n" + json.dumps(payload, indent=1, sort_keys=True) + "\n</step_to_judge>"}
    return await llm.acall(step="judge", output_model=JudgeResult, step_rules=text, prompt_version=version,
                           user_blocks=[ctx.context_block(), block], debrief_id=debrief_id)


def load_candidates() -> list[dict]:
    with CANDIDATES.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def candidate_as_step(row: dict) -> dict:
    return {"action": row["action"], "owner": row["owner"], "due_by": "", "playbook_rule_id": row["playbook_rule_id"],
            "release_card_id": row["release_card_id"], "action_type": row["action_type"], "why": row["why"],
            "evidence": [{"utterance_id": row["evidence_utterance_id"], "excerpt": row["evidence_excerpt"]}]}


def status() -> dict:
    rows = load_candidates() if CANDIDATES.exists() else []
    test = [r for r in rows if r["split"] == "test"]
    labeled = [r for r in test if r["label"].strip().lower() in {"pass", "fail"}]
    version, digest = judge_prompt_hash()
    frozen = json.loads(FREEZE.read_text()) if FREEZE.exists() else None
    return {"test_items": len(test), "test_labeled": len(labeled), "frozen": frozen is not None,
            "frozen_matches_current": bool(frozen) and frozen["sha256"] == digest,
            "calibrated": bool(test) and len(labeled) == len(test) and bool(frozen) and frozen["sha256"] == digest
            and (ROOT / "evals" / "judge_calibration.json").exists()}


def rates(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs of (human_pass, judge_pass). TPR = judge pass among human pass; TNR = judge fail among human fail."""
    tp = sum(1 for h, j in pairs if h and j)
    fn = sum(1 for h, j in pairs if h and not j)
    tn = sum(1 for h, j in pairs if not h and not j)
    fp = sum(1 for h, j in pairs if not h and j)
    return {"tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "tpr": f"{tp} of {tp + fn}", "tnr": f"{tn} of {tn + fp}"}


async def run_split(split: str, mode: str) -> dict:
    rows = [r for r in load_candidates() if r["split"] == split]
    missing = [r["id"] for r in rows if r["label"].strip().lower() not in {"pass", "fail"}]
    if missing:
        raise SystemExit(f"{len(missing)} {split} items are not labeled yet: {', '.join(missing)}")
    llm = LLMClient(mode=mode)
    pairs, details = [], []
    for r in rows:
        res = await judge_step(llm, r["deal_id"], candidate_as_step(r), f"judge-{split}-{r['id']}")
        if res.parsed is None:
            details.append({"id": r["id"], "error": res.parse_error or "refused"})
            continue
        human, judge = r["label"].strip().lower() == "pass", overall(res.parsed)
        pairs.append((human, judge))
        details.append({"id": r["id"], "human": human, "judge": judge, "critique": res.parsed.critique,
                        **{c: getattr(res.parsed, c) for c in CRITERIA}})
    return {"split": split, **rates(pairs), "details": details}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["status", "dev", "freeze", "test"])
    ap.add_argument("--mode", default="live", choices=["live", "record", "replay"])
    args = ap.parse_args()
    if args.command == "status":
        print(json.dumps(status(), indent=2))
    elif args.command == "freeze":
        version, digest = judge_prompt_hash()
        FREEZE.write_text(json.dumps({"prompt_version": version, "sha256": digest}, indent=2) + "\n")
        print(f"froze judge prompt {version} {digest[:12]}")
    elif args.command == "dev":
        print(json.dumps(asyncio.run(run_split("dev", args.mode)), indent=2))
    elif args.command == "test":
        st = status()
        if not st["frozen_matches_current"]:
            raise SystemExit("judge prompt is not frozen or changed after the freeze; refusing to score test")
        out = asyncio.run(run_split("test", args.mode))
        (ROOT / "evals" / "judge_calibration.json").write_text(json.dumps(out, indent=2) + "\n")
        print(json.dumps({k: v for k, v in out.items() if k != "details"}, indent=2))


if __name__ == "__main__":
    main()
