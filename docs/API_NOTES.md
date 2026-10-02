# API notes

Source of truth for what `src/llm.py` sends. Raw results: `docs/smoke_results.json`. Rerun with `python scripts/smoke_test.py`.

## Status

| Check | Status | Result |
|---|---|---|
| (a) `client.messages.parse(output_format=PydanticModel)` on `claude-sonnet-5-5` | Pending live run (no `ANTHROPIC_API_KEY` on 2026-10-02) | Offline: SDK 1.11.0 accepts it and fills `parsed_output` |
| (b) `output_config={"effort": ...}` in the same call | Pending live run | Offline: SDK merges both into one request body, `output_config = {effort, format}` |
| (c) content block types returned | Pending live run | Offline mock only: `parse` reads JSON from the `text` block when a `thinking` block comes first |
| (d) cache read on repeated stable prefix | Pending live run | Not measured. No savings claimed. |
| (e) `temperature` rejected with 400 | Pending live run | Offline: `parse()` in SDK 1.11.0 has no `temperature`, `top_p` or `top_k` parameter at all |

"Offline" means verified against the installed SDK with a mock HTTP transport. It shows what the SDK sends, not what the API accepts.

## Verified locally (SDK 1.11.0, no network)

- `Messages.parse` parameters: `max_tokens, messages, model, diagnostics, metadata, output_config, output_format, service_tier, stop_sequences, system, thinking, tool_choice, tools, extra_headers, extra_query, extra_body, timeout`.
- No top-level `cache_control` on `parse`. Use block-level `cache_control: {"type": "ephemeral"}` on the system text blocks.
- `parse(output_format=M, output_config={"effort": "low"})` produces the body keys `max_tokens, messages, model, output_config`, with `output_config` keys `effort, format`.
- The SDK uses `httpx2`, not `httpx`. Custom transports in tests must use `httpx2.MockTransport`.

## Documented by the claude-api skill (cached 2026-09-25), not yet live-verified

- Sonnet 5.5: thinking is adaptive by default. `thinking: {"type": "disabled"}` returns 400. `budget_tokens` returns 400. Non-default sampling params return 400. Assistant prefill returns 400. Forced `tool_choice` `any` or `tool` returns 400.
- Effort is GA in `output_config`, values `low, medium, high, xhigh, max`, default `high` on Sonnet 5.5.
- Default thinking display is `omitted`, so thinking blocks can arrive with empty text. Code must read blocks by type.
- `stop_details` is only populated when `stop_reason == "refusal"`.
- Structured outputs and the Citations API cannot be combined in one call (400).
- Pricing per MTok: input $2.00, output $10.00, cache read $0.20. Cache write is assumed to be 1.25x input ($2.50) and still needs checking.

## What llm.py will send (until the live run says otherwise)

```
client.messages.parse(
    model=DEBRIEF_MODEL,
    max_tokens=<per step>,
    system=[{"type": "text", "text": <stable block>, "cache_control": {"type": "ephemeral"}}, <step rules>],
    messages=[{"role": "user", "content": <transcript then data>}],
    output_format=<PydanticModel>,
    output_config={"effort": <per step>},
)
```

Never sent: `temperature`, `top_p`, `top_k`, `thinking`, assistant prefill, `tool_choice`, `fallbacks`.

## Fill in after the live run

- Observed block types per probe:
- Effort accepted (low, medium):
- Temperature probe status code and message:
- cache_creation_input_tokens on d1, cache_read_input_tokens on d2:
- Latency per probe:
