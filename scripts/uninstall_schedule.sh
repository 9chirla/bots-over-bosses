#!/usr/bin/env bash
set -euo pipefail

LABEL="com.bots-over-bosses.daily"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST_DEST"

echo "Removed daily schedule ($LABEL)."
