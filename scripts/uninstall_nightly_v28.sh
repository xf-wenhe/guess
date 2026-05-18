#!/usr/bin/env bash
set -euo pipefail

PLIST_NAME="com.guess.nightly-train-v28"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "Uninstalling nightly v28 training..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"
echo "Done."
