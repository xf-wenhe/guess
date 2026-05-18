#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_NAME="com.guess.nightly-train-v28"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "Installing nightly v28 training..."
echo "  plist: $PLIST_PATH"
echo "  schedule: 22:00 daily"
echo "  script: $ROOT_DIR/scripts/nightly_train_v28.sh"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${ROOT_DIR}/scripts/nightly_train_v28.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>22</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>${ROOT_DIR}</string>
    <key>StandardOutPath</key>
    <string>${ROOT_DIR}/tmp/launchd_nightly_v28.out.log</string>
    <key>StandardErrorPath</key>
    <string>${ROOT_DIR}/tmp/launchd_nightly_v28.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "Installed. Checking..."
launchctl list | grep "$PLIST_NAME" || echo "  (not yet loaded, will trigger at 22:00)"
echo ""
echo "Commands:"
echo "  check:  launchctl list | grep v28"
echo "  manual: NIGHTLY_AUTO_PROMOTE=0 bash scripts/nightly_train_v28.sh"
echo "  dry:    NIGHTLY_DRY_RUN=1 bash scripts/nightly_train_v28.sh"
echo "  logs:   tail -f tmp/nightly_train_v28_*.log"
echo "  remove: bash scripts/uninstall_nightly_v28.sh"
