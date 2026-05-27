#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "please run as root: sudo bash scripts/uninstall_nightly_10pm_daemon.sh" >&2
  exit 1
fi

LABEL="com.guess.nightly-train-v26.daemon"
PLIST_PATH="/Library/LaunchDaemons/${LABEL}.plist"
DAEMON_MAIN_SCRIPT="/private/tmp/com.guess.nightly-train-v26.main.sh"
DAEMON_WRAPPER_SCRIPT="/private/tmp/com.guess.nightly-train-v26.wrapper.sh"

launchctl bootout "system/${LABEL}" >/dev/null 2>&1 || true
launchctl disable "system/${LABEL}" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
rm -f "$DAEMON_MAIN_SCRIPT" "$DAEMON_WRAPPER_SCRIPT"

echo "removed daemon: $PLIST_PATH"
echo "done"
