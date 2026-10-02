"""Fail if any tracked text file contains an em dash. Run: python scripts/check_style.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "fixtures", ".venv"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".txt", ".csv", ".toml", ".sh", ".yml", ".yaml", ""}
EM_DASH = chr(0x2014)  # built from the code point so this file stays clean


def find_em_dashes(root: Path = ROOT) -> list[str]:
    hits = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name != "Makefile":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            if EM_DASH in line:
                hits.append(f"{path.relative_to(root)}:{n}")
    return hits


if __name__ == "__main__":
    found = find_em_dashes()
    for h in found:
        print(f"em dash: {h}")
    sys.exit(1 if found else 0)
