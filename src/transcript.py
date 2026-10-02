"""Transcript parsing, utterance lookup and evidence resolution.

Quotes shown in the UI come only from render_quote(), which reads the utterance table.
The model supplies utterance IDs and short excerpts; code checks them and renders the text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from src.config import ROOT

TRANSCRIPT_DIR = ROOT / "data" / "transcripts"
FUZZY_THRESHOLD = 95
TURN_RE = re.compile(r"^\[(\d{1,3}:\d{2})\]\s+([^:]+):\s*(.*)$")
_WS = re.compile(r"\s+")
_PUNCT_EDGES = re.compile(r"^[\s\"'.,;:!?]+|[\s\"'.,;:!?]+$")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


class TranscriptError(ValueError):
    pass


@dataclass(frozen=True)
class Participant:
    name: str
    title: str
    side: str  # "customer" or "apex"


@dataclass
class Utterance:
    id: str
    speaker: str
    title: str
    side: str
    start_timestamp: str
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Transcript:
    deal_id: str
    participants: list[Participant]
    utterances: list[Utterance] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._by_id = {u.id: u for u in self.utterances}

    def get(self, utterance_id: str) -> Utterance | None:
        return self._by_id.get(utterance_id.strip().upper())

    def render_for_model(self) -> str:
        return "\n".join(
            f"[{u.id} | {u.start_timestamp} | {u.speaker}, {u.title} ({u.side})] {u.text}"
            for u in self.utterances
        )

    def substantive_customer_utterances(self, min_words: int = 8) -> list[Utterance]:
        return [u for u in self.utterances if u.side == "customer" and u.word_count >= min_words]

    @property
    def word_count(self) -> int:
        return sum(u.word_count for u in self.utterances)

    def full_text(self) -> str:
        return "\n".join(u.text for u in self.utterances)

    def resolve_evidence(self, utterance_id: str, excerpt: str) -> tuple[bool, str]:
        """Return (ok, reason). ok when the ID exists and the excerpt matches that utterance."""
        u = self.get(utterance_id)
        if u is None:
            return False, f"utterance {utterance_id!r} does not exist"
        ex = normalize(excerpt)
        if not ex:
            return False, f"empty excerpt for {utterance_id}"
        target = normalize(u.text)
        if ex in target:
            return True, "exact"
        score = fuzz.partial_ratio(ex, target)
        if score >= FUZZY_THRESHOLD:
            # Fuzzy matching tolerates a one character change, which can turn 4.7 into 5.
            # Numbers must therefore match exactly even when the rest of the excerpt is fuzzy.
            target_numbers = set(_NUMBER.findall(target))
            missing = [n for n in _NUMBER.findall(ex) if n not in target_numbers]
            if missing:
                return False, f"number {missing[0]!r} not in {u.id} (fuzzy {score:.0f} rejected)"
            return True, f"fuzzy {score:.0f}"
        return False, f"excerpt not found in {u.id} (best partial_ratio {score:.0f})"

    def render_quote(self, utterance_id: str) -> dict:
        """Verbatim quote for the UI, built from the utterance table only."""
        u = self.get(utterance_id)
        if u is None:
            raise TranscriptError(f"cannot render quote, unknown utterance {utterance_id!r}")
        return {"utterance_id": u.id, "speaker": u.speaker, "title": u.title, "side": u.side,
                "timestamp": u.start_timestamp, "text": u.text}


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = _WS.sub(" ", text).strip().lower()
    return _PUNCT_EDGES.sub("", text)


def parse_transcript(text: str, deal_id: str = "") -> Transcript:
    header, sep, body = text.partition("\n---\n")
    if not sep:
        raise TranscriptError("missing '---' separator after PARTICIPANTS header")
    participants: list[Participant] = []
    for line in header.splitlines():
        line = line.strip()
        if not line or line.upper() == "PARTICIPANTS" or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3 or parts[2] not in {"customer", "apex"}:
            raise TranscriptError(f"bad participant line: {line!r}")
        participants.append(Participant(*parts))
    by_name = {p.name: p for p in participants}

    turns: list[list[str]] = []  # [timestamp, speaker, text]
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = TURN_RE.match(line)
        if m:
            ts, speaker, said = m.groups()
            speaker = speaker.strip()
            if speaker not in by_name:
                raise TranscriptError(f"unknown speaker {speaker!r} at [{ts}]")
            turns.append([ts, speaker, said.strip()])
        elif turns:
            turns[-1][2] = f"{turns[-1][2]} {line}".strip()
        else:
            raise TranscriptError(f"text before first turn: {line!r}")

    utterances = []
    for i, (ts, speaker, said) in enumerate(turns, 1):
        p = by_name[speaker]
        utterances.append(Utterance(id=f"U{i:03d}", speaker=p.name, title=p.title, side=p.side,
                                    start_timestamp=ts, text=said))
    return Transcript(deal_id=deal_id, participants=participants, utterances=utterances)


def load_transcript(deal_id: str, directory: Path = TRANSCRIPT_DIR) -> Transcript:
    path = directory / f"{deal_id}.txt"
    return parse_transcript(path.read_text(encoding="utf-8"), deal_id=deal_id)
