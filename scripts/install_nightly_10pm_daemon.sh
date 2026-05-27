#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "please run as root: sudo bash scripts/install_nightly_10pm_daemon.sh" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

NIGHTLY_ROOT="${NIGHTLY_ROOT:-$ROOT_DIR/.nightly}"
if [[ "$NIGHTLY_ROOT" != /* ]]; then
  NIGHTLY_ROOT="$ROOT_DIR/$NIGHTLY_ROOT"
fi

RUN_AS_USER="${NIGHTLY_RUN_AS_USER:-${SUDO_USER:-$(stat -f '%Su' "$ROOT_DIR")}}"
RUN_AS_GROUP="${NIGHTLY_RUN_AS_GROUP:-$(id -gn "$RUN_AS_USER")}"
RUN_AS_HOME="$(dscl . -read "/Users/$RUN_AS_USER" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
if [[ -z "$RUN_AS_HOME" ]]; then
  RUN_AS_HOME="/Users/$RUN_AS_USER"
fi
AGENT_OWNER_USER="$RUN_AS_USER"
AGENT_OWNER_HOME="$(dscl . -read "/Users/$AGENT_OWNER_USER" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
if [[ -z "$AGENT_OWNER_HOME" ]]; then
  AGENT_OWNER_HOME="/Users/$AGENT_OWNER_USER"
fi

AGENT_LABEL="com.guess.nightly-train-v26.daemon"
PLIST_PATH="/Library/LaunchDaemons/${AGENT_LABEL}.plist"

RUNNER_DATA_DIR="${NIGHTLY_RUNNER_DATA_DIR:-$NIGHTLY_ROOT/data}"
RUNNER_TMP_DIR="$RUNNER_DATA_DIR/tmp"
RUNNER_MODELS_DIR="$RUNNER_DATA_DIR/models"
RUNNER_CALIB_DIR="$RUNNER_DATA_DIR/calib"
RUNNER_GOLD_DIR="$RUNNER_DATA_DIR/gold"
RUNNER_WORKSPACES_DIR="${NIGHTLY_RUNNER_WORKSPACES_DIR:-$NIGHTLY_ROOT/workspaces}"
RUNNER_ROOT="$RUNNER_WORKSPACES_DIR/guess_runtime"
TRAIN_SCRIPT_PATH="$RUNNER_ROOT/scripts/nightly_train_v26.sh"
LAUNCHD_LOG_DIR="${NIGHTLY_LAUNCHD_LOG_DIR:-$NIGHTLY_ROOT/logs}"
SYNC_BACK_ROOT="${NIGHTLY_SYNC_BACK_ROOT:-$ROOT_DIR}"
STDOUT_LOG="$LAUNCHD_LOG_DIR/launchd_nightly_v26.daemon.out.log"
STDERR_LOG="$LAUNCHD_LOG_DIR/launchd_nightly_v26.daemon.err.log"
SYSTEM_STDOUT_LOG="/tmp/launchd_nightly_v26.daemon.out.log"
SYSTEM_STDERR_LOG="/tmp/launchd_nightly_v26.daemon.err.log"
DAEMON_MAIN_SCRIPT="/private/tmp/com.guess.nightly-train-v26.main.sh"
DAEMON_WRAPPER_SCRIPT="/private/tmp/com.guess.nightly-train-v26.wrapper.sh"

BASE_MODEL_NAME="bge-m3-finetuned-v27-semreal-anchor"
BASE_MODEL_SOURCE="$ROOT_DIR/models/$BASE_MODEL_NAME"
BASE_MODEL_TARGET="$RUNNER_MODELS_DIR/$BASE_MODEL_NAME"
BASE_CALIB_SOURCE="$ROOT_DIR/data/semantic_calibration_v27_semreal_anchor.json"
BASE_CALIB_TARGET="$RUNNER_CALIB_DIR/semantic_calibration_v27_semreal_anchor.json"

mkdir -p "$NIGHTLY_ROOT" "$RUNNER_DATA_DIR" "$RUNNER_WORKSPACES_DIR" "$LAUNCHD_LOG_DIR"
mkdir -p "$RUNNER_TMP_DIR" "$RUNNER_MODELS_DIR" "$RUNNER_CALIB_DIR" "$RUNNER_GOLD_DIR" "$SYNC_BACK_ROOT/models" "$SYNC_BACK_ROOT/data"

chown -R "$RUN_AS_USER:$RUN_AS_GROUP" "$NIGHTLY_ROOT" "$SYNC_BACK_ROOT/models" "$SYNC_BACK_ROOT/data"

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

if [[ ! -d "$BASE_MODEL_SOURCE" ]]; then
  echo "missing base model source: $BASE_MODEL_SOURCE" >&2
  exit 1
fi
if [[ ! -f "$BASE_CALIB_SOURCE" ]]; then
  echo "missing base calibration source: $BASE_CALIB_SOURCE" >&2
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

cp "$RUNNER_ROOT/scripts/nightly_train_v26.sh" "$DAEMON_MAIN_SCRIPT"
chmod 755 "$DAEMON_MAIN_SCRIPT"
chown root:wheel "$DAEMON_MAIN_SCRIPT"

cat > "$DAEMON_WRAPPER_SCRIPT" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export NIGHTLY_SCRIPT_ROOT="${RUNNER_ROOT}"
cd "${RUNNER_ROOT}"
exec /bin/bash "${DAEMON_MAIN_SCRIPT}"
WRAP
chmod 755 "$DAEMON_WRAPPER_SCRIPT"
chown root:wheel "$DAEMON_WRAPPER_SCRIPT"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${AGENT_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${DAEMON_WRAPPER_SCRIPT}</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/</string>

  <key>UserName</key>
  <string>${RUN_AS_USER}</string>
  <key>GroupName</key>
  <string>${RUN_AS_GROUP}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${RUN_AS_HOME}</string>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>

    <key>NIGHTLY_ROOT</key>
    <string>${NIGHTLY_ROOT}</string>
    <key>NIGHTLY_PROJECT_ROOT</key>
    <string>${ROOT_DIR}</string>
    <key>NIGHTLY_WORK_DIR</key>
    <string>${RUNNER_TMP_DIR}</string>
    <key>NIGHTLY_SYNC_BACK_ROOT</key>
    <string>${SYNC_BACK_ROOT}</string>

    <key>NIGHTLY_ENFORCE_FREE_SPACE_CHECK</key>
    <string>1</string>
    <key>NIGHTLY_MIN_FREE_GB</key>
    <string>24</string>

    <key>NIGHTLY_AUTO_PROMOTE</key>
    <string>1</string>
    <key>NIGHTLY_DELETE_OLD_ON_PROMOTE</key>
    <string>1</string>
    <key>NIGHTLY_DELETE_REJECTED_CANDIDATE</key>
    <string>1</string>
    <key>NIGHTLY_MIN_MAE_IMPROVEMENT</key>
    <string>0.005</string>
    <key>NIGHTLY_MIN_ACC_IMPROVEMENT</key>
    <string>0.0</string>
    <key>NIGHTLY_REQUIRE_NO_DEGRADE_ALL</key>
    <string>0</string>
    <key>NIGHTLY_REQUIRE_STRICT_IMPROVEMENT</key>
    <string>1</string>
    <key>NIGHTLY_BASE_SEED</key>
    <string>20260303</string>
    <key>NIGHTLY_TOTAL_RUNS</key>
    <string>1</string>
    <key>NIGHTLY_CONTINUE_ON_ROUND_ERROR</key>
    <string>1</string>

    <key>NIGHTLY_BUILD_TIMEOUT_SEC</key>
    <string>1200</string>
    <key>NIGHTLY_PRETRAIN_TIMEOUT_SEC</key>
    <string>10800</string>
    <key>NIGHTLY_ANCHOR_TIMEOUT_SEC</key>
    <string>7200</string>
    <key>NIGHTLY_EVAL_TIMEOUT_SEC</key>
    <string>1800</string>
    <key>NIGHTLY_REGRESSION_TIMEOUT_SEC</key>
    <string>1200</string>

    <key>NIGHTLY_ENABLE_ANCHOR_FINETUNE</key>
    <string>1</string>
    <key>NIGHTLY_ANCHOR_LEARNING_RATE</key>
    <string>1.5e-6</string>
    <key>SEM_MAX_PAIRS</key>
    <string>1600</string>
    <key>SEM_LEARNING_RATE</key>
    <string>1.8e-6</string>

    <key>SEM_UNSUP_PAIRS_JSONL</key>
    <string>${RUNNER_GOLD_DIR}/unsupervised_pairs_v26.jsonl</string>
    <key>SEM_GOLD_POOL_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_pool.csv</string>
    <key>SEM_GOLD_CALIB_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_calib.csv</string>
    <key>SEM_GOLD_EVAL_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_eval.csv</string>
    <key>SEM_GOLD_MANUAL_ANCHOR_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_manual_anchor.csv</string>
    <key>SEM_ANCHOR_TRAIN_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_manual_anchor.csv</string>

    <key>SEM_BASE_MODEL</key>
    <string>${BASE_MODEL_TARGET}</string>
    <key>SEM_OUTPUT_MODEL</key>
    <string>${RUNNER_MODELS_DIR}/bge-m3-finetuned-local-candidate</string>
    <key>SEM_ANCHOR_MODEL</key>
    <string>${RUNNER_MODELS_DIR}/bge-m3-finetuned-local-candidate-anchor</string>
    <key>SEM_BASE_CALIB</key>
    <string>${BASE_CALIB_TARGET}</string>
    <key>SEM_OUTPUT_CALIB</key>
    <string>${RUNNER_CALIB_DIR}/semantic_calibration_local_candidate.json</string>
  </dict>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>23</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>RunAtLoad</key>
  <false/>

  <key>StandardOutPath</key>
  <string>${SYSTEM_STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${SYSTEM_STDERR_LOG}</string>
</dict>
</plist>
PLIST

chmod 644 "$PLIST_PATH"
chown root:wheel "$PLIST_PATH"

launchctl bootout "system/${AGENT_LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap system "$PLIST_PATH"
launchctl enable "system/${AGENT_LABEL}"

# Avoid duplicated schedules from previous LaunchAgent.
OLD_AGENT_LABEL="com.guess.nightly-train-v26"
OLD_AGENT_PLIST="$AGENT_OWNER_HOME/Library/LaunchAgents/${OLD_AGENT_LABEL}.plist"
launchctl bootout "gui/$(id -u "$AGENT_OWNER_USER")/${OLD_AGENT_LABEL}" >/dev/null 2>&1 || true
rm -f "$OLD_AGENT_PLIST"

echo "installed daemon: $PLIST_PATH"
echo "label: $AGENT_LABEL"
echo "run_as_user: $RUN_AS_USER"
echo "schedule: every day 23:00"
echo "runner_root: $RUNNER_ROOT"
echo "sync_back_root: $SYNC_BACK_ROOT"
echo "logs: $SYSTEM_STDOUT_LOG / $SYSTEM_STDERR_LOG"
echo "daemon_entry: $DAEMON_WRAPPER_SCRIPT"
echo "daemon_main: $DAEMON_MAIN_SCRIPT"
echo "check: sudo launchctl print system/${AGENT_LABEL} | egrep 'state =|last exit code =|runs ='"
echo "note: daemon runs as ${RUN_AS_USER}; if permissions drift, run: sudo chown -R ${RUN_AS_USER}:${RUN_AS_GROUP} '$ROOT_DIR/.nightly'"
