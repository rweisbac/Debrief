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

## Prompt changes and why

None yet. Prompts start at v1 in checkpoint 2.

## Things I chose not to build and why

- Real integrations (Gong, Salesforce, Slack). Adapter interfaces with file-backed mocks keep the demo offline and safe. The production path is in the README.
- Auto-sending anything to customers. Every customer-facing draft needs a human approval. The consultative motion stays with the rep.
- An agent framework. The chain is 4 fixed stages in plain Python. The control flow is known in advance, so a framework would add risk without adding capability.
- A differentiation battlecard engine. That is Phase 3. For now Debrief only flags competitor mentions and points the SC to a release card.
- CS-side forecasting. The handoff brief is a Phase 2 preview built from TV evidence. Predicting time to first value would need post-sale data we do not have.

## What breaks first

To be filled in checkpoint 3, with the event signal for each.
