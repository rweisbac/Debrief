"""Load versioned prompts from prompts/<step>/v<N>.md. The highest N wins unless pinned."""
from __future__ import annotations

import json
import re
from functools import lru_cache

from src import config
from src.config import ROOT

PROMPTS_DIR = ROOT / "prompts"
DATA = ROOT / "data"
_V = re.compile(r"^v(\d+)\.md$")


def versions(step: str) -> list[int]:
    d = PROMPTS_DIR / step
    return sorted(int(m.group(1)) for p in d.glob("v*.md") if (m := _V.match(p.name)))


def load(step: str, version: int | None = None) -> tuple[str, str]:
    """Return (text, "v<N>")."""
    available = versions(step)
    if not available:
        raise FileNotFoundError(f"no prompt versions for step {step!r}")
    if version is None:
        version = config.PROMPT_PINS.get(step)
    n = version if version is not None else available[-1]
    if n not in available:
        raise FileNotFoundError(f"prompt {step}/v{n}.md does not exist")
    return (PROMPTS_DIR / step / f"v{n}.md").read_text(encoding="utf-8").strip(), f"v{n}"


@lru_cache(maxsize=1)
def stable_reference() -> tuple[str, str]:
    """The cached prefix shared by every step: preamble, playbook, release cards, competitors.

    Returns (text, version label). Content is read from files and serialized with sorted keys,
    so it is byte identical across calls and the prompt cache can hit.
    """
    shared, shared_v = load("shared")
    playbook = config.PLAYBOOK_FILE.read_text(encoding="utf-8").strip()
    cards = json.loads((DATA / "release_cards.json").read_text(encoding="utf-8"))["cards"]
    competitors = json.loads((DATA / "competitors.json").read_text(encoding="utf-8"))["competitors"]
    text = "\n\n".join([
        shared,
        "<playbook>\n" + playbook + "\n</playbook>",
        "<release_cards>\n" + json.dumps(cards, indent=1, sort_keys=True) + "\n</release_cards>",
        "<competitor_notes>\n" + json.dumps(competitors, indent=1, sort_keys=True) + "\n</competitor_notes>",
    ])
    return text, f"shared-{shared_v}"


def playbook_rule_ids() -> set[str]:
    return set(re.findall(r"^## (PB-\d{2}):", config.PLAYBOOK_FILE.read_text(encoding="utf-8"), flags=re.M))


def release_card_ids() -> set[str]:
    return {c["id"] for c in json.loads((DATA / "release_cards.json").read_text(encoding="utf-8"))["cards"]}
