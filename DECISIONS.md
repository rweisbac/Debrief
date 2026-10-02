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
- Evidence of fix (eval or test, before and after): tests/deterministic/test_chain.py::test_cached_prefix_identical_across_steps, test_llm.py::test_step_rules_placement and test_real_sdk_backend_request_shape. Not live-verified: smoke probe (f) is pending a key. The output schema also changes per step and may invalidate the cache anyway; only measured cache_read_input_tokens will be reported.
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

## Prompt changes and why

All prompts are at v1 (checkpoint 2). No changes yet: nothing has run against the model, so there is no evidence to change them on. Each future change gets a new v<N> file and an entry here naming the eval result that motivated it.

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

## What breaks first

In likely order, with the event that shows it (also in the README):

1. Checks flag good model drafts, because they were only tested on hand-written outputs (D-11). Signal: verifier_flagged and rule_override_applied per debrief, and flagged drafts approved unedited.
2. Steps feel generic and get dismissed. Signal: step_dismissed with reason not_relevant above the agreed rate.
3. Reps do not open the card in the channel it arrives in. Signal: card_ignored_24h.
4. Nudges become noise. Signal: nudge_sent without nudge_acted_on.
5. The SC stops confirming the record once novelty fades. Signal: record_confirmed_by_sc within 1 business day trending toward the 60% baseline.
6. Upstream formats change (Gong transcript shape, CRM fields). Signal: parse errors and evidence_resolves failures.
7. A model or SDK update changes behaviour. Signal: eval pass rates and the smoke test on every bump.
