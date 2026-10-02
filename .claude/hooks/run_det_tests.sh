#!/usr/bin/env bash
# PostToolUse hook: run deterministic tests after an Edit or Write under src/.
# Reads the hook JSON payload on stdin. Exit 2 shows stderr to Claude (the edit already happened).
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path",""))' 2>/dev/null)"
case "$FILE" in
  "$REPO"/src/*|src/*) ;;
  *) exit 0 ;;
esac
cd "$REPO" || exit 0
OUT="$(python3 -m pytest -q tests/deterministic 2>&1)"
STATUS=$?
if [ $STATUS -ne 0 ]; then
  echo "Deterministic tests failed after editing $FILE:" >&2
  echo "$OUT" | tail -40 >&2
  exit 2
fi
exit 0
