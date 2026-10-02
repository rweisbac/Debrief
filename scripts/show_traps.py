"""Print the planted traps T1 to T6 (and adversarial checks) with utterance IDs and verbatim text.

Text is rendered from the parsed transcript, not from the gold file.
Run: python scripts/show_traps.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.transcript import load_transcript  # noqa: E402

GOLD = ROOT / "data" / "gold"


def rows() -> list[dict]:
    out = []
    for path in sorted(GOLD.glob("*.json")):
        g = json.loads(path.read_text(encoding="utf-8"))
        t = load_transcript(g["deal_id"])
        items = list(g["traps"])
        if "adversarial" in g:
            adv = g["adversarial"]
            src = g["contradictions"][0]["evidence"] if g["contradictions"] else []
            items.append({"id": adv["id"], "name": "Adversarial", "evidence": src,
                          "expected_behavior": adv["expected_behavior"]})
        for trap in items:
            quotes = []
            for ref in trap["evidence"]:
                q = t.render_quote(ref["utterance_id"])
                quotes.append(f'{q["utterance_id"]} [{q["timestamp"]}] {q["speaker"]}: "{ref["anchor"]}"')
            out.append({"id": trap["id"], "deal": g["deal_id"], "name": trap["name"],
                        "quotes": quotes, "expected": trap["expected_behavior"]})
    return sorted(out, key=lambda r: r["id"])


if __name__ == "__main__":
    print("| Trap | Deal | What | Utterances | Expected behavior |")
    print("|---|---|---|---|---|")
    for r in rows():
        quotes = "<br>".join(r["quotes"]) or "whole transcript"
        print(f'| {r["id"]} | {r["deal"]} | {r["name"]} | {quotes} | {r["expected"]} |')
