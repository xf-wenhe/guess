#!/usr/bin/env bash
set -euo pipefail

AGENT_ID="com.guess.nightly-train-v26"
PLIST_PATH="$HOME/Library/LaunchAgents/${AGENT_ID}.plist"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NIGHTLY_ROOT="${NIGHTLY_ROOT:-$ROOT_DIR/.nightly}"
if [[ "$NIGHTLY_ROOT" != /* ]]; then
  NIGHTLY_ROOT="$ROOT_DIR/$NIGHTLY_ROOT"
fi
WRAPPER_SCRIPT="$NIGHTLY_ROOT/nightly_launcher.sh"

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
rm -f "$WRAPPER_SCRIPT"

echo "removed: $PLIST_PATH"
echo "removed: $WRAPPER_SCRIPT"
echo "done"
echo "note: logs and reports in $NIGHTLY_ROOT/logs/ and $NIGHTLY_ROOT/reports/ are preserved"
