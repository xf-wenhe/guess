#!/usr/bin/env bash
set -euo pipefail

AGENT_ID="com.guess.nightly-train-v26"
PLIST_PATH="$HOME/Library/LaunchAgents/${AGENT_ID}.plist"

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "removed: $PLIST_PATH"
echo "done"
