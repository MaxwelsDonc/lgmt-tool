#!/usr/bin/env bash
# LGMT one-command setup (Linux / macOS).
# Usage:  bash setup.sh [--dev] [--demo]
set -euo pipefail

DEV=0; DEMO=0
for arg in "$@"; do
  case "$arg" in
    --dev)  DEV=1 ;;
    --demo) DEMO=1 ;;
    *) echo "unknown flag: $arg (supported: --dev --demo)" >&2; exit 1 ;;
  esac
done

PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "python3 not found; please install Python >= 3.10." >&2; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "Python >= 3.10 required (found $($PY --version))." >&2; exit 1; }

[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q --upgrade pip
pip install -q -e .
[ "$DEV" = 1 ] && pip install -q -e ".[dev]" 

if [ "$DEMO" = 1 ]; then
  lgmt demo
  echo "Report written to demo_output/report.html"
else
  echo "Done. Try: lgmt demo   (offline, no API key needed)"
fi
