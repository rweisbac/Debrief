"""Slack interactivity: the buttons and menus on the capture card and the debrief card.

Slack posts every click to one request URL (served by src/web.py at /slack/interactions). Requests are checked
with the app's signing secret before anything else runs. The handler never sends anything to a customer.

Capture card:
- a menu change (cap_sel) stores the edit and redraws the card with the field marked edited
- Edit (cap_edit) opens a modal for that field; saving the modal stores the edit and redraws the card
- Confirm all (cap_confirm) stores the labels, writes the confirmed fields to CRM, and replaces the card with the
  confirmed values and the next best step

Debrief card: act and dismiss buttons log the same events as the app.

Timing: Slack does not say when a person first looked at a message, so seconds_to_complete on Slack runs from the
AE's first tap on the card to Confirm all. A one-tap confirm records 0.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request

from src import blockkit, capture, events, record_store, service
from src.adapters import FileCRMSource

MAX_SKEW_SECONDS = 300


def verify(signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None) -> bool:
    """Slack request signing: v0=HMAC_SHA256(secret, "v0:{timestamp}:{body}"), rejected when older than 5 minutes."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        if abs((now or time.time()) - int(timestamp)) > MAX_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class SlackAPI:
    """The few Slack Web API calls the handler needs. Injected so tests never touch the network."""

    def __init__(self, token: str = "", post=None):
        self._token = token or os.environ.get("DEBRIEF_SLACK_BOT_TOKEN", "")
        self._post = post or self._http_post

    def _http_post(self, url: str, body: dict, auth: bool = True) -> dict:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        try:
            return json.loads(raw)
        except ValueError:
            return {"ok": raw.strip() == b"ok"}

    def call(self, method: str, body: dict) -> dict:
        return self._post(f"https://slack.com/api/{method}", body, True)

    def respond(self, response_url: str, body: dict) -> dict:
        return self._post(response_url, body, False)


# Pending edits per capture card

def _draft(capture_id: str) -> dict:
    with record_store.connect() as conn:
        row = conn.execute("SELECT * FROM capture_drafts WHERE capture_id = ?", (capture_id,)).fetchone()
    if not row:
        return {"edits": {}, "first_action_at": 0.0, "channel": "", "message_ts": ""}
    return {**dict(row), "edits": json.loads(row["edits"])}


def _save_draft(capture_id: str, draft: dict) -> None:
    with record_store.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO capture_drafts VALUES (?, ?, ?, ?, ?)",
                     (capture_id, json.dumps(draft["edits"], sort_keys=True), draft["first_action_at"],
                      draft["channel"], draft["message_ts"]))


def _touch(capture_id: str, payload: dict, now: float) -> dict:
    d = _draft(capture_id)
    if not d["first_action_at"]:
        d["first_action_at"] = now
    container = payload.get("container") or {}
    d["channel"] = d["channel"] or container.get("channel_id") or (payload.get("channel") or {}).get("id", "")
    d["message_ts"] = d["message_ts"] or container.get("message_ts", "")
    return d


def _redraw(cap: dict, d: dict, api: SlackAPI, response_url: str = "") -> None:
    crm = FileCRMSource().deal(cap["deal_id"])
    card = blockkit.capture_card(cap, service.card_routing(cap, crm["owner_ae"]), crm, d["edits"])
    if response_url:
        api.respond(response_url, {"replace_original": True, **card})
    elif d["channel"] and d["message_ts"]:
        api.call("chat.update", {"channel": d["channel"], "ts": d["message_ts"], **card})


def handle(payload: dict, api: SlackAPI | None = None, now: float | None = None) -> dict:
    """Handle one interaction payload. Returns the HTTP body to send back to Slack (usually empty)."""
    api = api or SlackAPI()
    now = now or time.time()
    if payload.get("type") == "view_submission" and (payload.get("view") or {}).get("callback_id") == "cap_edit":
        return _modal_saved(payload, api, now)
    if payload.get("type") != "block_actions":
        return {}
    response_url = payload.get("response_url", "")
    for action in payload.get("actions", []):
        parts = action.get("action_id", "").split("|")
        kind = parts[0]
        if kind == "cap_sel":
            _, cid, field, part = parts
            cap = service.find_capture(cid)
            if cap:
                d = _touch(cid, payload, now)
                d["edits"].setdefault(field, {})[part] = action["selected_option"]["value"]
                _save_draft(cid, d)
                _redraw(cap, d, api, response_url)
        elif kind == "cap_edit":
            _, cid, field = parts
            cap = service.find_capture(cid)
            if cap:
                d = _touch(cid, payload, now)
                _save_draft(cid, d)
                api.call("views.open", {"trigger_id": payload.get("trigger_id", ""),
                                        "view": blockkit.capture_edit_modal(cap, field, d["edits"])})
        elif kind == "cap_confirm":
            _confirm(parts[1], payload, api, now, response_url)
        elif kind.startswith("act_") or kind.startswith("dismiss_"):
            _step_action(kind, action)
    return {}


def _modal_saved(payload: dict, api: SlackAPI, now: float) -> dict:
    meta = json.loads(payload["view"]["private_metadata"])
    cid, field = meta["capture_id"], meta["field"]
    cap = service.find_capture(cid)
    if not cap:
        return {}
    edit = {}
    for block_id, el in payload["view"]["state"]["values"].items():
        v = el.get(block_id) or next(iter(el.values()), {})
        if v.get("type") == "static_select":
            edit[block_id] = (v.get("selected_option") or {}).get("value", "")
        elif v.get("type") == "datepicker":
            edit[block_id] = v.get("selected_date") or ""
        else:
            edit[block_id] = v.get("value") or ""
    d = _touch(cid, payload, now)
    d["edits"][field] = {**d["edits"].get(field, {}), **edit}
    _save_draft(cid, d)
    _redraw(cap, d, api)
    return {"response_action": "clear"}


def _confirm(cid: str, payload: dict, api: SlackAPI, now: float, response_url: str) -> None:
    cap = service.find_capture(cid)
    if not cap:
        return
    crm = FileCRMSource().deal(cap["deal_id"])
    d = _draft(cid)
    seconds = round(now - d["first_action_at"], 1) if d["first_action_at"] else 0.0
    session = service.confirm_capture(cap, crm["owner_ae"], d["edits"], seconds, channel="slack")
    record, _ = service.load_debrief(cap["deal_id"], allow_run=False)
    done = blockkit.capture_done_card(cap, crm, session, record)
    if response_url:
        api.respond(response_url, {"replace_original": True, **done})


def _step_action(kind: str, action: dict) -> None:
    try:
        value = json.loads(action.get("value") or "{}")
    except ValueError:
        return
    deal_id = value.get("deal_id", "")
    if not deal_id:
        return
    if kind.startswith("act_"):
        events.log("step_action_taken", "ae", deal_id, step=value.get("step"), action=value.get("action", ""),
                   channel="slack")
    elif value.get("reason") in events.DISMISS_REASONS:
        events.log("step_dismissed", "ae", deal_id, step=value.get("step"), reason=value["reason"], channel="slack")
