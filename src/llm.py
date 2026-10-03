"""The only module that talks to the Claude API.

Rules (see CLAUDE.md):
- every structured step uses client.messages.parse(output_format=<PydanticModel>)
- only model, max_tokens, system, messages, output_format and output_config.effort are sent
- content blocks are read by type, never by position
- at most 1 retry per call: on stop_reason max_tokens (2x tokens) or a failed validator (with feedback)
- refusals are logged and returned, never retried
- every attempt is logged to SQLite llm_calls
- replay mode reads fixtures only and raises on a miss; it never builds a network client

messages.parse raises a pydantic ValidationError when the JSON is truncated, which hides
stop_reason and usage. To keep parse() and still see the raw response, the HTTP client has a
response hook that stores each raw body under a per call header. That raw body is what gets
logged and what record mode saves as the replay fixture.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel, ValidationError

from src import config, record_store
from src.prompts import stable_reference

CALL_ID_HEADER = "x-debrief-call-id"
SENT_KEYS = {"model", "max_tokens", "system", "messages", "output_config"}
LOG_TEXT_LIMIT = 20000


class ReplayMiss(RuntimeError):
    def __init__(self, step: str, key: str):
        super().__init__(f"replay fixture missing for step {step!r}, key {key}. "
                         f"Run with DEBRIEF_MODE=record (needs DEBRIEF_API_KEY or ANTHROPIC_API_KEY) to create it.")
        self.step, self.key = step, key


class LLMError(RuntimeError):
    pass


@dataclass
class CallResult:
    step: str
    prompt_version: str
    parsed: BaseModel | None
    stop_reason: str
    refused: bool = False
    refusal: dict = field(default_factory=dict)
    attempts: int = 0
    validator_errors: list[str] = field(default_factory=list)
    parse_error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    keys: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.parsed is not None and not self.refused and not self.validator_errors


class Backend(Protocol):
    async def send(self, request: dict, output_model: type[BaseModel]) -> tuple[dict, BaseModel | None, str]:
        """Return (raw response body, parsed output or None, parse error text)."""


class AnthropicBackend:
    """Live backend. Built lazily so replay mode never constructs a client."""

    def __init__(self, transport=None, api_key: str | None = None, max_retries: int = 2) -> None:
        """transport and api_key exist for offline tests (an httpx2 MockTransport); production passes neither.
        max_retries covers SDK transport retries on 429, 5xx and connection errors only (D-14)."""
        self._client = None
        self._captured: dict[str, dict] = {}
        self._transport, self._api_key, self._max_retries = transport, api_key, max_retries

    async def _hook(self, response) -> None:
        call_id = response.request.headers.get(CALL_ID_HEADER)
        if call_id:
            await response.aread()
            try:
                self._captured[call_id] = response.json()
            except ValueError:
                self._captured[call_id] = {"error": response.text[:2000]}

    def client(self):
        if self._client is None:
            import anthropic
            import httpx2

            key = self._api_key or config.api_key()
            kwargs = {"api_key": key} if key else {}
            self._client = anthropic.AsyncAnthropic(
                timeout=600, max_retries=self._max_retries, **kwargs,
                http_client=httpx2.AsyncClient(transport=self._transport, event_hooks={"response": [self._hook]}))
        return self._client

    async def send(self, request: dict, output_model: type[BaseModel]) -> tuple[dict, BaseModel | None, str]:
        call_id = uuid.uuid4().hex
        try:
            msg = await self.client().messages.parse(
                **request, output_format=output_model, extra_headers={CALL_ID_HEADER: call_id})
        except ValidationError as e:
            raw = self._captured.pop(call_id, None)
            if raw is None:
                raise
            return raw, None, str(e)[:2000]
        raw = self._captured.pop(call_id, None) or msg.model_dump(mode="json", exclude={"parsed_output"})
        return raw, msg.parsed_output, ""


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def replay_key(step: str, prompt_version: str, model: str, request_input: dict) -> str:
    return hashlib.sha256((step + prompt_version + model + canonical_json(request_input)).encode()).hexdigest()


def text_from_blocks(raw: dict) -> str:
    """Join text blocks by type. Thinking and other block types are skipped."""
    return "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")


def parse_raw(raw: dict, output_model: type[BaseModel]) -> tuple[BaseModel | None, str]:
    text = text_from_blocks(raw)
    if not text:
        return None, "no text block in response"
    try:
        return output_model.model_validate_json(text), ""
    except ValidationError as e:
        return None, str(e)[:2000]


def _redactor() -> Callable[[str], str]:
    """Redact PERSON, EMAIL_ADDRESS, PHONE_NUMBER in logs if presidio is installed. Logs only."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        return lambda text: text
    analyzer, anonymizer = AnalyzerEngine(), AnonymizerEngine()
    entities = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]

    def redact(text: str) -> str:
        results = analyzer.analyze(text=text, entities=entities, language="en")
        return anonymizer.anonymize(text=text, analyzer_results=results).text
    return redact


class LLMClient:
    def __init__(self, mode: str | None = None, backend: Backend | None = None, model: str | None = None,
                 db_path: Path | None = None, replay_dir: Path | None = None,
                 redact: Callable[[str], str] | None = None):
        self.mode = mode or config.MODE
        if self.mode not in {"live", "record", "replay"}:
            raise ValueError(f"bad mode {self.mode!r}")
        self.model = model or config.MODEL
        self.db_path = db_path
        self.replay_dir = Path(replay_dir or config.REPLAY_DIR)
        self._backend = backend
        self._redact = redact
        self.requests_sent: list[dict] = []  # request bodies handed to the backend, for tests

    @property
    def backend(self) -> Backend:
        if self.mode == "replay":
            raise RuntimeError("replay mode must never use a network backend")
        if self._backend is None:
            self._backend = AnthropicBackend()
        return self._backend

    def redact(self, text: str) -> str:
        if self._redact is None:
            self._redact = _redactor()
        return self._redact(text)

    def build_request(self, step_rules: str, user_blocks: list[dict], max_tokens: int, effort: str,
                      feedback: str = "") -> dict:
        stable_text, _ = stable_reference()
        system = [{"type": "text", "text": stable_text, "cache_control": {"type": "ephemeral"}}]
        content = list(user_blocks)
        if feedback:
            content.append({"type": "text", "text": feedback})
        messages: list[dict] = [{"role": "user", "content": content}]
        if config.STEP_RULES_PLACEMENT == "mid_conversation_system":
            messages.append({"role": "system", "content": step_rules})
        else:
            system.append({"type": "text", "text": step_rules})
        return {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages,
                "output_config": {"effort": effort}}

    async def _send(self, step: str, prompt_version: str, request: dict,
                    output_model: type[BaseModel]) -> tuple[dict, BaseModel | None, str, bool, str]:
        key_input = {"request": request, "output_model": output_model.__name__,
                     "schema": output_model.model_json_schema()}
        key = replay_key(step, prompt_version, self.model, key_input)
        path = self.replay_dir / f"{key}.json"
        reuse = self.mode == "record" and path.exists() and not config.RERECORD
        if self.mode == "replay" or reuse:
            if not path.exists():
                raise ReplayMiss(step, key)
            raw = json.loads(path.read_text(encoding="utf-8"))["raw"]
            parsed, err = parse_raw(raw, output_model)
            return raw, parsed, err, True, key
        unknown = set(request) - SENT_KEYS
        if unknown:
            raise LLMError(f"refusing to send unexpected parameters: {sorted(unknown)}")
        self.requests_sent.append(request)
        raw, parsed, err = await self.backend.send(request, output_model)
        if self.mode == "record":
            self.replay_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"step": step, "prompt_version": prompt_version, "model": self.model,
                                        "key": key, "recorded_at": datetime.now(timezone.utc).isoformat(),
                                        "raw": raw}, indent=1) + "\n", encoding="utf-8")
        return raw, parsed, err, False, key

    def _log(self, *, debrief_id: str, step: str, prompt_version: str, attempt: int, key: str, raw: dict,
             effort: str, latency_ms: int, replay_hit: bool, request: dict, error: str) -> dict:
        usage = raw.get("usage") or {}
        u = {k: int(usage.get(k) or 0) for k in
             ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        cost = config.cost_usd(self.model, u["input_tokens"], u["output_tokens"],
                               u["cache_read_input_tokens"], u["cache_creation_input_tokens"])
        logged_input = self.redact(canonical_json(request["messages"]))[:LOG_TEXT_LIMIT]
        logged_output = self.redact(text_from_blocks(raw))[:LOG_TEXT_LIMIT]
        record_store.log_llm_call({
            "id": uuid.uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
            "debrief_id": debrief_id, "step": step, "prompt_version": prompt_version, "model": self.model,
            "mode": self.mode, "attempt": attempt, "input_hash": key, **u, "latency_ms": latency_ms,
            "stop_reason": str(raw.get("stop_reason") or ""), "effort": effort, "cost_usd": cost,
            "replay_hit": int(replay_hit), "error": error, "logged_input": logged_input,
            "logged_output": logged_output}, self.db_path)
        return {**u, "cost_usd": cost}

    async def acall(self, *, step: str, output_model: type[BaseModel], step_rules: str, prompt_version: str,
                    user_blocks: list[dict], debrief_id: str,
                    validator: Callable[[BaseModel], list[str]] | None = None) -> CallResult:
        settings = config.STEP_SETTINGS[step]
        effort, max_tokens = settings["effort"], settings["max_tokens"]
        _, shared_v = stable_reference()
        pv = f"{prompt_version}+{shared_v}"
        result = CallResult(step=step, prompt_version=pv, parsed=None, stop_reason="")
        feedback = ""
        for attempt in (1, 2):
            request = self.build_request(step_rules, user_blocks, max_tokens, effort, feedback)
            t0 = time.perf_counter()
            raw, parsed, parse_err, replay_hit, key = await self._send(step, pv, request, output_model)
            latency = round((time.perf_counter() - t0) * 1000)
            stop = str(raw.get("stop_reason") or "")
            usage = self._log(debrief_id=debrief_id, step=step, prompt_version=pv, attempt=attempt, key=key,
                              raw=raw, effort=effort, latency_ms=latency, replay_hit=replay_hit,
                              request=request, error=parse_err)
            result.attempts = attempt
            result.keys.append(key)
            result.stop_reason = stop
            result.latency_ms += latency
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                setattr(result, k, getattr(result, k) + usage[k])
            result.cost_usd = round(result.cost_usd + usage["cost_usd"], 6)

            if stop == "refusal":
                result.refused = True
                result.refusal = raw.get("stop_details") or {"type": "refusal"}
                result.parsed = None
                return result
            if stop == "max_tokens":
                result.parse_error = parse_err or "output truncated at max_tokens"
                if attempt == 1:
                    max_tokens *= 2
                    continue
                return result
            if parsed is None:
                result.parse_error = parse_err
                if attempt == 1:
                    feedback = ("Your previous output could not be parsed against the schema. "
                                f"Return the full output again. Parser error: {parse_err[:500]}")
                    continue
                return result
            errors = validator(parsed) if validator else []
            result.parsed, result.validator_errors, result.parse_error = parsed, errors, ""
            if errors and attempt == 1:
                feedback = ("Your previous output failed these checks. Fix every one and return the full "
                            "output again:\n- " + "\n- ".join(errors))
                continue
            return result
        return result

    def call(self, **kwargs) -> CallResult:
        return asyncio.run(self.acall(**kwargs))
