"""Automatic trigger: run a debrief when a new technical validation transcript arrives.

Two entry points feed the same `process_call`:
- `watch`: polls the call source for transcripts it has not processed yet (file-backed here, so it
  watches data/transcripts).
- `serve`: a small webhook receiver. Gong automation rules can POST to it when a call is ready.

What it does: runs the normal chain, saves the debrief, logs `card_generated`, and posts an internal
"card ready" message to the AE. Nothing is sent to a customer. Drafts wait for a human to approve.

Not built: mapping a real Gong call id to a CRM opportunity. Here the payload carries `deal_id`.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src import service
from src.adapters import VAR, CRMSource, FileCRMSource, FileGongSource, FileNotifier, GongSource, Notifier
from src.chain import Chain, load_context
from src.llm import LLMClient, ReplayMiss

TV_STAGE = "Technical Validation"
MAX_ATTEMPTS = 2  # a failed run is retried once, then left for a human, so a bad call cannot loop on cost
LEDGER = VAR / "ingest_ledger.json"
MAX_BODY_BYTES = 64 * 1024


def _load_ledger(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def process_call(deal_id: str, *, gong: GongSource | None = None, crm_source: CRMSource | None = None,
                 llm: LLMClient | None = None, notifier: Notifier | None = None,
                 ledger_path: Path = LEDGER, now: datetime | None = None) -> dict:
    """Debrief one call if it is a new TV transcript. Returns {"deal_id", "status", "detail"}.

    Status: done, skipped (not TV stage, or already processed), waiting (CRM or activity data not there yet),
    error (run failed; retried up to MAX_ATTEMPTS)."""
    gong, crm_source = gong or FileGongSource(), crm_source or FileCRMSource()
    notifier = notifier or FileNotifier()
    now = now or datetime.now(timezone.utc)

    def result(status: str, detail: str = "") -> dict:
        return {"deal_id": deal_id, "status": status, "detail": detail}

    try:
        crm = crm_source.deal(deal_id)
        gong.activity(deal_id)
        transcript = gong.transcript(deal_id)
    except FileNotFoundError as e:
        return result("waiting", f"missing input: {Path(str(e.filename)).name}")
    if crm.get("stage") != TV_STAGE:
        return result("skipped", f"stage is {crm.get('stage')!r}, not {TV_STAGE!r}")

    digest = hashlib.sha256(transcript.render_for_model().encode("utf-8")).hexdigest()
    ledger = _load_ledger(ledger_path)
    entry = ledger.get(deal_id, {})
    if entry.get("hash") == digest and (entry.get("status") == "done" or entry.get("attempts", 0) >= MAX_ATTEMPTS):
        return result("skipped", f"already {entry['status']}")

    attempts = entry.get("attempts", 0) + 1 if entry.get("hash") == digest else 1
    try:
        run = asyncio.run(Chain(llm or LLMClient()).run(load_context(deal_id, gong, crm_source)))
        payload = run.to_dict()
        payload["source"] = "auto"
        errors = list(run.errors)
    except ReplayMiss as e:
        payload, errors = None, [str(e)]
    except Exception as e:  # keep the watcher alive; the ledger records what happened
        payload, errors = None, [f"{type(e).__name__}: {e}"]

    if payload is None or errors:
        ledger[deal_id] = {"hash": digest, "status": "error", "attempts": attempts, "at": now.isoformat(),
                           "errors": errors}
        _save_ledger(ledger_path, ledger)
        return result("error", "; ".join(errors)[:300])

    service.generate_card(deal_id, payload, now, prompt_version=json.dumps(payload["prompt_versions"], sort_keys=True))
    notifier.send(crm["owner_ae"], "ae", deal_id, "card_ready", {
        "text": f"Your debrief for {crm['account']} is ready. Review the next steps and drafts before anything is sent.",
        "debrief_id": payload["debrief_id"], "at": now.isoformat()})
    ledger[deal_id] = {"hash": digest, "status": "done", "attempts": attempts, "at": now.isoformat(),
                       "debrief_id": payload["debrief_id"]}
    _save_ledger(ledger_path, ledger)
    return result("done", payload["debrief_id"])


def scan_once(gong: FileGongSource | None = None, **kwargs) -> list[dict]:
    """One pass over every call the source knows about. Cheap for calls already processed."""
    gong = gong or FileGongSource()
    return [process_call(d, gong=gong, **kwargs) for d in gong.list_calls()]


def watch(interval: int = 30, **kwargs) -> None:
    seen: dict[str, tuple[str, str]] = {}
    while True:
        for r in scan_once(**kwargs):
            key = (r["status"], r["detail"])
            if seen.get(r["deal_id"]) != key:  # print changes only, not every poll
                seen[r["deal_id"]] = key
                print(f"{datetime.now().strftime('%H:%M:%S')} {r['deal_id']}: {r['status']} {r['detail']}", flush=True)
        time.sleep(interval)


def check_webhook(secret: str, given_secret: str, length: int, read_body) -> tuple[int, dict, str]:
    """Validate one webhook request. Returns (http status, reply body, deal_id to run or "")."""
    if not hmac.compare_digest(given_secret, secret):
        return 401, {"error": "bad secret"}, ""
    if length > MAX_BODY_BYTES:
        return 413, {"error": "body too large"}, ""
    try:
        deal_id = json.loads(read_body(length)).get("deal_id", "")
    except (ValueError, AttributeError):
        return 400, {"error": "body must be JSON"}, ""
    if not isinstance(deal_id, str) or not deal_id.replace("_", "").isalnum():
        return 400, {"error": "deal_id missing or invalid"}, ""
    return 202, {"accepted": deal_id}, deal_id


def make_handler(secret: str, **kwargs):
    pool = ThreadPoolExecutor(max_workers=1)  # one debrief at a time; the webhook replies before it finishes

    def job(deal_id: str) -> None:
        r = process_call(deal_id, **kwargs)
        print(f"{r['deal_id']}: {r['status']} {r['detail']}", flush=True)

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/gong/webhook":
                return self._reply(404, {"error": "not found"})
            code, body, deal_id = check_webhook(secret, self.headers.get("X-Debrief-Secret", ""),
                                                int(self.headers.get("Content-Length") or 0), self.rfile.read)
            if deal_id:
                pool.submit(job, deal_id)
            self._reply(code, body)

        def log_message(self, *args) -> None:
            pass

    return Handler


def serve(port: int = 8765, host: str = "127.0.0.1", **kwargs) -> None:
    secret = os.environ.get("DEBRIEF_WEBHOOK_SECRET", "")
    if not secret:
        raise SystemExit("Set DEBRIEF_WEBHOOK_SECRET before starting the webhook receiver.")
    print(f"Listening on http://{host}:{port}/gong/webhook", flush=True)
    ThreadingHTTPServer((host, port), make_handler(secret, **kwargs)).serve_forever()


def main() -> None:
    p = argparse.ArgumentParser(description="Run a debrief automatically when a TV transcript arrives.")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch", help="poll for new transcripts")
    w.add_argument("--interval", type=int, default=30)
    s = sub.add_parser("serve", help="webhook receiver")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    sub.add_parser("once", help="one pass, then exit")
    sub.add_parser("call", help="process one deal").add_argument("deal_id")
    a = p.parse_args()
    if a.cmd == "watch":
        watch(a.interval)
    elif a.cmd == "serve":
        serve(a.port, a.host)
    elif a.cmd == "once":
        for r in scan_once():
            print(f"{r['deal_id']}: {r['status']} {r['detail']}")
    else:
        r = process_call(a.deal_id)
        print(f"{r['deal_id']}: {r['status']} {r['detail']}")


if __name__ == "__main__":
    main()
