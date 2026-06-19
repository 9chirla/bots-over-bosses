#!/usr/bin/env bash
# Daily job search — use with launchd, cron, or run manually.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/logs"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
python3 main.py
