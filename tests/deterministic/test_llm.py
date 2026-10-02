import asyncio
import json

import pytest

from src import config, record_store
from src.llm import LLMClient, ReplayMiss, replay_key, text_from_blocks
from src.schemas import RecapEmail
from tests.fakes import FakeBackend, raw_body, recap_a

FORBIDDEN = {"temperature", "top_p", "top_k", "thinking", "tool_choice", "tools", "stop_sequences"}


@pytest.fixture
def client_factory(tmp_path):
    def make(mode="live", backend=None):
        return LLMClient(mode=mode, backend=backend or FakeBackend(), db_path=tmp_path / "t.sqlite3",
                         replay_dir=tmp_path / "replay", redact=lambda s: s)
    return make


def call(client, validator=None, step="draft_recap_email"):
    return client.call(step=step, output_model=RecapEmail, step_rules="rules", prompt_version="v1",
                       user_blocks=[{"type": "text", "text": "transcript"}], debrief_id="d1", validator=validator)


def test_request_uses_allowlist_and_effort(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()))
    c = client_factory(backend=fb)
    res = call(c)
    assert res.ok
    req = fb.requests[0][1]
    assert set(req) == {"model", "max_tokens", "system", "messages", "output_config"}
    assert not FORBIDDEN & set(req)
    assert req["output_config"] == {"effort": "low"}
    assert req["model"] == config.MODEL
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert all(m["role"] != "assistant" for m in req["messages"])  # no prefill


def test_effort_per_step(client_factory):
    from src.schemas import VerifierReport
    from tests.fakes import clean_report
    fb = FakeBackend().queue("VerifierReport", raw_body(clean_report()))
    c = client_factory(backend=fb)
    c.call(step="verify", output_model=VerifierReport, step_rules="r", prompt_version="v1",
           user_blocks=[{"type": "text", "text": "x"}], debrief_id="d1")
    assert fb.requests[0][1]["output_config"] == {"effort": "medium"}


def test_blocks_read_by_type():
    raw = raw_body(recap_a())
    assert raw["content"][0]["type"] == "thinking"
    assert json.loads(text_from_blocks(raw))["subject"].startswith("Recap")


def test_max_tokens_retries_once_with_double(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body('{"subject": "trunc', stop="max_tokens"), raw_body(recap_a()))
    c = client_factory(backend=fb)
    res = call(c)
    assert res.ok and res.attempts == 2
    first, second = fb.requests[0][1]["max_tokens"], fb.requests[1][1]["max_tokens"]
    assert second == 2 * first


def test_max_tokens_twice_gives_up(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body('{"a', stop="max_tokens"), raw_body('{"b', stop="max_tokens"))
    res = call(client_factory(backend=fb))
    assert res.parsed is None and res.attempts == 2 and fb.count("RecapEmail") == 2


def test_refusal_not_retried(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body(None, stop="refusal",
                                                     stop_details={"type": "refusal", "category": "cyber"}))
    res = call(client_factory(backend=fb))
    assert res.refused and res.attempts == 1 and res.refusal["category"] == "cyber"
    assert fb.count("RecapEmail") == 1


def test_validator_retry_appends_feedback(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()), raw_body(recap_a()))
    seen = []

    def validator(obj):
        seen.append(obj)
        return ["subject too vague"] if len(seen) == 1 else []
    res = call(client_factory(backend=fb), validator=validator)
    assert res.ok and res.attempts == 2
    retry_content = fb.requests[1][1]["messages"][0]["content"]
    assert "subject too vague" in retry_content[-1]["text"]


def test_validator_fails_twice_keeps_errors(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()), raw_body(recap_a()))
    res = call(client_factory(backend=fb), validator=lambda o: ["still wrong"])
    assert res.attempts == 2 and res.validator_errors == ["still wrong"] and not res.ok


def test_every_attempt_logged_with_all_columns(client_factory, tmp_path):
    fb = FakeBackend().queue("RecapEmail", raw_body('{"x', stop="max_tokens"), raw_body(recap_a()))
    call(client_factory(backend=fb))
    rows = record_store.calls_for_debrief("d1", tmp_path / "t.sqlite3")
    assert [r["attempt"] for r in rows] == [1, 2]
    required = {"id", "step", "prompt_version", "model", "input_hash", "input_tokens", "output_tokens",
                "cache_read_input_tokens", "cache_creation_input_tokens", "latency_ms", "stop_reason", "effort",
                "cost_usd"}
    assert required <= set(rows[0])
    assert rows[0]["stop_reason"] == "max_tokens" and rows[1]["cache_read_input_tokens"] == 3000


def test_cost_math():
    # 1000 input at $2, 200 output at $10, 3000 cache read at $0.20 per million
    assert config.cost_usd("claude-sonnet-5-5", 1000, 200, 3000, 0) == round((2000 + 2000 + 600) / 1e6, 6)


def test_step_rules_placement(client_factory, monkeypatch):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()), raw_body(recap_a()))
    c = client_factory(backend=fb)
    call(c)
    msgs = fb.requests[0][1]["messages"]
    assert msgs[-1] == {"role": "system", "content": "rules"}
    monkeypatch.setattr(config, "STEP_RULES_PLACEMENT", "top_system")
    call(c)
    req = fb.requests[1][1]
    assert req["system"][-1]["text"] == "rules" and len(req["messages"]) == 1


def test_redaction_only_touches_logs(client_factory, tmp_path):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()))
    c = LLMClient(mode="live", backend=fb, db_path=tmp_path / "r.sqlite3", replay_dir=tmp_path / "rp",
                  redact=lambda s: s.replace("transcript", "[REDACTED]"))
    call(c)
    assert fb.requests[0][1]["messages"][0]["content"][0]["text"] == "transcript"
    row = record_store.calls_for_debrief("d1", tmp_path / "r.sqlite3")[0]
    assert "[REDACTED]" in row["logged_input"] and "transcript" not in row["logged_input"]


# Replay cache

def test_record_then_replay_hits(client_factory):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()))
    rec = call(client_factory(mode="record", backend=fb))
    rep = call(client_factory(mode="replay", backend=FakeBackend()))
    assert rep.ok and rep.parsed == rec.parsed and rep.keys == rec.keys


def test_replay_miss_is_loud(client_factory):
    with pytest.raises(ReplayMiss) as e:
        call(client_factory(mode="replay"))
    assert "draft_recap_email" in str(e.value) and e.value.key in str(e.value)


def test_replay_key_changes_with_prompt_version():
    a = replay_key("extract", "v1", "m", {"x": 1})
    assert a != replay_key("extract", "v2", "m", {"x": 1}) and a == replay_key("extract", "v1", "m", {"x": 1})


def test_no_outbound_calls_in_replay_with_invalid_key(tmp_path, monkeypatch):
    """Replay mode with a bad API key: hits and misses both complete with no client and no socket."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-invalid")
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()))
    LLMClient(mode="record", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
              redact=lambda s: s).call(step="draft_recap_email", output_model=RecapEmail, step_rules="r",
                                       prompt_version="v1", user_blocks=[{"type": "text", "text": "t"}],
                                       debrief_id="d1")
    replay = LLMClient(mode="replay", db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                       redact=lambda s: s)
    res = replay.call(step="draft_recap_email", output_model=RecapEmail, step_rules="r", prompt_version="v1",
                      user_blocks=[{"type": "text", "text": "t"}], debrief_id="d1")
    assert res.ok
    with pytest.raises(ReplayMiss):
        replay.call(step="draft_recap_email", output_model=RecapEmail, step_rules="different", prompt_version="v1",
                    user_blocks=[{"type": "text", "text": "t"}], debrief_id="d1")
    assert replay._backend is None and replay.requests_sent == []
    with pytest.raises(RuntimeError):
        replay.backend  # noqa: B018


def test_record_reuses_existing_fixture(client_factory, monkeypatch):
    fb = FakeBackend().queue("RecapEmail", raw_body(recap_a()))
    call(client_factory(mode="record", backend=fb))
    fb2 = FakeBackend()
    res = call(client_factory(mode="record", backend=fb2))
    assert res.ok and fb2.requests == []
    monkeypatch.setattr(config, "RERECORD", True)
    fb3 = FakeBackend().queue("RecapEmail", raw_body(recap_a()))
    call(client_factory(mode="record", backend=fb3))
    assert len(fb3.requests) == 1


def test_real_sdk_backend_request_shape(tmp_path):
    """The real AnthropicBackend over a mock transport: parse() is used, body has only allowed keys."""
    import anthropic
    import httpx2

    from src.llm import AnthropicBackend

    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        if len(bodies) == 1:
            return httpx2.Response(200, json=raw_body('{"subject": "cut', stop="max_tokens"))
        return httpx2.Response(200, json=raw_body(recap_a()))

    b = AnthropicBackend()
    b._client = anthropic.AsyncAnthropic(api_key="test", max_retries=0, http_client=httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), event_hooks={"response": [b._hook]}))
    c = LLMClient(mode="live", backend=b, db_path=tmp_path / "t.sqlite3", redact=lambda s: s)
    res = call(c)
    assert res.ok and res.attempts == 2  # truncated JSON surfaced as max_tokens via the hook, then retried
    body = bodies[0]
    assert set(body) == {"model", "max_tokens", "system", "messages", "output_config"}
    assert set(body["output_config"]) == {"effort", "format"}
    assert [m["role"] for m in body["messages"]] == ["user", "system"]
    assert bodies[1]["max_tokens"] == 2 * body["max_tokens"]
