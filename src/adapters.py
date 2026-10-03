"""Source and delivery adapters. File-backed mocks only; nothing here touches the network.

Production path (not built):
- GongSource: Gong REST API for call metadata and raw transcripts. The Gong MCP server is
  read-only and does not return raw transcripts, so it is not enough on its own.
- CRMSource: Salesforce Hosted MCP for opportunity, contacts and activity.
- Notifier: Slack MCP or a Bolt app posting the Block Kit card to the AE, SC or manager.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from src.config import ROOT
from src.transcript import Transcript, load_transcript

DATA = ROOT / "data"
VAR = ROOT / "var"


class GongSource(Protocol):
    def transcript(self, deal_id: str) -> Transcript: ...
    def activity(self, deal_id: str) -> dict: ...
    def list_calls(self) -> list[str]: ...


class CRMSource(Protocol):
    def deal(self, deal_id: str) -> dict: ...
    def list_deals(self) -> list[str]: ...


class Notifier(Protocol):
    def send(self, recipient: str, role: str, deal_id: str, kind: str, payload: dict) -> dict: ...


class FileGongSource:
    def __init__(self, data_dir: Path = DATA):
        self.data_dir = data_dir

    def transcript(self, deal_id: str) -> Transcript:
        return load_transcript(deal_id, self.data_dir / "transcripts")

    def activity(self, deal_id: str) -> dict:
        return json.loads((self.data_dir / "gong_activity" / f"{deal_id}.json").read_text(encoding="utf-8"))

    def list_calls(self) -> list[str]:
        return sorted(p.stem for p in (self.data_dir / "transcripts").glob("*.txt"))


class FileCRMSource:
    def __init__(self, data_dir: Path = DATA):
        self.data_dir = data_dir

    def deal(self, deal_id: str) -> dict:
        return json.loads((self.data_dir / "crm" / f"{deal_id}.json").read_text(encoding="utf-8"))

    def list_deals(self) -> list[str]:
        return sorted(p.stem for p in (self.data_dir / "crm").glob("*.json"))


class FileNotifier:
    """Appends messages to a JSONL outbox. Internal messages only; customer email is never sent from here."""

    def __init__(self, outbox: Path = VAR / "outbox.jsonl"):
        self.outbox = outbox

    def send(self, recipient: str, role: str, deal_id: str, kind: str, payload: dict) -> dict:
        if role not in {"ae", "sc", "manager", "csm"}:
            raise ValueError(f"notifier only sends internal messages, got role {role!r}")
        msg = {"sent_at": datetime.now(timezone.utc).isoformat(), "recipient": recipient, "role": role,
               "deal_id": deal_id, "kind": kind, "payload": payload}
        self.outbox.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg) + "\n")
        return msg

    def read_all(self) -> list[dict]:
        if not self.outbox.exists():
            return []
        return [json.loads(line) for line in self.outbox.read_text(encoding="utf-8").splitlines() if line.strip()]


class CRMWriter(Protocol):
    def update_opportunity(self, deal_id: str, fields: dict, source: str) -> dict: ...


class FileCRMWriter:
    """Appends opportunity field updates to a JSONL file. Production path: Salesforce Hosted MCP or the REST API,
    updating the opportunity's NextStep and custom fields. Only fields the AE confirmed are written."""

    def __init__(self, path: Path = VAR / "crm_updates.jsonl"):
        self.path = path

    def update_opportunity(self, deal_id: str, fields: dict, source: str) -> dict:
        row = {"at": datetime.now(timezone.utc).isoformat(), "deal_id": deal_id, "source": source, "fields": fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return row

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


class SlackError(RuntimeError):
    pass


class SlackNotifier:
    """Posts internal messages to Slack with chat.postMessage. Never customer-facing: same role guard as FileNotifier.

    Where it posts: a DM when the recipient's name is in the user map (JSON file named by DEBRIEF_SLACK_USERS,
    {"Sam Lee": "U0123ABC"}), else the shared DEBRIEF_SLACK_CHANNEL with the name in the message. Needs
    DEBRIEF_SLACK_BOT_TOKEN with the chat:write scope (im:write for DMs). The token is never logged."""

    def __init__(self, token: str, channel: str = "", users: dict[str, str] | None = None, app_url: str = "",
                 post=None) -> None:
        if not token or not (channel or users):
            raise ValueError("SlackNotifier needs a token and either a channel or a user map")
        self._token, self.channel, self.users, self.app_url = token, channel, users or {}, app_url
        self._post = post or self._http_post

    def _http_post(self, body: dict) -> dict:
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage", data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def send(self, recipient: str, role: str, deal_id: str, kind: str, payload: dict) -> dict:
        if role not in {"ae", "sc", "manager", "csm"}:
            raise ValueError(f"notifier only sends internal messages, got role {role!r}")
        user = self.users.get(recipient)
        channel = user or self.channel
        if not channel:
            raise SlackError(f"no Slack user for {recipient!r} and no DEBRIEF_SLACK_CHANNEL set")
        from src import blockkit  # local import: blockkit pulls in the transcript module
        text = payload["text"] if user else f"For {recipient} ({role.upper()}): {payload['text']}"
        body = {"channel": channel, "text": text}
        if "blocks" in payload:
            body["blocks"] = blockkit.slack_safe(payload, self.app_url,
                                                 interactive=bool(os.environ.get("DEBRIEF_SLACK_SIGNING_SECRET")))
        reply = self._post(body)
        if not reply.get("ok"):
            raise SlackError(f"Slack rejected the message: {reply.get('error', 'unknown error')}")
        return {"slack_ts": reply.get("ts"), "channel": channel}


class CompositeNotifier:
    """Always writes the file outbox (the app reads it), then tries Slack. A Slack failure never blocks the debrief."""

    def __init__(self, file_notifier: FileNotifier, slack: SlackNotifier | None = None) -> None:
        self.file, self.slack = file_notifier, slack

    def send(self, recipient: str, role: str, deal_id: str, kind: str, payload: dict) -> dict:
        msg = self.file.send(recipient, role, deal_id, kind, payload)
        if self.slack:
            try:
                msg["slack"] = {"ok": True, **self.slack.send(recipient, role, deal_id, kind, payload)}
            except Exception as e:  # network, auth or config problem; report it, do not raise
                msg["slack"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        return msg

    def read_all(self) -> list[dict]:
        return self.file.read_all()


def make_notifier() -> FileNotifier | CompositeNotifier:
    """File outbox always; Slack as well when DEBRIEF_SLACK_BOT_TOKEN is set."""
    file_notifier = FileNotifier()
    token = os.environ.get("DEBRIEF_SLACK_BOT_TOKEN", "")
    if not token:
        return file_notifier
    users_path = os.environ.get("DEBRIEF_SLACK_USERS", "")
    users = json.loads(Path(users_path).read_text(encoding="utf-8")) if users_path else {}
    slack = SlackNotifier(token, os.environ.get("DEBRIEF_SLACK_CHANNEL", ""), users,
                          os.environ.get("DEBRIEF_APP_URL", ""))
    return CompositeNotifier(file_notifier, slack)
