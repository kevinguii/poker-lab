#!/usr/bin/env bash
# Starts pokerlab from the repo's virtualenv (creating and installing it on first use).
# Extra arguments go to `pokerlab` (e.g. --port 8001).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev]"
fi

# On macOS the editable-install .pth file can end up flagged "hidden", and Python 3.13 skips hidden .pth files
# ("No module named pokerlab"). Clear the flag, and put src/ on the path regardless.
[ "$(uname)" = "Darwin" ] && chflags nohidden .venv/lib/python*/site-packages/*.pth 2>/dev/null || true
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

exec .venv/bin/python -m pokerlab.cli "$@"
