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

## Status

The first attempt on 2026-10-04 could not run: every API call returned 400 "Your credit balance is too low". See `results.md` for the current state.

## Rules followed

- Gold labels were written before any output was seen.
- Debrief was not changed after seeing results. Any later change is a separate, labeled run.
- Every failure is listed in `results.md`.
