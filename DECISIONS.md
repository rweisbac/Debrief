# Decisions

Synthetic data, fictional company. Entries use docs/DECISIONS_TEMPLATE.md.

## What I asked the AI to build

Debrief, a post-demo playbook for Enterprise technical validation (TV) demos at fictional Apex. It has 3 jobs: a close-the-demo checklist, a structured record with at most 3 ranked next steps and drafts after the demo, and nudges, SC loop closure and a CS handoff over time. It doubles as a diagnostic: dismiss reasons show which of 6 candidate causes of post-demo inaction is real. Humans approve everything. Built in 4 checkpoints with a review stop after each.

## Where the AI output was wrong and how I corrected it

## D-01: live smoke test not yet run
- Step and prompt version: checkpoint 0, scripts/smoke_test.py
- What the AI produced: a smoke test with 6 live probes and an offline section.
- Why it was wrong: not wrong, but incomplete. No ANTHROPIC_API_KEY in the build environment on 2026-10-02, so the live probes were skipped.
- What I changed: added offline checks against the installed SDK (1.11.0) using a mock transport. They confirm the SDK sends `output_config = {effort, format}` in one request and parses JSON when a thinking block comes first. docs/API_NOTES.md marks every API-level claim as "pending live run".
- Evidence of fix (eval or test, before and after): docs/smoke_results.json, status "skipped", offline section all true.
- What I would do in production: run the smoke test in CI on every SDK or model bump, and block deploys when a probe changes.
- Update 2026-10-03: the live smoke test has since been run, and the recording run exercised the same calls in the full chain. Results are in docs/API_NOTES.md. Still open: running the smoke test in CI.

## D-02: refusal fallbacks left off (skill vs prompt conflict)
- Step and prompt version: checkpoint 0, src/llm.py design
- What the AI produced: the claude-api skill recommends enabling the server-side `fallbacks: "default"` parameter by default for claude-sonnet-5-5 code.
- Why it was wrong: it conflicts with the brief. On refusal: log, surface in the UI, do not retry. A server-side fallback is a silent retry on another model. It would also make the model in the replay key differ from the model that produced the output.
- What I changed: no `fallbacks` parameter. Refusals are logged with stop_details and shown as "needs review".
- Evidence of fix (eval or test, before and after): reviewer rule R3 and R6; llm.py test for refusal handling (checkpoint 2).
- What I would do in production: revisit with sales ops. If refusals turn out to be false positives on normal sales content, enable fallbacks and log the serving model per call.

## D-03: lifelines dropped, Kaplan-Meier hand-rolled
- Step and prompt version: checkpoint 0, requirements.txt
- What the AI produced: lifelines in requirements.txt.
- Why it was wrong: lifelines failed to install (its autograd-gamma dependency would not build in this environment).
- What I changed: removed it. The brief allows a hand-rolled Kaplan-Meier; src/metrics.py will implement it, with a censored hand-computed test.
- Evidence of fix (eval or test, before and after): `pip install -r requirements.txt` succeeds.
- What I would do in production: use lifelines or scipy in a pinned analysis environment and cross-check against the hand-rolled version.

## D-04: presidio not installed
- Step and prompt version: checkpoint 0, environment
- What the AI produced: an attempt to install presidio-analyzer and presidio-anonymizer.
- Why it was wrong: the install failed on a system PyYAML conflict. Presidio also needs a spaCy model download.
- What I changed: left presidio optional. Log redaction is a no-op unless presidio imports, and the UI and README say so.
- Evidence of fix (eval or test, before and after): llm.py logs work without presidio (checkpoint 2 test).
- What I would do in production: install presidio in the container image with a pinned spaCy model, and test that redaction runs on logs only.

## D-05: style checker contained the character it bans
- Step and prompt version: checkpoint 0, scripts/check_style.py
- What the AI produced: the em dash constant written as an escape inside a shell heredoc. The shell turned it into a literal em dash in the file.
- Why it was wrong: it broke the no em dash rule. The new style test caught it on its first run.
- What I changed: the constant is now built with chr(0x2014).
- Evidence of fix (eval or test, before and after): tests/deterministic/test_style.py failed with scripts/check_style.py:10, then passed. The hook exited 2 on a planted bad file in src/ and 0 on a clean edit.
- What I would do in production: keep the check in CI and pre-commit.

## D-06: fuzzy evidence match let a changed number through
- Step and prompt version: checkpoint 1, src/transcript.py resolve_evidence (no prompt yet)
- What the AI produced: evidence resolution exactly as specified: normalized substring, or rapidfuzz partial_ratio >= 95.
- Why it was wrong: "5 billion events a month" scored above 95 against "4.7 billion events a month" because only one character differs. A misquoted number would have been rendered as grounded, which is exactly what trap T5 tests.
- What I changed: a fuzzy match now also requires every number in the excerpt to appear exactly in the utterance. Substring matches are unchanged.
- Evidence of fix (eval or test, before and after): tests/deterministic/test_transcript.py::test_evidence_fails failed on the changed number before the fix and passes after. Regression test tests/regressions/test_r01_fuzzy_number_drift.py.
- What I would do in production: keep the exact number rule, and log the fuzzy score per evidence ref to see how often fuzzy matching is needed at all.

## D-07: step rules sent as a mid-conversation system message (prompt layout conflict)
- Step and prompt version: checkpoint 2, src/llm.py build_request, all steps v1
- What the AI produced: the brief asks for two things that conflict under the API's render order (system, then messages): "schema and rules go in the system prompt" and "playbook, release cards, competitor notes, then transcript, then step instructions".
- Why it was wrong: putting step rules in the top-level system prompt places them before the transcript. That changes the prefix per step, so the transcript cannot be cached across the 6 calls.
- What I changed: top-level system holds only the stable reference (preamble, playbook, release cards, competitors) with cache_control. The user turn holds the transcript and CRM (cached) and then step data. The step rules follow as a {"role": "system"} message in messages, which the claude-api skill documents for Sonnet 5.5. A config switch, DEBRIEF_STEP_RULES_PLACEMENT=top_system, falls back to the plain layout.
- Evidence of fix (eval or test, before and after): tests/deterministic/test_chain.py::test_cached_prefix_identical_across_steps, test_llm.py::test_step_rules_placement and test_real_sdk_backend_request_shape. Update 2026-10-03: the default placement was accepted live on all 76 calls, so the fallback was not needed. The output schema also changes per step and may invalidate the cache anyway; only measured cache_read_input_tokens will be reported. Measured: calls read about 3.4k to 5.5k tokens (zero on the first deal) while writing 6.7k to 11k new tokens, so the transcript prefix is not shown to be reused across steps. Cause not established.
- What I would do in production: confirm with probe (f) and the measured cache reads, and keep whichever layout reads more cached tokens.

## D-08: messages.parse hides stop_reason on truncated output
- Step and prompt version: checkpoint 2, src/llm.py
- What the AI produced: a first design that read stop_reason from the parse() result.
- Why it was wrong: in SDK 1.11.0, parse() raises a pydantic ValidationError when the JSON is cut off at max_tokens. The response, with its stop_reason and usage, is lost, so the "retry once at 2x max_tokens" rule could never fire, and the tokens were never logged. with_raw_response has no parse().
- What I changed: the HTTP client has a response hook that stores each raw body under a per-call header. parse() is still the only call. On a ValidationError the raw body supplies stop_reason and usage. The same raw body is what record mode saves as the fixture.
- Evidence of fix (eval or test, before and after): test_llm.py::test_real_sdk_backend_request_shape drives the real SDK over a mock transport. A truncated first response is retried at 2x max_tokens and logged.
- What I would do in production: ask for an SDK option that returns the message alongside the parse error, then drop the hook.

## D-09: deterministic checks raised false alarms on clean drafts
- Step and prompt version: checkpoint 2, src/checks.py
- What the AI produced: a name check that flagged "Send Elena" as an unknown person (a sentence-initial verb), and a number check that read playbook IDs like PB-03 as the number 03.
- Why it was wrong: every clean debrief would have been sent for regeneration, doubling cost and marking good drafts as needing review.
- What I changed: ID and enum fields are skipped by the number check, and date fields are checked by the date check instead. The name check accepts a word that appears anywhere in the transcript or CRM (case-insensitive) or in the roster. This is a heuristic: an invented name made of common words can slip through, and the LLM verifier is the second line.
- Evidence of fix (eval or test, before and after): tests/deterministic/test_rules_checks.py::test_clean_artifacts_pass failed, then passed. test_chain.py clean path is 6 calls. test_invented_person_caught and test_changed_number_caught still pass.
- What I would do in production: track the false alarm rate per check from the verifier_flagged events, and tighten or retire any check above an agreed rate.

## D-10: superseded feature eval was phrase-blind
- Step and prompt version: checkpoint 2, evals/scoring.py trap T4
- What the AI produced: a T4 check that failed any draft containing "hourly sync".
- Why it was wrong: it failed a correct internal summary line, "Hourly sync: continuous sync now, resolved", which reports the correction rather than presenting hourly as current.
- What I changed: the check is sentence-level. A sentence with an old-behavior phrase fails only if it does not also signal the change (continuous, no longer, used to, changed, and so on).
- Evidence of fix (eval or test, before and after): tests/deterministic/test_evals.py::test_trap_scoring_deal_a failed, then passed. test_superseded_phrase_fails_trap still fails "The connector syncs hourly."
- What I would do in production: back the phrase check with the verifier's superseded_feature_as_current verdict and review disagreements by hand.

## D-11: stress test of checks and scorers, and fixes
- Step and prompt version: checkpoint 2, src/checks.py, src/rules.py, evals/scoring.py (no prompt change)
- What the AI produced: the deterministic checks and eval scorers from D-07 to D-10. An independent agent planted 61 problems and 17 clean variants against them (tests/stress, evals/stress_report.md).
- Why it was wrong: they caught 31 of 61 and raised 7 false alarms. The worst gaps: overclaims scored as passing when the verifier had not run; polite chases ("circle back", "remind Aisha") survived R-CHASE and trap T6; a number passed if it appeared anywhere in the sources, so 38,000 rounded to 40,000 passed, and a CRM timestamp vouched for "47 billion"; a meeting moved from Oct 8 to Oct 9 passed; the name check flagged "Flag Lakestream" and missed invented stakeholders in the extraction.
- What I changed: overclaim and grounding scorers report "not run" as a failure. New no_unsupported_claims check for savings, guarantee and ROI claims. Wider chase patterns, and T6 requires the top step not to be a chase. Number check strips timestamps, phones, IDs and dates, reads number words and bn or k suffixes, and flags a number whose surrounding words match a different number with the same unit. Recap and internal summary dates must be dates said in the call, and relative dates are flagged. The name check uses proper nouns from the sources plus an English word list (wordfreq, sentence-initial words only) and also runs on the extraction. score_steps accepts lowercase rule IDs.
- Evidence of fix (eval or test, before and after): caught 31 of 61 before, 49 of 61 after; false alarms 7 of 17 before, 1 of 17 after; 24 GAP markers removed because the tests now pass. All earlier tests still pass (204 passed, 13 xfailed).
- What I would do in production: the stricter checks are untested on real model output. Watch the verifier_flagged and rule_override_applied events for a rise in false alarms after the first recording, and loosen any check that fires on drafts a human approves unedited.

## D-14: reviewer pass over the full diff, and what I changed
- Step and prompt version: checkpoint 3, all code; draft_recap_email v1 to v2
- What the AI produced: the code reviewed by the read-only reviewer subagent (.claude/agents/reviewer.md) against rules R1 to R22. It found 1 violation and 5 possible issues.
- Why it was wrong:
  - R1: a test built an SDK client itself.
  - R18: a rewritten draft whose re-verify call failed could still be one-tap approved.
  - R13: the recap prompt asked for the customer's words, and nothing checked quoted text in drafts.
  - The README said 13 open gaps without explaining that this is 12 misses plus 1 false alarm.
- What I changed:
  - AnthropicBackend now takes an optional test transport and builds the client itself. No file outside src/llm.py and scripts/smoke_test.py constructs a client.
  - A failed re-verify now marks the draft needs review, with a flag.
  - A new check, quotes_in_transcript, runs on all drafts.
  - draft_recap_email v2 drops quotation marks.
  - README wording fixed.
- Evidence of fix (eval or test, before and after): test_chain.py::test_regenerated_draft_needs_review_when_reverify_fails and test_rules_checks.py::test_quoted_text_must_be_in_transcript are new and pass. A grep for AsyncAnthropic outside src/llm.py and the smoke test finds nothing. 235 passed, 13 xfailed.
- What I would do in production:
  - Kept as is, with the reasons: SDK transport retries (max_retries=2, on 429, 5xx and connection errors). These are not model retries: no output was seen, so the "retry only on max_tokens or a validator" rule does not apply. They are not logged per attempt, because the SDK hides them; the latency shows them.
  - Also kept: a reply that does not parse against the schema is treated as a failed validator (one retry with the parser error as feedback).
  - The top_system fallback breaks the cache order and stays a documented fallback only (D-07).
  - Still open: extraction validator failures after retry are recorded as errors but do not mark anything needs review. Today no extraction quote is shown in the UI.

## Prompt changes and why

All prompts started at v1 (checkpoint 2). Each change gets a new v<N> file and an entry here.

- draft_recap_email v2 (checkpoint 3, D-14): asks for no quotation marks, so the model cannot put words in the customer's mouth. Exact quotes are rendered by the app from the transcript. Motivated by the reviewer finding, not by an eval result (no recording exists yet).
- assess_and_recommend v2 (D-15): each step is the 10 minute first move; routine post-demo steps do not qualify on their own. Motivated by run 1 judge results.
- assess_and_recommend v3, draft_recap_email v3, judge v2 (D-17): rebuilt from the best practice research; behind DEBRIEF_BEST_PRACTICE=1 until recorded.
- capture v1 (D-16): new step for the post-demo confirm card.
- extract v3 (D-15): customer stakeholders only; open items cite the line where raised. Motivated by run 1 precision and open item recall.

## Things I chose not to build and why

- Real integrations (Gong, Salesforce, Slack). Adapter interfaces with file-backed mocks keep the demo offline and safe. The production path is in the README.
- Auto-sending anything to customers. Every customer-facing draft needs a human approval. The consultative motion stays with the rep.
- An agent framework. The chain is 4 fixed stages in plain Python. The control flow is known in advance, so a framework would add risk without adding capability.
- A differentiation battlecard engine. That is Phase 3. For now Debrief only flags competitor mentions and points the SC to a release card.
- CS-side forecasting. The handoff brief is a Phase 2 preview built from TV evidence. Predicting time to first value would need post-sale data we do not have.

## D-12: demo runs on hand-written sample cards until a recording exists
- Step and prompt version: checkpoint 3, scripts/build_samples.py, app.py
- What the AI produced: a choice between an empty demo (no API key, so no fixtures) and showing hand-written outputs.
- Why it was wrong: an empty demo cannot show the flow, but hand-written outputs presented as model output would misrepresent the prototype.
- What I changed: two hand-written sample debriefs (deal_a, deal_b) run through the real rules, MAP enforcement and checks via a scripted backend, and must pass every check. They are stored as source "sample" and every view, the Block Kit JSON and the card footer label them "Sample card written by hand to show the layout. Not generated from the call." The app prefers a real saved or replayed debrief whenever one exists.
- Evidence of fix (eval or test, before and after): tests/app/test_app_walkthrough.py::test_sample_label_shown and test_cp3_units.py::test_samples_are_labeled_and_pass_checks.
- What I would do in production: delete the samples after the first recording.

## D-13: a test expectation was wrong, not the code
- Step and prompt version: checkpoint 3, tests/deterministic/test_cp3_units.py
- What the AI produced: a boundary test asserting that 20 of 66 non-actions with 20 events does not meet the 30% and 20 event rule.
- Why it was wrong: 20 of 66 is 30.3% with exactly 20 events, so it meets both conditions. The code was right.
- What I changed: the test now asserts the boundary case meets the rule, and adds explicit cases for exactly 30% and for 19 events.
- Evidence of fix (eval or test, before and after): the test failed, then passed with metrics.diagnose unchanged.
- What I would do in production: keep boundary tests next to every pre-declared decision rule.

## D-14: one extraction schema was too large for the API grammar
- Step and prompt version: extract v1, then extract v2 and extract_b v1
- What the AI produced: a single `ExtractionRecord` output schema with 15 fields and 13 nested evidence lists, sent in one call. It passed all offline tests.
- Why it was wrong: the first live call failed with 400 "The compiled grammar is too large". Offline tests use a fake backend and cannot see the API's schema limit.
- What I changed: the extraction is requested in two parts (`ExtractionPartA`, `ExtractionPartB`), run one after the other and merged in code into the same `ExtractionRecord`, so downstream steps are unchanged. Chain is now 7 calls per debrief. Prompts bumped to extract v2 and extract_b v1.
- Evidence of fix (eval or test, before and after): before, 400 on the first live call (deal_a). After, both parts parsed with no validator errors on all 5 deals. tests/regressions/test_extraction_split.py keeps the merged schema out of the request path and the merge lossless. Cost: two extract calls at about $0.065 each on deal_a.
- What I would do in production: run the live smoke test on every schema change, since only the live API enforces this limit.

## D-15: first recorded run showed weak steps, a forced deal state and two approvable errors
- Step and prompt version: assess_and_recommend v1 to v2, extract v2 to v3, src/rules.py R-WAIT, src/chain.py, src/checks.py, evals/scoring.py
- What the AI produced: run 1 (2026-10-03, `evals/history/results_run1_2026-10-03.md`). The uncalibrated judge passed 1 of 13 next steps: 10 failed "doable in 10 minutes" and 8 failed "non-obvious". R-WAIT forced deal_b to waiting_on_customer although Apex still owed the written SSO design. On deal_c the verifier rated an uncommitted promise in the recap ("We will come back with a plan") medium, so the recap stayed one-tap approvable, and the rewritten internal summary kept 2026-10-09, a date nobody said, because the date check was medium. The eval table read "Needs review: none" next to grounding FAIL because the scorer only reads first drafts.
- Why it was wrong: steps were whole deliverables (an onboarding plan, a pricing range) or routine moves (send the recap, flag the competitor). A deal is not waiting on the customer while Apex owes an open item. A promise nobody made in the call must never be one-tap approvable in the customer email.
- What I changed:
  - assess_and_recommend v2: each step is the 10 minute first move that starts the bigger deliverable; routine post-demo steps do not qualify on their own.
  - extract v3: customer stakeholders only; open items cite the line where the question was raised.
  - R-WAIT does not fire when an Apex participant owns an open technical item.
  - email_promises_uncommitted on the recap blocks approval at any verifier severity.
  - Dates not said in the call are high severity in the recap and internal summary.
  - The eval table shows grounding for the first draft and the final draft (pass, blocked, or FAIL when a problem reaches an approvable draft). Run 1 results are kept in `evals/history/`.
- Evidence of fix (eval or test, before and after): run 2, 1 run per deal, $2.47 over 76 live calls, none refused.
  - Judge: 1 of 13 steps passed before, 4 of 11 after. Failing "10 minutes": 10 of 13 before, 5 of 11 after. Failing "non-obvious": 8 of 13 before, 4 of 11 after. The judge is uncalibrated and v2 was written after reading its critiques, so this can be teaching to the judge until hand labels exist.
  - Deal state: 3 of 5 before, 4 of 5 after (deal_b now open_technical_gap; R-WAIT did not fire).
  - Final grounding: no grounding failure reached an approvable draft on any deal; deal_c's internal summary is blocked for review.
  - Open item recall 6 of 10 to 8 of 10; stakeholder precision 19 of 25 to 19 of 21.
  - Regressions: commitment recall 23 of 23 to 22 of 23 (missed deal_b "write down anything security related for Raj"); objection recall 9 of 12 to 8 of 12; trap T6 on deal_b now fails because the top step is the SSO answer, not the security packet; deal_b's recap is now blocked by a likely false alarm (the verifier called the written SSO design uncommitted, but the customer asked for it in U058 and U059 and Marcus took it on in U073). Mean cost per debrief rose from $0.375 to $0.409.
  - Ablation: false alarms on clean drafts 1 of 5 before, 0 of 5 after; planted errors caught with the verifier 20 of 20 both times.
  - Tests: tests/regressions/test_r02_recorded_run_gates.py.
- What I would do in production: run 3 or more runs per deal before reading any change, because one run per deal cannot separate a prompt effect from sampling noise. Hand-label the judge set before tuning prompts against it again. Track how often the recap promise gate blocks drafts a rep then sends unedited; that is the false alarm rate for this rule. Still open: deal_c's gold label says competitive_risk, but the prompt tells the model to use waiting_on_customer when a customer process has no date, and Ben deferred with no date. The label and the prompt disagree; the product owner should decide which is right rather than tuning the model to the label.

## D-16: post-demo capture ("confirm, don't write") replaces the in-call checklist
- Step and prompt version: capture v1 (new), src/capture.py, src/slack_actions.py, src/web.py
- What the AI produced: a capture design brief (from a Claude Cowork agent) asking for a separate FastAPI app with its own extraction call, the model's self-reported confidence as the routing score, code fence stripping with a retry on parse failure, and a "ready-to-send" follow-up email.
- Why it was wrong: a second app would duplicate the debrief pipeline; a model's own confidence is poorly calibrated; this repo uses structured outputs (no fences) with at most 1 retry; and nothing is sent to a customer without approval. The in-call checklist it replaces was also unrealistic: reps are presenting, not typing.
- What I changed:
  - The capture step runs inside the existing pipeline after the debrief, on the same cached prefix, and pre-fills 4 fields: priority and why now, champion and economic buyer, top risk, next step.
  - Confidence is computed in code: the model's probability capped by checkable signals (no basis, unmatched evidence, inferred, CRM disagreement, top risk other, a date not said in the call).
  - Routing: auto-confirm at 0.90; champion and top risk always asked for each AE's first 20 confirms; a 10% spot check on confident fields so the error rate among auto-confirmed fields is measured; an unsaid date is never auto-confirmed.
  - The card is a real interactive Slack message (menus, edit modals, Confirm all) through a signed /slack/interactions endpoint, with the same card on the web for demos and non-Slack users. The debrief card's act and dismiss buttons now work in Slack too.
  - Confirmed fields are written to the CRM opportunity through an adapter. Every confirm is stored as labels for per-field accuracy, calibration by confidence bucket, auto-confirm rate, questions per meeting and time to confirm, plus a threshold simulator.
  - The AE's confirmed fields feed the next steps and drafts on a rerun (live mode), only when present, so recorded replay keys do not change.
  - 7 new synthetic deals (12 in all, 3 per bucket) with capture ground truth, a scorer and a seed script with a simulated AE that is labeled simulated everywhere.
- Evidence of fix (eval or test, before and after): tests/deterministic/test_capture.py, test_web.py, test_capture_gold.py, test_best_practice.py, test_ingest.py (capture card first; a failed capture never blocks the debrief card). No capture output is recorded yet (the owner asked to hold recording until best practice was drafted); the demo uses 2 hand-written sample captures labeled as samples and scored by the real code.
- What I would do in production: record capture output and run `scripts/seed_capture.py --mode record`; then replace simulated confirms with real ones and set the threshold from the calibration table, not from 0.90.

## D-17: next steps, recap and judge rebuilt from best practice research
- Step and prompt version: data/playbook_v2.md, assess_and_recommend v3, draft_recap_email v3, judge v2 (behind DEBRIEF_BEST_PRACTICE=1)
- What the AI produced: judge v1 graded steps on criteria I chose ("doable in 10 minutes", "a typical AE would not do it unprompted"), and assess_and_recommend v2 was tuned to that judge (D-15).
- Why it was wrong: the deep research (`docs/research/best_practice_findings.md`) found "doable in 10 minutes" penalizes the highest-value steps (a complete security packet, a phased plan) and "would not do it unprompted" cannot be observed by a grader. The playbook also missed 3 high-value moves: a mutual action plan, handling indecision, and recaps written for absent stakeholders. Tuning prompts to an unvalidated judge risked teaching to the judge.
- What I changed:
  - Playbook v2 amends PB-01 to PB-10 and adds PB-11 to PB-16 (deferral path, draft mutual action plan, technical win in writing, indecision, internal disagreement, low information), each with its evidence and strength, plus an explicit baseline hygiene list.
  - assess_and_recommend v3 ranks by the binding constraint and follows the research rubric; it drops the 10 minute rule and adds deal state precedence (an incumbent that is the default alternative is competitive_risk even when the customer deferred). That settles the deal_c label question from D-15 in favor of the gold label.
  - draft_recap_email v3 is written to be forwarded, under 120 words.
  - Judge v2 grades R1 to R8: acceptable when R1, R2, R4, R5 and R6 pass, strong when R3 and R7 also pass.
  - The research's reference answers are data (`data/reference_steps/`) with a keyword coverage score that needs no model calls, and a judge check: judge v2 must pass the must-have steps, fail the wrong ones and fail R7 on routine ones before it is trusted.
  - Everything sits behind DEBRIEF_BEST_PRACTICE=1, because the playbook is in the cached prefix of every call and changing it in place would break every recorded fixture and the demo before a re-record.
- Evidence of fix (eval or test, before and after): baseline with the recorded run 2 (profile off), `evals/reference_results.md`: must-have steps covered 10 of 15 (keyword floor), 0 steps matching a wrong step, 1 routine-only step, deal state agrees with the research on 4 of 5 (deal_c is the miss). After: not measured; needs a recording with the profile on. Tests: tests/deterministic/test_reference.py (the keyword floor had 2 negation false positives, "no week estimates" and "without writing a legal opinion", caught by a test that good reference steps never trip a wrong pattern), test_best_practice.py.
- What I would do in production: record with the profile on, run `evals/reference.py judge` and `evals/reference.py coverage`, make the profile the default if coverage rises without new wrong steps, and replace keyword matching with an LLM matcher checked against these labels. Then calibrate on outcome data as the research's open questions describe.

## What breaks first

In likely order, with the event that shows it (also in the README):

1. Checks flag good model drafts, because they were only tested on hand-written outputs (D-11). Signal: verifier_flagged and rule_override_applied per debrief, and flagged drafts approved unedited.
2. Steps feel generic and get dismissed. Signal: step_dismissed with reason not_relevant above the agreed rate.
3. Reps do not open the card in the channel it arrives in. Signal: card_ignored_24h.
4. Nudges become noise. Signal: nudge_sent without nudge_acted_on.
5. The SC stops confirming the record once novelty fades. Signal: record_confirmed_by_sc within 1 business day trending toward the 60% baseline.
6. Upstream formats change (Gong transcript shape, CRM fields). Signal: parse errors and evidence_resolves failures.
7. A model or SDK update changes behaviour. Signal: eval pass rates and the smoke test on every bump.
