# Debrief: briefing for Cowork

Use this to understand the project and the attached screenshots. Everything here is a prototype on synthetic data. Apex and every customer in it are fictional.

## What it is

Debrief is a post-demo playbook for Enterprise technical validation (TV) demos at Apex, a fictional software company. Today, after a TV demo, nothing in the workflow tells the account executive (AE) or solutions consultant (SC) what to do next. Days spent in the TV stage rose from 12 to 14 to 18 over three quarters while other stages stayed flat. Debrief fills that gap and also works as a diagnostic: it records why people do or do not act, so the team can find the real cause of the stall.

Humans approve everything. Nothing is ever sent to a customer automatically.

## What it does, in three jobs

1. **Close the demo.** A four-line checklist the AE and SC fill in before leaving the call: a dated next step the customer agreed to, a named stakeholder to add, the customer's own business outcome, and anything the SC promised.
2. **After the demo.** It reads the call transcript plus CRM context and produces a call record, at most 3 ranked next steps, and three drafts: a recap email, an internal summary and a mutual action plan.
3. **Over time.** Reminders on a business-hours clock, a closing note back to the SC when the deal moves, and a handoff brief for the customer success manager (CSM) built from what was captured at TV.

## What is different from a call summary

Call recorders and CRMs already summarize calls and draft follow-ups, so Debrief treats those as commodity. The added parts are:
- **TV-stage playbook rules.** Every next step cites a playbook rule (PB-01 to PB-10) and must be something a typical AE would not do unprompted. Fewer than 3 steps is normal. Padding is not allowed.
- **SC commitments.** Promises made in passing ("I'll send you the release note") are pulled out, checked against what the checklist caught, given a due date and closed back to the SC.
- **A dismiss-reason diagnostic.** Each step has one-tap reasons: already done, waiting on customer, not relevant, no time. Over 30 days these show which of six candidate causes of post-demo inaction is real.
- **CS handoff from TV evidence.** The champion, stated outcome, objections and answers, open items and MEDDPICC gaps reach the CSM instead of being lost.

## How a debrief is produced

Seven model calls per debrief on Claude Sonnet 5.5, then code checks:
1. **Extract** (two calls, part A and part B, merged in code). Pulls out the business outcome, agreed next step, objections, open technical items, commitments, stakeholders, competitor mentions, signals, exact numbers, customer dependencies, contradictions, corrections and checklist mismatches. Every item carries evidence: an utterance ID and an excerpt.
2. **Assess and recommend.** Picks the deal state and at most 3 next steps. Deterministic rules then override it where they should (for example, a customer dependency with no date moves the state to "waiting on customer"). Overrides are logged.
3. **Drafts**, three in parallel: recap email, internal summary, mutual action plan.
4. **Verify.** Deterministic checks first, then a skeptical verifier call. A high-severity failure regenerates that draft once. If it still fails it is marked "needs review" and cannot be approved. The original is always kept.

MEDDPICC gaps are computed in code, not by the model. The extract step is split in two because the API rejected one large output schema ("compiled grammar is too large"). That is logged as decision D-14.

## Rules the system enforces

- The model never writes a quote that reaches the screen. Quotes, with speaker and timestamp, are rendered by code from the transcript.
- Evidence must resolve to a real utterance and a matching excerpt, or the output is retried once with the error as feedback.
- Every output field is required. At most 3 next steps. Short "why" fields only.
- Never present a metric target as a result. Never claim causation.
- Tests never use the network. Model output is recorded once and replayed from `fixtures/replay/`.

## Who sees what

- **AE:** the close-the-demo checklist, the debrief card with next steps, a "Why this step" toggle showing the transcript quote, and draft approval.
- **SC:** their commitments and open technical items, with a "Confirm record" button.
- **Sales manager:** coaching prompts, one question per deal for the next 1:1. It is explicitly not a scorecard.
- **CSM:** the handoff brief, a Phase 2 preview.
- **Measurement:** adoption, diagnostic and impact metrics. Thresholds are proposals, not agreed targets.

## The screenshots

All seven are from real recorded model output on one deal, Halvorsen Freight (deal_a), captured with the sample cards turned off. The footer reads "Source: saved".

| File | What it shows |
|---|---|
| 01_ae_close_the_demo_checklist | The four-line checklist before the call ends |
| 02_ae_card_next_steps | Deal state "Ready to advance" and ranked next steps with owner, due date, playbook rule and release card |
| 03_ae_why_this_step_with_transcript_quote | The "Why this step" toggle open, with two transcript quotes shown with speaker and time |
| 04_ae_recap_draft_for_approval | The recap email draft, open items, cost for the debrief and the Slack card |
| 05_sc_commitments_and_record | The SC view: open items table, commitments with due dates, Confirm record |
| 06_manager_coaching_prompts | Coaching prompts and touches in the 14 days after demo. Other deals show "no debrief yet" only because the capture script drove one deal |
| 07_measurement | The measurement tab, labeled synthetic example data |

## What was measured on the real run (2026-10-03)

One recording run, 5 synthetic deals, 76 live calls, none refused.
- **Cost:** mean $0.375 per debrief (range $0.220 to $0.490). Whole session $2.58 including judge, ablation and probes.
- **Latency:** summed call time averages 118 s per debrief. Critical path with parallel drafts is about 106 s, derived from per-call logs. End to end wall clock was not measured.
- **Cache:** reads were small, about 3.4k to 5.5k tokens per call, and the transcript prefix is not being reused across steps. The cause is unknown. Dollar savings are not measured.
- **Eval, 1 run per deal:** deal state matches on 3 of 5 deals, grounding passes on 3 of 5, the overclaim check passes on 4 of 5, steps pass on 5 of 5, and all trap and adversarial checks pass. Failing cases are in `evals/results.md` and are not fixed.
- **Verifier ablation:** with the verifier, planted errors caught were 5 of 5 on changed numbers (4 of 5 without), uncommitted promises (4 of 5 without), superseded features (0 of 5 without) and invented people (5 of 5 either way). It raised 1 false alarm on 5 clean drafts, none without.
- **LLM judge:** uncalibrated. Treat its verdicts as opinions.

## How to talk about it honestly

- These are one-run, small-sample numbers on 5 transcripts written to contain specific traps. They show the prototype works end to end, not that it performs in production.
- Win rate by days in TV is correlational and may run in reverse: weak deals stall and also lose. Do not claim Debrief causes faster deals or higher win rates.
- Gong, Salesforce and Slack are file-backed mocks. "Mark as sent" is a button, not an email integration.
- The two cards shown by `make demo` are hand-written samples and are labeled "Not generated from the call". The screenshots are not those.
- Known weak spots: deterministic checks are heuristics (they missed some planted problems in the stress test), and the cache behavior is unexplained.

## Where things live

- `README.md`: overview, diagnosis, measurement plan, demo script
- `DECISIONS.md`: mistakes the AI made and how they were fixed
- `evals/results.md` and `evals/ablation.md`: eval results
- `docs/API_NOTES.md`: what was verified against the live API
- `docs/screenshots/`: the images above
- Repo: https://github.com/rweisbac/Debrief, branch `claude/amazing-cerf-xmmxlf`, PR 2
