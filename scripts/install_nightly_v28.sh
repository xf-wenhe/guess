#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NIGHTLY_ROOT="${NIGHTLY_ROOT:-$ROOT_DIR/.nightly}"
if [[ "$NIGHTLY_ROOT" != /* ]]; then
    NIGHTLY_ROOT="$ROOT_DIR/$NIGHTLY_ROOT"
fi

RUNNER_ROOT="${NIGHTLY_RUNNER_ROOT:-$NIGHTLY_ROOT/workspaces/guess_runtime}"
WORK_DIR="${NIGHTLY_WORK_DIR:-$NIGHTLY_ROOT/data/tmp}"
MODELS_DIR="${NIGHTLY_MODELS_DIR:-$NIGHTLY_ROOT/data/models}"
CALIB_DIR="${NIGHTLY_CALIB_DIR:-$NIGHTLY_ROOT/data/calib}"
LOG_DIR="${NIGHTLY_LOG_DIR:-$NIGHTLY_ROOT/logs}"
SYNC_BACK_ROOT="${NIGHTLY_SYNC_BACK_ROOT:-$ROOT_DIR}"

if [[ "$RUNNER_ROOT" != /* ]]; then RUNNER_ROOT="$ROOT_DIR/$RUNNER_ROOT"; fi
if [[ "$WORK_DIR" != /* ]]; then WORK_DIR="$ROOT_DIR/$WORK_DIR"; fi
if [[ "$MODELS_DIR" != /* ]]; then MODELS_DIR="$ROOT_DIR/$MODELS_DIR"; fi
if [[ "$CALIB_DIR" != /* ]]; then CALIB_DIR="$ROOT_DIR/$CALIB_DIR"; fi
if [[ "$LOG_DIR" != /* ]]; then LOG_DIR="$ROOT_DIR/$LOG_DIR"; fi
if [[ "$SYNC_BACK_ROOT" != /* ]]; then SYNC_BACK_ROOT="$ROOT_DIR/$SYNC_BACK_ROOT"; fi

BASE_MODEL_NAME="bge-m3-finetuned-v27-semreal-anchor"
BASE_MODEL_SOURCE="$ROOT_DIR/models/$BASE_MODEL_NAME"
BASE_MODEL_TARGET="$MODELS_DIR/$BASE_MODEL_NAME"
BASE_CALIB_SOURCE="$ROOT_DIR/data/semantic_calibration_v27_semreal_anchor.json"
BASE_CALIB_TARGET="$CALIB_DIR/semantic_calibration_v27_semreal_anchor.json"

PLIST_NAME="com.guess.nightly-train-v28"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$NIGHTLY_ROOT" "$RUNNER_ROOT" "$WORK_DIR" "$MODELS_DIR" "$CALIB_DIR" "$LOG_DIR"

if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude ".git/" \
        --exclude ".nightly/" \
        --exclude "build/" \
        --exclude "tmp/" \
        "$ROOT_DIR/" "$RUNNER_ROOT/"
else
    rm -rf "$RUNNER_ROOT"
    mkdir -p "$RUNNER_ROOT"
    cp -R "$ROOT_DIR/." "$RUNNER_ROOT/"
    rm -rf "$RUNNER_ROOT/.git" "$RUNNER_ROOT/.nightly" "$RUNNER_ROOT/build" "$RUNNER_ROOT/tmp"
fi

if [[ ! -d "$BASE_MODEL_SOURCE" || ! -f "$BASE_CALIB_SOURCE" ]]; then
    echo "missing v28 base artifacts under source repo" >&2
    echo "base_model_source=$BASE_MODEL_SOURCE" >&2
    echo "base_calib_source=$BASE_CALIB_SOURCE" >&2
    exit 1
fi

if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$BASE_MODEL_SOURCE/" "$BASE_MODEL_TARGET/"
else
    rm -rf "$BASE_MODEL_TARGET"
    mkdir -p "$BASE_MODEL_TARGET"
    cp -R "$BASE_MODEL_SOURCE/." "$BASE_MODEL_TARGET/"
fi
cp "$BASE_CALIB_SOURCE" "$BASE_CALIB_TARGET"

echo "Installing nightly v28 training..."
echo "  plist: $PLIST_PATH"
echo "  schedule: 22:00 daily"
echo "  script: $RUNNER_ROOT/scripts/nightly_train_v28.sh"
echo "  nightly_root: $NIGHTLY_ROOT"
echo "  runner_root: $RUNNER_ROOT"
echo "  work_dir: $WORK_DIR"
echo "  models_dir: $MODELS_DIR"
echo "  calib_dir: $CALIB_DIR"
echo "  log_dir: $LOG_DIR"
echo "  sync_back_root: $SYNC_BACK_ROOT"

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
        <string>scripts/nightly_train_v28.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>22</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>${RUNNER_ROOT}</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd_nightly_v28.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd_nightly_v28.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>NIGHTLY_ROOT</key>
        <string>${NIGHTLY_ROOT}</string>
        <key>NIGHTLY_PROJECT_ROOT</key>
        <string>${ROOT_DIR}</string>
        <key>NIGHTLY_WORK_DIR</key>
        <string>${WORK_DIR}</string>
        <key>NIGHTLY_SYNC_BACK_ROOT</key>
        <string>${SYNC_BACK_ROOT}</string>
        <key>NIGHTLY_ENFORCE_FREE_SPACE_CHECK</key>
        <string>1</string>
        <key>NIGHTLY_MIN_FREE_GB</key>
        <string>24</string>
        <key>SEM_BASE_MODEL</key>
        <string>${BASE_MODEL_TARGET}</string>
        <key>SEM_OUTPUT_MODEL</key>
        <string>${MODELS_DIR}/bge-m3-finetuned-v28c-candidate</string>
        <key>SEM_BASE_CALIB</key>
        <string>${BASE_CALIB_TARGET}</string>
        <key>SEM_OUTPUT_CALIB</key>
        <string>${CALIB_DIR}/semantic_calibration_v28c_candidate.json</string>
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
echo "  logs:   tail -f $WORK_DIR/nightly_train_v28_*.log"
echo "  remove: bash scripts/uninstall_nightly_v28.sh"
