# Debrief

Post-demo playbook for Enterprise technical validation (TV) demos at Apex, a fictional company. Synthetic data, fictional company.

## Stack
Python 3.11, anthropic SDK (1.x, uses httpx2), pydantic v2, Streamlit, SQLite, pytest, rapidfuzz. No agent or orchestration framework. Presidio is optional.

## Commands
- `make test`: `pytest -q` (no API key needed)
- `make eval`: `python evals/run_evals.py` in replay mode
- `make demo`: `DEBRIEF_MODE=replay streamlit run app.py`
- `make record`: run the chain on all transcripts with `DEBRIEF_MODE=record`
- `python scripts/smoke_test.py`: live API probe, results in docs/API_NOTES.md

## Env
`DEBRIEF_MODEL` (default `claude-sonnet-5-5`), `DEBRIEF_MODE` (live, record, replay; default replay), `ANTHROPIC_API_KEY`.

## Hard rules for model calls
1. All model calls go through `src/llm.py`. No `anthropic.Anthropic()` anywhere else (scripts/smoke_test.py is the only exception).
2. Every structured step uses `client.messages.parse(output_format=<PydanticModel>)`.
3. Never send temperature, top_p, top_k, assistant prefill, forced tool_choice, thinking budgets, or `thinking: disabled`.
4. Effort per step: extract low, assess_and_recommend medium, draft low, verify medium.
5. Read response content blocks by type. Never index `content[0]`.
6. `max_tokens` stop: retry once with 2x max_tokens. `refusal` stop: log, surface in UI, never retry.
7. Retry only on max_tokens or a failed semantic validator. Max 1 retry, with the validator error appended as feedback.
8. Log every call to SQLite `llm_calls` (step, prompt_version, model, input_hash, all token counts, latency_ms, stop_reason, effort, cost_usd).
9. Prompt order for caching: playbook, release cards, competitor notes, then transcript, then step instructions. Report measured cache reads only.
10. Schema and rules in the system prompt, data in the user turn. Prompts live in `prompts/<step>/v<N>.md`; bump N on any change.
11. Redact PERSON, EMAIL_ADDRESS, PHONE_NUMBER in logs only if presidio is installed. Never redact what is sent to the model.

## Hard rules for schemas and output
- Every field required. Empty lists, not Optional or unions. No field named "reasoning"; use "why" (max 25 words).
- At most 3 next steps. Never pad. Fewer is fine.
- The model never writes quote text that reaches the UI. Quotes are rendered by code from the utterance table.
- Evidence must resolve: utterance_id exists and excerpt matches (substring after normalization or rapidfuzz partial_ratio >= 95).
- Nothing is sent to a customer automatically. Humans approve everything.
- Never present a metric target as a result. Never claim causation.

## Replay cache
Key = sha256(step + prompt_version + model + canonical_json(input)), stored at `fixtures/replay/<key>.json`. Replay mode raises on a miss naming step and key. Never fall through to the network.

## Tests
- Tests never touch the network. Use the replay cache or fakes.
- `tests/deterministic` runs on every edit under `src/` (hook in `.claude/settings.json`).
- Every bug found in review becomes a test in `tests/regressions/`.

## Writing style
No em dashes anywhere (code, comments, prompts, UI, docs). Sentence case headings and labels. Plain sales language in the UI, no AI jargon.

## Decisions
Log AI mistakes and fixes in DECISIONS.md using docs/DECISIONS_TEMPLATE.md.
