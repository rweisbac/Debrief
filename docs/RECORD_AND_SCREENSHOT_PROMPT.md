# Prompt: record real debriefs and capture screenshots

Paste the text below into a new Claude Code session on branch `claude/serene-cray-u5atca`. It spends API money (a few dollars at most), so it stops for approval before the paid step.

---

Read CLAUDE.md first and follow its hard rules. Goal: replace the hand-written sample cards with real model output on the 5 synthetic transcripts, then capture screenshots for my interview walkthrough.

1. Preflight, no cost. Run `pip install -r requirements.txt playwright`, then `make test` and `make style`. Confirm `ANTHROPIC_API_KEY` or `DEBRIEF_API_KEY` is set without printing its value. Stop and tell me if tests fail.
2. Tell me what `make record` will do and what you expect it to cost (6 calls per deal, 5 deals, plus judge and ablation calls, Sonnet 5.5 pricing is in src/config.py). Wait for my yes before step 3.
3. Run `make record`. If a deal fails or is refused, report it with the reason. Never retry a refusal. Do not delete or overwrite existing fixtures unless I say so (`DEBRIEF_RERECORD=1`).
4. Run `make eval`. Report the pass rates from `evals/results.md` and `evals/ablation.md` as they are, including failures. Do not describe a metric target as a result and do not claim causation.
5. Measure for real: from the `llm_calls` table, report cost per debrief, latency per debrief and the cache read tokens actually observed. Update the "Current status" and "Cost and latency" sections of README.md and the open items in DECISIONS.md and docs/API_NOTES.md with those numbers only. If a number was not measured, say "not measured".
6. Run `DEBRIEF_SAMPLES=0 python scripts/take_screenshots.py`. Open at least three of the PNGs in docs/screenshots/ and check that: the "Not generated from the call" sample banner is gone, the quotes come from the transcript, and nothing says "needs review" without a reason. If a screen looks wrong, fix the cause or tell me. Do not edit the PNGs.
7. Run `python -m src.ingest once` with `DEBRIEF_MODE=replay` and show me `var/outbox.jsonl` so I can see the AE and SC messages built from real output. If I give you a Slack bot token and channel, also post one test message there, never to a customer.
8. Commit with a clear message and push to `claude/serene-cray-u5atca` (fixtures, evals output, docs, screenshots). Do not open a new PR; the existing PR is https://github.com/rweisbac/Debrief/pull/1. Then summarize: what ran, what it cost, what failed, what is still unverified.

Rules: no em dashes anywhere, sentence case headings, nothing is sent to a customer, no network in tests.
