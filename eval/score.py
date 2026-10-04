"""Score Debrief and the baseline on the 4 metrics and write eval/results.md and eval/results.json.

Synthetic data, fictional companies. Run: python eval/score.py

(a) Traceable claims: share of claims the blind judge marks supported by a transcript line or the CRM.
    Debrief also gets a deterministic number: share of its cited evidence that resolves to the transcript.
(b) Gold risk recall: a gold risk counts as found when one line of the output matches its keywords.
(c) Fabricated commitments: claims the judge marks overstated_commitment, plus a deterministic count of
    gold hedged statements (non_commitments) that appear in a commitments line with no hedge word.
(d) Low-confidence flagging: share of gold uncertain items that appear in a line that also carries a
    hedge word (unclear, not confirmed, depends, disagree, no date, open, and similar).

Keyword matching is a floor: it misses paraphrases and can match a passing mention. Both systems are
scored by the same code on the same text.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run import CASES, DATA, OUT, load, render_debrief, render_extraction  # noqa: E402
from src.transcript import load_transcript  # noqa: E402

GOLD = ROOT / "eval" / "gold"
HEDGE = re.compile(
    r"\b(unclear|not clear|unconfirmed|not confirmed|to be confirmed|to confirm|tbc|tbd|tentative|maybe|may|might|"
    r"possibly|probably|depends|depending|dependent|conditional|unless|disagree\w*|contradict\w*|conflict\w*|"
    r"differ\w*|unknown|not sure|unsure|uncertain\w*|open|pending|no date|undated|not dated|no firm|not firm|"
    r"not yet|hedg\w*|soft|vague|non-?committal|try|tries|trying|if|whether|unresolved|not committed|no commitment|"
    r"qualified|caveat\w*|lukewarm|not a decision|not agreed|no agreed|tbd)\b", re.I)


def gold(case: str) -> dict:
    return json.loads((GOLD / f"{case}.json").read_text(encoding="utf-8"))


def matches(keywords: list[list[str]], text: str) -> bool:
    t = text.lower()
    return all(any(term.lower() in t for term in group) for group in keywords)


def lines_of(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        out += [s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()] if len(line) > 300 else [line]
    return [l for l in out if l.strip()]


def section(text: str, word: str) -> list[str]:
    """Lines of the markdown section whose heading contains word (baseline output)."""
    # A heading is a markdown heading or a line that is bold from start to end. A numbered bold item such as
    # "1. **Correct the CRM:**" is content, not a heading (bug found in run 2, fixed before rescoring run 1).
    lines, grab, heading = [], False, re.compile(r"^\s*(#+\s|\*\*[^*]+\*\*:?\s*$)")
    for line in text.splitlines():
        if heading.match(line) and len(line) < 80:
            grab = word in line.lower()
            continue
        if grab and line.strip():
            lines.append(line)
    return lines


def commitment_lines(system: str, r: dict) -> list[str]:
    if system == "baseline":
        return section(r["text"], "commit")
    ex = r.get("extraction") or {}
    out = [f"{c['who']} will {c['what']} by {c['by_when'] or 'no date'}" for c in ex.get("commitments", [])]
    s = ((r.get("artifacts") or {}).get("internal_summary") or {}).get("current") or {}
    out += s.get("commitments", [])
    m = ((r.get("artifacts") or {}).get("mutual_action_plan") or {}).get("current") or {}
    out += [f"{row['milestone']} {row['target_date']} agreed" for row in m.get("rows", []) if row["status"] == "agreed"]
    return out


def evidence_resolution(r: dict, case: str) -> tuple[int, int]:
    """Deterministic: cited evidence that resolves, across extraction, final assessment and final drafts."""
    t = load_transcript(case, DATA / "transcripts")
    refs = []

    def walk(o):
        if isinstance(o, dict):
            if set(o) == {"utterance_id", "excerpt"}:
                refs.append(o)
            else:
                for v in o.values():
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(r.get("extraction"))
    for v in (r.get("artifacts") or {}).values():
        walk(v.get("current"))
    ok = sum(1 for e in refs if t.resolve_evidence(e["utterance_id"], e["excerpt"])[0])
    return ok, len(refs)


def score_case(case: str, system: str) -> dict:
    g, r = gold(case), load(system, case)
    if not r or r.get("status") != "ran":
        return {"case": case, "system": system, "status": "not_run",
                "reason": (r or {}).get("error", "no output")[:300]}
    text = render_debrief(r) if system == "debrief" else r["text"]
    full = text + "\n" + render_extraction(r) if system == "debrief" else text
    lines, full_lines = lines_of(text), lines_of(full)
    found = lambda kw, ls: any(matches(kw, l) for l in ls)  # noqa: E731

    risks = [{"id": x["id"], "found": found(x["keywords"], lines), "found_full": found(x["keywords"], full_lines)}
             for x in g["risks"]]
    concerns = [{"id": x["id"], "found": found(x["keywords"], full_lines)} for x in g["concerns"]]
    clines = commitment_lines(system, r)
    hedged_as_firm = [x["id"] for x in g["non_commitments"]
                      if any(matches(x["keywords"], l) and not HEDGE.search(l) for l in clines)]
    commits_found = [x["id"] for x in g["commitments"] if found(x["keywords"], clines)]
    uncertain = []
    for x in g["uncertain"]:
        hits = [l for l in full_lines if matches(x["keywords"], l)]
        uncertain.append({"id": x["id"], "mentioned": bool(hits), "flagged": any(HEDGE.search(l) for l in hits)})
    agreed_fab = False
    if system == "debrief" and g["agreed_next_step"]["exists"] is False:
        agreed_fab = bool((r.get("extraction") or {}).get("agreed_next_step", {}).get("exists"))

    j = load(f"judge_{system}", case)
    judge = None
    if j and j.get("status") == "ran":
        cl = j["claims"]
        judge = {"claims": len(cl), "supported": sum(c["supported"] for c in cl),
                 "overstated_commitments": sum(c["overstated_commitment"] for c in cl),
                 "overstated_list": [c["claim"] for c in cl if c["overstated_commitment"]],
                 "unsupported_list": [c["claim"] for c in cl if not c["supported"]],
                 "flagged_uncertain": sum(c["flagged_uncertain"] for c in cl)}
    out = {"case": case, "system": system, "status": "ran", "hard_cases": g["hard_cases"], "risks": risks,
           "concerns": concerns, "commitments_found": commits_found, "commitments_total": len(g["commitments"]),
           "hedged_as_firm": hedged_as_firm, "agreed_next_step_fabricated": agreed_fab, "uncertain": uncertain,
           "judge": judge, "cost_usd": r.get("cost_usd", 0), "words": len(text.split())}
    if system == "debrief":
        ok, n = evidence_resolution(r, case)
        out.update(evidence_ok=ok, evidence_total=n, errors=r.get("errors", []),
                   needs_review=[k for k, v in (r.get("artifacts") or {}).items() if v.get("needs_review")],
                   deal_state=((r.get("artifacts") or {}).get("assessment") or {}).get("current", {}) and
                   r["artifacts"]["assessment"]["current"]["deal_state"])
    return out


def pct(a: int, b: int) -> str:
    return f"{a} of {b} ({100 * a / b:.0f}%)" if b else "n/a"


def totals(rows: list[dict]) -> dict:
    ran = [r for r in rows if r["status"] == "ran"]
    js = [r["judge"] for r in ran if r["judge"]]
    t = {
        "ran": len(ran), "not_run": len(rows) - len(ran),
        "claims": sum(j["claims"] for j in js), "supported": sum(j["supported"] for j in js), "judged": len(js),
        "risks": sum(len(r["risks"]) for r in ran), "risks_found": sum(x["found"] for r in ran for x in r["risks"]),
        "risks_found_full": sum(x["found_full"] for r in ran for x in r["risks"]),
        "concerns": sum(len(r["concerns"]) for r in ran),
        "concerns_found": sum(x["found"] for r in ran for x in r["concerns"]),
        "overstated": sum(j["overstated_commitments"] for j in js),
        "hedged_as_firm": sum(len(r["hedged_as_firm"]) for r in ran),
        "non_commitments": sum(len(gold(r["case"])["non_commitments"]) for r in ran),
        "agreed_fab": sum(r["agreed_next_step_fabricated"] for r in ran),
        "uncertain": sum(len(r["uncertain"]) for r in ran),
        "uncertain_mentioned": sum(x["mentioned"] for r in ran for x in r["uncertain"]),
        "uncertain_flagged": sum(x["flagged"] for r in ran for x in r["uncertain"]),
        "commitments": sum(r["commitments_total"] for r in ran),
        "commitments_found": sum(len(r["commitments_found"]) for r in ran),
        "cost": round(sum(r["cost_usd"] for r in ran), 3), "words": sum(r["words"] for r in ran),
    }
    if ran and "evidence_ok" in ran[0]:
        t["evidence_ok"] = sum(r["evidence_ok"] for r in ran)
        t["evidence_total"] = sum(r["evidence_total"] for r in ran)
    return t


def write(results: dict) -> None:
    d, b = results["totals"]["debrief"], results["totals"]["baseline"]
    L = ["# Eval results: Debrief vs plain baseline", "",
         "Synthetic data, fictional companies. Generated by `eval/score.py`. Do not edit numbers by hand.", "",
         f"- Generated: {results['generated']}. Model: claude-sonnet-5-5. 1 run per case. 15 hand-written transcripts, gold labels written before any run.",
         f"- Ran: Debrief {d['ran']} of 15, baseline {b['ran']} of 15. Judged: Debrief {d['judged']}, baseline {b['judged']}.",
         "- The claim judge is a single uncalibrated model call per output (`eval/prompts/claim_judge_v1.md`), blind to which system wrote it, same model family as both systems.",
         "- A post hoc hand review of every judge flag and every Debrief block is in `eval/hand_review.md`. It changes no number here.",
         "", "## Headline", "",
         "| Metric | Debrief | Baseline |", "|---|---|---|",
         f"| (a) Claims the judge marks supported | {pct(d['supported'], d['claims'])} | {pct(b['supported'], b['claims'])} |",
         f"| (a) Debrief cited evidence that resolves (deterministic) | {pct(d.get('evidence_ok', 0), d.get('evidence_total', 0))} | not applicable, no citations |",
         f"| (b) Gold risks found, user-facing output | {pct(d['risks_found'], d['risks'])} | {pct(b['risks_found'], b['risks'])} |",
         f"| (b) Gold risks found, including Debrief's call record | {pct(d['risks_found_full'], d['risks'])} | same as above |",
         f"| (c) Commitment claims the judge marks overstated or fabricated | {d['overstated']} | {b['overstated']} |",
         f"| (c) Gold hedged statements written as firm commitments | {d['hedged_as_firm']} of {d['non_commitments']} | {b['hedged_as_firm']} of {b['non_commitments']} |",
         f"| (c) Agreed next step claimed when none was agreed (Debrief record field) | {d['agreed_fab']} | judged in row above |",
         f"| (d) Gold uncertain items flagged as uncertain | {pct(d['uncertain_flagged'], d['uncertain'])} | {pct(b['uncertain_flagged'], b['uncertain'])} |",
         f"| (d) Gold uncertain items mentioned at all | {pct(d['uncertain_mentioned'], d['uncertain'])} | {pct(b['uncertain_mentioned'], b['uncertain'])} |",
         f"| Secondary: gold concerns found | {pct(d['concerns_found'], d['concerns'])} | {pct(b['concerns_found'], b['concerns'])} |",
         f"| Secondary: gold commitments found in commitment lines | {pct(d['commitments_found'], d['commitments'])} | {pct(b['commitments_found'], b['commitments'])} |",
         f"| Cost for all cases (USD, from token counts) | ${d['cost']} | ${b['cost']} |",
         f"| Words of output a rep reads | {d['words']} | {b['words']} |", ""]
    L += ["## Per case", "",
          "| Case | Hard case | System | Supported claims | Risks found | Overstated (judge) | Hedged as firm | Uncertain flagged | Notes |",
          "|---|---|---|---|---|---|---|---|---|"]
    for case in CASES:
        for sysname in ("debrief", "baseline"):
            r = next(x for x in results["rows"] if x["case"] == case and x["system"] == sysname)
            if r["status"] != "ran":
                L.append(f"| {case} | | {sysname} | not run | | | | | {r['reason'][:80]} |")
                continue
            j = r["judge"]
            note = ""
            if sysname == "debrief":
                note = f"state {r['deal_state']}; needs review: {', '.join(r['needs_review']) or 'none'}"
                if r["errors"]:
                    note += f"; errors: {'; '.join(r['errors'])[:100]}"
            L.append(f"| {case} | {', '.join(r['hard_cases']) or 'none'} | {sysname} | "
                     f"{pct(j['supported'], j['claims']) if j else 'not judged'} | "
                     f"{sum(x['found'] for x in r['risks'])} of {len(r['risks'])} | "
                     f"{j['overstated_commitments'] if j else 'n/a'} | {', '.join(r['hedged_as_firm']) or '0'} | "
                     f"{sum(x['flagged'] for x in r['uncertain'])} of {len(r['uncertain'])} | {note} |")
    L += ["", "## Every failure", "", "Missed risks, hedged statements written as firm, unflagged uncertain items, and every claim the judge marked unsupported or overstated.", ""]
    for r in results["rows"]:
        if r["status"] != "ran":
            continue
        g = gold(r["case"])
        name = {x["id"]: x["summary"] for k in ("risks", "uncertain", "non_commitments") for x in g[k]}
        items = [f"missed risk {x['id']}: {name[x['id']]}" for x in r["risks"] if not x["found"]]
        items += [f"hedged written as firm {h}: {name[h]}" for h in r["hedged_as_firm"]]
        items += [f"uncertain not flagged {x['id']}: {name[x['id']]}" for x in r["uncertain"] if not x["flagged"]]
        if r["agreed_next_step_fabricated"]:
            items.append("record says a next step was agreed; gold says none was")
        if r["judge"]:
            items += [f"judge unsupported: {c}" for c in r["judge"]["unsupported_list"]]
            items += [f"judge overstated commitment: {c}" for c in r["judge"]["overstated_list"]]
        if items:
            L.append(f"### {r['case']} {r['system']}")
            L += [f"- {i}" for i in items] + [""]
    L += ["## Method limits", "",
          "- 15 synthetic transcripts written by the same person who wrote the gold labels. Not independent.",
          "- 1 run per case per system. No variance estimate.",
          "- The judge is uncalibrated and from the same model family. Its supported and overstated calls were not hand checked except where noted in `eval/README.md`.",
          "- Keyword matching is a floor for recall and flagging; a hedge word near a keyword is a loose proxy for a real flag.",
          "- The baseline prompt was written before any result and was not tuned. Debrief was not changed for this eval.", ""]
    (ROOT / "eval" / "results.md").write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    rows = [score_case(c, s) for c in CASES for s in ("debrief", "baseline")]
    results = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "rows": rows,
               "totals": {s: totals([r for r in rows if r["system"] == s]) for s in ("debrief", "baseline")}}
    (ROOT / "eval" / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    write(results)
    print(json.dumps(results["totals"], indent=1))


if __name__ == "__main__":
    main()
