"""Source and delivery adapters. File-backed mocks only; nothing here touches the network.

Production path (not built):
- GongSource: Gong REST API for call metadata and raw transcripts. The Gong MCP server is
  read-only and does not return raw transcripts, so it is not enough on its own.
- CRMSource: Salesforce Hosted MCP for opportunity, contacts and activity.
- Notifier: Slack MCP or a Bolt app posting the Block Kit card to the AE, SC or manager.
"""
from __future__ import annotations

import json
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
