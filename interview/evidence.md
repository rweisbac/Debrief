# Debrief evidence file

Facts from the repo only. Every line has a path or a commit. Audited on branch `claude/charming-brown-jc9s3d` at commit `01c51e2`, 34 commits in history.

Labels: [repo] means a file or commit in this repo. [eval] means a results file. Anything else is marked.

## What it is

- Debrief is a post-demo playbook for the window right after an Enterprise technical validation (TV) demo at a fictional company called Apex. All data is synthetic. [repo] `README.md`, `CLAUDE.md`
- It does 3 jobs: a confirm card the account executive (AE) fills in about 30 seconds, a debrief after the demo, and nudges, loop closure and a customer success (CS) handoff over time. [repo] `README.md` intro
- Stack: Python 3.11, the Anthropic SDK 1.x, pydantic v2, Streamlit, FastAPI, SQLite, rapidfuzz, pytest. No agent or orchestration framework. [repo] `CLAUDE.md`, `requirements.txt`

## Inputs

- Call transcript as text with a participants header (name, title, apex or customer) and timestamped turns. Parsed into numbered utterances U001 to Unnn. [repo] `src/transcript.py` `parse_transcript`
- CRM opportunity as JSON: account, stage, ACV (annual contract value), AE, SC (solutions consultant), contacts, champion, economic buyer, discovery notes, prior calls, competitors, demo times, close-the-demo checklist. [repo] `data/crm/deal_x.json`
- Gong-shaped call activity as JSON. [repo] `data/gong_activity/`
- Shared reference sent on every call: playbook (PB-01 to PB-10, or 16 rules in v2), 7 release cards (RC-07 to RC-14), 2 competitor notes (Lakestream, Quarrylane). [repo] `src/prompts.py` `stable_reference`, `data/playbook.md`, `data/release_cards.json`, `data/competitors.json`
- 12 synthetic transcripts: 5 debrief deals with planted traps (deal_a, deal_b, deal_c, deal_x, deal_y) and 7 shorter capture deals (deal_d to deal_j). [repo] `data/transcripts/`, `README.md` "Known limits"
- Sources are file-backed mocks. Gong, Salesforce and Slack are not connected to real systems. [repo] `src/adapters.py` docstring, `README.md` "Known limits and what is mocked"

## Outputs

- Extraction record with 15 fields: business outcome, agreed next step, objections, open technical items, integration patterns, commitments, stakeholders, competitor mentions, buying signals, risk signals, exact numbers, customer dependencies, contradictions, corrections, checklist mismatches. Every list item carries evidence (utterance ID plus excerpt). [repo] `src/schemas.py` `ExtractionRecord`
- Assessment: 1 of 6 deal states, at most 3 ranked next steps, each with owner, due date, playbook rule ID, action type, a "why" of 25 words or fewer, and evidence. [repo] `src/schemas.py` `Assessment`, `NextStep`
- 3 drafts: customer recap email, internal summary, mutual action plan (MAP). [repo] `src/schemas.py`, `src/chain.py` `DRAFT_STEPS`
- MEDDPICC view (metrics, economic buyer, decision criteria, decision process, paper process, pain, champion, competition) computed in code, not by the model. [repo] `src/meddpicc.py`, `src/schemas.py` `MeddpiccView`
- Capture card: 4 pre-filled fields (priority and why now, champion and economic buyer, top risk, next step and date), each with a confidence computed in code. [repo] `prompts/capture/v1.md`, `src/capture.py`
- Slack Block Kit cards for the AE and SC, a web confirm page, a capture dashboard, and CRM write-back to a file. [repo] `src/blockkit.py`, `src/web.py`, `src/slack_actions.py`, `README.md` "Production path"

## Architecture

- 4 fixed stages in plain Python, 7 model calls on the normal path: extract (2 calls), assess and recommend (1), 3 drafts in parallel, verify (1). [repo] `src/chain.py` docstring and `Chain.run`
- All model calls go through 1 module, `src/llm.py`, using `client.messages.parse` with a pydantic output schema. Only model, max_tokens, system, messages and output_config are sent; anything else raises. [repo] `src/llm.py` `SENT_KEYS`, `_send`
- Effort per step: extract low, assess medium, drafts low, verify medium, judge medium, capture low. [repo] `src/config.py` `STEP_SETTINGS`
- Retry policy: at most 1 retry, only on a max_tokens stop (2x tokens) or a failed validator (error fed back). Refusals are logged and never retried. [repo] `src/llm.py` `acall`
- Prompt layout for caching: stable reference in the system prompt with cache_control, then transcript and CRM in the user turn, then step rules as a mid-conversation system message. [repo] `src/llm.py` `build_request`, DECISIONS D-07
- Replay cache keyed on sha256 of step, prompt version, model and canonical input. Replay mode raises on a miss and never builds a network client. [repo] `src/llm.py` `replay_key`, `ReplayMiss`, `LLMClient.backend`
- Every call is logged to SQLite `llm_calls` with tokens, latency, stop reason, effort and cost. [repo] `src/record_store.py`, `src/llm.py` `_log`
- Automatic trigger by polling or a Gong-style webhook, skipping calls not in the TV stage. [repo] `src/ingest.py`, `README.md` "Automatic trigger"

## Deterministic vs LLM judgment

Deterministic (code, no model):

- Transcript parsing and utterance IDs. [repo] `src/transcript.py`
- Evidence resolution: the utterance must exist and the excerpt must match after normalization or rapidfuzz partial_ratio of 95 or more, and every number in a fuzzy match must appear exactly. [repo] `src/transcript.py` `resolve_evidence`, DECISIONS D-06
- Quote rendering in the UI from the utterance table, never from model text. [repo] `src/transcript.py` `render_quote`
- Schema validators: step cap of 3, why under 25 words, ISO dates, evidence required. [repo] `src/schemas.py` validators
- Rule overrides after the assess call: R-RULEID, R-NOEVID, R-LOWINFO, R-WAIT, R-CHASE, R-CAP, R-MAP. Each is logged. [repo] `src/rules.py`
- Checks on drafts: evidence_resolves, numbers_in_source, dates_future_business_days, names_known, no_unsupported_claims, quotes_in_transcript, max_three_steps, no_chase_when_waiting, map_agreed_has_evidence. [repo] `src/checks.py`
- MEDDPICC view and gaps. [repo] `src/meddpicc.py`
- Capture confidence: the model's probability capped by checkable signals (no evidence, unmatched evidence, inferred, CRM disagreement, top risk "other", a date not said in the call). [repo] `src/capture.py` `score`
- Nudge timing on a business-hours clock, metrics, Kaplan-Meier. [repo] `src/nudges.py`, `src/metrics.py`

LLM judgment:

- Extraction of all 15 fields. [repo] `prompts/extract/v3.md`, `prompts/extract_b/v1.md`
- Deal state and next step selection and ranking. [repo] `prompts/assess_and_recommend/v2.md`
- Draft writing. [repo] `prompts/draft_*`
- Skeptical verifier on 6 checks: quote supports claim, commitment overstated, buying signal overstated, email promises uncommitted, superseded feature as current, generic step. [repo] `prompts/verify/v1.md`
- Capture field values and the model's own confidence input. [repo] `prompts/capture/v1.md`
- Eval judge, uncalibrated. [repo] `prompts/judge/v1.md`, `evals/results.md`

## Human in the loop

- Nothing is sent to a customer automatically. The notifier refuses any role other than ae, sc, manager or csm. [repo] `src/adapters.py` `FileNotifier.send`, `README.md`
- The AE confirms or corrects the 4 capture fields; fields under 0.90 confidence are asked, champion and top risk are always asked for each AE's first 20 demos, and 10% of confident fields are asked anyway as a spot check. [repo] `src/config.py`, `src/capture.py` `route`, DECISIONS D-16
- A high severity check or verifier failure triggers 1 regeneration; if it still fails, the draft is marked needs review and approve is disabled. [repo] `src/chain.py` `_verify_and_repair`, `README.md` demo script 6:45
- An uncommitted promise in the recap blocks approval at any verifier severity. [repo] `src/chain.py` `_always_blocking`, DECISIONS D-15
- Each next step has act on and one-tap dismiss reasons. Dismiss reasons map to 6 candidate causes of post-demo inaction. [repo] `README.md` "Diagnosis"
- The SC confirms the internal record. [repo] `README.md` demo script 10:00

## Data handling

- Synthetic data only, fictional company. [repo] `README.md`, `data/crm/*.json` `_note`
- PERSON, EMAIL_ADDRESS and PHONE_NUMBER are redacted in logs only if presidio is installed; nothing sent to the model is redacted. Presidio is not installed in the build environment. [repo] `src/llm.py` `_redactor`, DECISIONS D-04
- Consent and retention are inherited from the call recorder in the proposed production path. [repo] `README.md` "Production path"
- API key from ANTHROPIC_API_KEY, with DEBRIEF_API_KEY as a fallback. [repo] `src/config.py` `apply_api_key_alias`, commit `082bd04`
- Local state in SQLite and `var/` files. [repo] `src/config.py` `DB_PATH`, `src/adapters.py` `VAR`

## Measured results already in the repo

- Recorded model output: 2 runs on 2026-10-03, 5 deals, 1 run per deal, `claude-sonnet-5-5`, 76 live calls each, none refused. [repo] `README.md` "Current status"
- Run 2: deal state matches gold on 4 of 5; uncalibrated judge passes 4 of 11 next steps; commitment recall 22 of 23; open item recall 8 of 10; objection recall 8 of 12. [eval] `evals/results.md`
- Verifier ablation: planted errors caught 20 of 20 with the verifier, 14 of 20 without; 0 false alarms on 5 clean drafts. [eval] `evals/ablation.md`
- Stress test of deterministic checks: 49 of 61 planted problems caught, 1 false alarm on 17 clean drafts. [eval] `evals/stress_report.md`, DECISIONS D-11
- Next steps against best practice reference answers (keyword match): 10 of 15 must-have steps covered, 0 wrong steps. [eval] `evals/reference_results.md`
- Cost per debrief, run 2: mean $0.409, range $0.199 to $0.550. Summed call latency mean 105 s. End to end wall clock not measured. [repo] `README.md` "Cost and latency"
- Test suite on this audit: 337 passed, 13 expected failures (known gaps), 0 failed. [repo] `python -m pytest -q`, run 2026-10-04

## Known limitations (stated in the repo)

- Gong, Salesforce and Slack are mocked; Slack was tested against a fake API only. [repo] `README.md` "Production path", "Known limits"
- 1 run per deal; cannot separate prompt effects from sampling noise. [repo] DECISIONS D-15 "What I would do in production"
- The judge is uncalibrated until hand labels exist. [repo] `README.md`, `evals/results.md`
- Ground truth was written by the builder and needs independent review. [repo] `README.md` "Known limits"
- Capture output and the best practice profile are not recorded. [repo] `README.md`, DECISIONS D-16, D-17
- Deterministic checks are heuristics with 12 known misses and 1 known false alarm (13 xfail tests). [repo] `README.md`, `tests/stress/`
- Prompt cache reuse across steps is not established; cache savings not measured. [repo] `README.md` "Cost and latency", DECISIONS D-07
- deal_b's recap is blocked by a likely false alarm; trap T6 regressed in run 2. [eval] `evals/results.md`, DECISIONS D-15
- Mapping a real Gong call ID to a CRM opportunity is not built. [repo] `README.md` "Automatic trigger"

## Design decisions changed or reversed

1. **1 extraction call became 2.** A single 15-field schema passed every offline test, then the first live call failed with 400 "The compiled grammar is too large". Split into part A and part B, merged in code. [repo] commit `25aceaa`, DECISIONS D-14 (second entry)
2. **R-WAIT narrowed.** The rule forced deal_b to waiting_on_customer even though Apex still owed the written SSO design. It no longer fires when an Apex participant owns an open technical item. [repo] commit `d9327d1`, `src/rules.py` R-WAIT, DECISIONS D-15
3. **Verifier severity no longer decides one blocker.** The verifier rated an uncommitted recap promise medium on deal_c, so it stayed one-tap approvable. Now that check blocks approval at any severity, and unsaid dates are high severity. [repo] commit `d9327d1`, `src/chain.py` `_always_blocking`, DECISIONS D-15
4. **The in-call checklist was replaced by a post-call confirm card.** Reps are presenting, not typing. A design brief asked to route on the model's self-reported confidence; that was rejected and confidence is now computed in code with caps. [repo] commit `4a80342`, DECISIONS D-16
5. **The "doable in 10 minutes" rule was reversed.** Prompt v2 and judge v1 required each step to be a 10 minute move. Research found this penalizes the highest-value steps, and tuning to an unvalidated judge risked teaching to the judge. Rebuilt as playbook v2, next steps v3 and judge v2 behind `DEBRIEF_BEST_PRACTICE=1`. [repo] commit `0302e54`, DECISIONS D-17

Also relevant: the claude-api skill recommended server-side refusal fallbacks; they were left off because a fallback is a silent retry on another model. [repo] DECISIONS D-02
