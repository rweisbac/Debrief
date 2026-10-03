"""Live smoke test for the Claude API features llm.py depends on.

Checks:
  a. client.messages.parse(output_format=<pydantic model>) works on DEBRIEF_MODEL
  b. output_config effort can be passed in the same parse call
  c. which content block types come back, in what order
  d. prompt caching on a stable prefix: observed cache_read_input_tokens on a repeat call
  e. negative probe: temperature sent through extra_body is rejected
  f. step rules as a mid-conversation {"role": "system"} message after the user turn (llm.py layout)
  offline (always runs, no network): the request body the installed SDK builds for
  parse + effort, captured with a mock transport, and parsing when a thinking block precedes text

Writes docs/smoke_results.json. Run: python scripts/smoke_test.py
This script is the only file outside src/llm.py allowed to build a client directly,
because its job is to probe the raw API before llm.py exists.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel  # noqa: E402

from src.config import MODEL, api_key, cost_usd  # noqa: E402

OUT = ROOT / "docs" / "smoke_results.json"


class Probe(BaseModel):
    deal_state: str
    next_step: str
    why: str


# About 5K tokens of stable text so the prefix clears the minimum cacheable length.
STABLE_PREFIX = "Fictional Apex playbook (synthetic). " + " ".join(
    f"Rule PB-{i:02d}: after a technical validation demo, the account executive confirms a dated next step, "
    f"names the economic buyer, routes open technical items to the solutions consultant with a due date, "
    f"and ties the recap to the customer's stated business outcome. Variant {i}."
    for i in range(1, 121)
)

USER_TEXT = (
    "Transcript excerpt:\n"
    "[U001 | 00:12 | Dana Ortiz, VP Data (customer)] We need SSO with our custom identity provider "
    "before security will sign off.\n"
    "[U002 | 00:31 | Sam Lee, AE (apex)] Understood, our SC will follow up.\n\n"
    "Return the deal state, one next step, and why in under 25 words."
)


def block_summary(resp) -> list[dict]:
    out = []
    for b in resp.content:
        item = {"type": b.type}
        if b.type == "text":
            item["chars"] = len(b.text)
        if b.type == "thinking":
            item["thinking_chars"] = len(getattr(b, "thinking", "") or "")
        out.append(item)
    return out


def usage_dict(resp) -> dict:
    u = resp.usage
    return {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
    }


def run_probe(name: str, fn) -> dict:
    t0 = time.perf_counter()
    try:
        resp = fn()
    except Exception as e:  # record the raw error, the point is to learn what the API does
        return {
            "probe": name, "ok": False,
            "error_type": type(e).__name__,
            "status_code": getattr(e, "status_code", None),
            "error": str(e)[:600],
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
    parsed = getattr(resp, "parsed_output", None)
    u = usage_dict(resp)
    return {
        "probe": name, "ok": True,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
        "model": resp.model,
        "stop_reason": resp.stop_reason,
        "stop_details": (resp.stop_details.model_dump() if getattr(resp, "stop_details", None) else None),
        "content_blocks": block_summary(resp),
        "parsed_output_type": type(parsed).__name__ if parsed is not None else None,
        "parsed_output": parsed.model_dump() if isinstance(parsed, BaseModel) else None,
        "usage": u,
        "cost_usd": cost_usd(MODEL, u["input_tokens"], u["output_tokens"],
                             u["cache_read_input_tokens"] or 0, u["cache_creation_input_tokens"] or 0),
    }


def offline_checks() -> dict:
    """Verify SDK request shaping without the network. Not a substitute for the live probes."""
    import inspect

    import anthropic
    import httpx2
    from anthropic.resources.messages import Messages

    captured: list[dict] = []

    def handler(req):
        captured.append(json.loads(req.content))
        return httpx2.Response(200, json={
            "id": "msg_offline", "type": "message", "role": "assistant", "model": MODEL,
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": '{"deal_state":"x","next_step":"y","why":"z"}'}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}})

    client = anthropic.Anthropic(api_key="offline-not-a-key",
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    resp = client.messages.parse(model=MODEL, max_tokens=10, messages=[{"role": "user", "content": "x"}],
                                 output_format=Probe, output_config={"effort": "low"})
    body = captured[0]
    return {
        "sdk_version": anthropic.__version__,
        "parse_signature_params": [p for p in inspect.signature(Messages.parse).parameters if p != "self"],
        "request_top_level_keys": sorted(body),
        "request_output_config_keys": sorted(body.get("output_config", {})),
        "effort_and_format_in_same_output_config": {"effort", "format"} <= set(body.get("output_config", {})),
        "parsed_with_thinking_block_first": isinstance(resp.parsed_output, Probe),
        "mock_block_types": [b.type for b in resp.content],
    }


def main() -> int:
    offline = offline_checks()
    print(f"offline: sdk={offline['sdk_version']} effort+format merged="
          f"{offline['effort_and_format_in_same_output_config']} "
          f"parse ok with thinking first={offline['parsed_with_thinking_block_first']}")
    if not api_key():
        result = {"status": "skipped", "reason": "DEBRIEF_API_KEY and ANTHROPIC_API_KEY not set", "model": MODEL,
                  "ran_at": datetime.now(timezone.utc).isoformat(), "offline": offline}
        OUT.write_text(json.dumps(result, indent=2) + "\n")
        print("SKIPPED: no DEBRIEF_API_KEY or ANTHROPIC_API_KEY. Nothing verified. Results file marks status=skipped.")
        return 0

    import anthropic

    client = anthropic.Anthropic(api_key=api_key())
    msgs = [{"role": "user", "content": USER_TEXT}]
    system_cached = [{"type": "text", "text": STABLE_PREFIX, "cache_control": {"type": "ephemeral"}}]

    probes = [
        run_probe("a_parse_output_format", lambda: client.messages.parse(
            model=MODEL, max_tokens=2000, messages=msgs, output_format=Probe)),
        run_probe("b_parse_with_effort_low", lambda: client.messages.parse(
            model=MODEL, max_tokens=2000, messages=msgs, output_format=Probe,
            output_config={"effort": "low"})),
        run_probe("b2_parse_with_effort_medium", lambda: client.messages.parse(
            model=MODEL, max_tokens=4000, messages=msgs, output_format=Probe,
            output_config={"effort": "medium"})),
        run_probe("d1_cache_write", lambda: client.messages.parse(
            model=MODEL, max_tokens=2000, system=system_cached, messages=msgs, output_format=Probe,
            output_config={"effort": "low"})),
        run_probe("d2_cache_read", lambda: client.messages.parse(
            model=MODEL, max_tokens=2000, system=system_cached, messages=msgs, output_format=Probe,
            output_config={"effort": "low"})),
        run_probe("f_mid_conversation_system", lambda: client.messages.parse(
            model=MODEL, max_tokens=2000, system=system_cached, output_format=Probe,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": USER_TEXT},
                      {"role": "system", "content": "Answer in under 15 words per field."}])),
        run_probe("e_temperature_rejected", lambda: client.messages.parse(
            model=MODEL, max_tokens=2000, messages=msgs, output_format=Probe,
            extra_body={"temperature": 0.2})),
    ]

    result = {"status": "ran", "model": MODEL, "sdk_version": anthropic.__version__,
              "ran_at": datetime.now(timezone.utc).isoformat(), "offline": offline, "probes": probes}
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    for p in probes:
        if p["ok"]:
            print(f"{p['probe']}: ok stop={p['stop_reason']} blocks={[b['type'] for b in p['content_blocks']]} "
                  f"parsed={p['parsed_output_type']} usage={p['usage']} {p['latency_ms']}ms")
        else:
            print(f"{p['probe']}: FAILED {p['status_code']} {p['error_type']}: {p['error'][:200]}")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
