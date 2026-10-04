# Interview eval: Debrief vs a plain Claude call

Synthetic data, fictional companies. Built for interview prep. Debrief itself is unchanged by this folder.

## What is here

- `data/transcripts/e01.txt` to `e15.txt`: 15 hand-written post-TV calls for enterprise software deals. CRM and call-activity files come from `build_cases.py`.
- `gold_src.py`: gold labels written before any system ran. It resolves each text anchor to an utterance ID and writes `gold/<id>.json`. Totals: 35 stakeholder concerns, 29 open risks, 35 firm commitments, 16 hedged statements that must not be written as commitments, 23 items a good output should flag as uncertain, 41 reference next steps.
- `run.py`: runs Debrief (record mode, fixtures in `fixtures/replay`), the baseline, and the claim judge. Raw outputs land in `outputs/`.
- `score.py`: computes the 4 metrics and writes `results.md` and `results.json`.
- `prompts/baseline_v1.md`, `prompts/claim_judge_v1.md`: written before any result and not tuned.

## Hard cases

| Case | Hard case |
|---|---|
| e02 | Every customer action is hedged; no dated next step |
| e03 | VP and IT director contradict each other on seats, residency and freshness |
| e04 | The CISO who must sign off is absent; buyer unknown |
| e05 | Long rambling call, 83 turns; privacy concern buried mid call |
| e06 | EU-only legal rule and a spend freeze in the last minute |
| e09 | Low information; the only contact does not decide |
| e10 | SC promises a feature date the release card does not support |
| e11 | Enthusiastic contact, no commitment, budget owner absent |
| e12 | Same person says "sign by month end", then concedes board approval |
| e15 | CFO joins at the end with term and build vs buy objections |

e01, e07, e08, e13 and e14 are cleaner controls.

## How to run

```
python eval/build_cases.py      # CRM and activity files
python eval/gold_src.py         # gold labels
python eval/run.py debrief      # needs an API key with credit
python eval/run.py baseline
python eval/run.py judge
python eval/score.py
```

## Baseline

One `messages.create` call per transcript with the same model, the raw transcript and CRM record, and the generic prompt in `prompts/baseline_v1.md`. No schema, no effort setting, no playbook, no checks. It calls the SDK directly because it is the control arm; this is a deliberate exception to CLAUDE.md hard rule 1, kept inside `eval/`.

## Metrics

See the docstring in `score.py`. In short: (a) share of claims a blind judge marks supported, plus Debrief's deterministic evidence resolution; (b) gold risk recall by keyword; (c) overstated or fabricated commitments by the judge, plus gold hedged statements written as firm; (d) gold uncertain items that appear next to a hedge word.

## Status and verdict

Run on 2026-10-04 after an earlier attempt failed on API credit. All 15 cases ran for both systems with no errors. Total spend about $7.00: Debrief $4.80, baseline $0.58, judge $1.62. Numbers come from `results.md`; the hand classification comes from `hand_review.md`.

| Metric | Result | Verdict |
|---|---|---|
| (a) Claims the judge marks supported | 414 of 443 (93%) vs 529 of 567 (93%) | Tie |
| (a) Claims a rep can check against a cited line | 949 of 949 Debrief citations resolve; the baseline cites nothing | Debrief wins on checkability, not on accuracy |
| (b) Gold risk recall | 29 of 29 vs 29 of 29 | Tie. The keyword metric saturated and cannot tell the systems apart |
| (c) Overstated commitments, judge count | 23 vs 17 | Debrief loses on the raw count |
| (c) Same flags, hand classified as real | 6 vs 16 | Debrief better, post hoc and 1 reviewer. 16 of Debrief's 23 are recommendations with due dates |
| (c) Hedged statements written as firm, keyword | 2 of 16 vs 1 of 16 | Debrief slightly worse |
| (c) Uncommitted promises in the customer email | Debrief's recaps also contained them: 4 recaps, all blocked before approval. The baseline's emails held 9, with no gate | Debrief wins on what can be sent, hand review. Both systems write this error; only Debrief stops it |
| (d) Uncertain items flagged | 23 of 23 vs 22 of 23 | Tie |
| Cost per case | $0.320 vs $0.039 | Debrief costs about 8x |
| Wall clock per case, median | about 109 s vs 26 s, run 4 at a time | Debrief about 4x slower |
| Words a rep reads | 13,576 vs 16,677 | Debrief about 19% shorter |

Debrief failures found:
- The low-information rule overrode the deal state on 6 of 15 cases; only 1 was a low-information call by design.
- 6 of 14 blocked drafts were pure false alarms from the number and name checks ("one", "two", "Budget:", "Deferral:").

What this eval cannot show: anything about real calls, variance across runs, or whether the judge agrees with people.

## Next step comparison (run 2)

Script `next_steps.py`, results `next_steps_results.md`, cost $2.57. Debrief unchanged; its steps come from run 1.

| Test | Result | Reading |
|---|---|---|
| Blind head to head vs the generic baseline's first 3 steps | Debrief 13 wins, 2 ties, 0 losses | Debrief clearly better than a summarize-and-draft call |
| Blind head to head vs raw Claude asked for a ranked top 3 | Debrief 3, ties 5, raw 7 | Raw Claude preferred; judge reasons often say "covers more" |
| Same, raw cut to Debrief's step count (post hoc control) | Debrief 6, ties 4, raw 5 | Even once list length is matched |
| Rubric, steps judged acceptable | Debrief 22 of 33, raw top 3 15 of 45 | Debrief's steps pass the research rubric more often |
| Rubric, first step acceptable | Debrief 12 of 15, raw top 3 9 of 15 | Debrief's first step passes more often |

Verdict: against a raw call that is asked the right question, Debrief's recommendations are about even on blind preference and somewhat better on the research rubric. Both judges are uncalibrated and disagree, so this does not settle it. Debrief gave only 2 steps on 11 of 15 cases (its low-information rule cut 6 of those), which costs it coverage. A seller panel rating a blind sample is the test that would settle it.

## Rules followed

- Gold labels were written before any output was seen.
- Debrief was not changed after seeing results. Any later change is a separate, labeled run.
- Every failure is listed in `results.md`.
