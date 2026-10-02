"""One-off data tool: rewrite transcript timestamps so they increase and span a realistic call length.

Speaking time is estimated at 150 words per minute plus a 2 second turn gap. Long solutions
consultant turns get extra screen time for the live demo. Each call is then scaled to its target
length. Run once after editing a transcript: python scripts/retime_transcripts.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.transcript import TRANSCRIPT_DIR, parse_transcript  # noqa: E402

# deal_id: (start second, target start second of the last utterance)
TARGETS = {
    "deal_a": (4, 47 * 60 + 10),
    "deal_b": (3, 41 * 60 + 30),
    "deal_c": (2, 43 * 60 + 5),
    "deal_x": (95, 21 * 60 + 40),
    "deal_y": (3, 31 * 60 + 20),
}
TURN_RE = re.compile(r"^\[(\d{1,3}:\d{2})\](\s+[^:]+:.*)$")


def fmt(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def retime(deal_id: str) -> None:
    path = TRANSCRIPT_DIR / f"{deal_id}.txt"
    text = path.read_text(encoding="utf-8")
    t = parse_transcript(text, deal_id)
    start, end = TARGETS[deal_id]
    raw = [0.0]
    for u in t.utterances[:-1]:
        dur = u.word_count / 2.5 + 2
        if "Solutions Consultant" in u.title and u.word_count >= 25:
            dur += 75  # screen time while the demo runs
        raw.append(raw[-1] + dur)
    scale = (end - start) / raw[-1]
    stamps = [fmt(start + r * scale) for r in raw]

    header, _, body = text.partition("\n---\n")
    out, i = [], 0
    for line in body.splitlines():
        m = TURN_RE.match(line.strip())
        if m:
            out.append(f"[{stamps[i]}]{m.group(2)}")
            i += 1
        else:
            out.append(line)
    path.write_text(header + "\n---\n" + "\n".join(out).rstrip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    for deal in TARGETS:
        retime(deal)
        print(f"retimed {deal}")
