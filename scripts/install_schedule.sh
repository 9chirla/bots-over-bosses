#!/usr/bin/env bash
# Install (or reinstall) daily 07:00 local-time launchd job.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.bots-over-bosses.daily"
PLIST_SRC="$ROOT/scripts/com.bots-over-bosses.daily.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

chmod +x "$ROOT/scripts/run_daily.sh"
mkdir -p "$ROOT/logs"

sed "s|__PROJECT_ROOT__|$ROOT|g" "$PLIST_SRC" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed daily schedule: 07:00 local time"
echo "Plist: $PLIST_DEST"
echo "Logs:  $ROOT/logs/"
echo ""
echo "Test now:  bash $ROOT/scripts/run_daily.sh"
echo "Remove:    launchctl bootout gui/$(id -u)/$LABEL && rm $PLIST_DEST"
