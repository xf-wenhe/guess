#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

NIGHTLY_ROOT="${NIGHTLY_ROOT:-$ROOT_DIR/.nightly}"
if [[ "$NIGHTLY_ROOT" != /* ]]; then
  NIGHTLY_ROOT="$ROOT_DIR/$NIGHTLY_ROOT"
fi

AGENT_ID="com.guess.nightly-train-v26"
PLIST_PATH="$HOME/Library/LaunchAgents/${AGENT_ID}.plist"
LOGS_DIR="${NIGHTLY_LOGS_DIR:-$HOME/.guess_nightly/logs}"
LAUNCHER_DIR="${NIGHTLY_LAUNCHER_DIR:-$HOME/.guess_nightly}"
STDOUT_LOG="$LOGS_DIR/launchd_nightly_v26.out.log"
STDERR_LOG="$LOGS_DIR/launchd_nightly_v26.err.log"
REPORTS_DIR="$NIGHTLY_ROOT/reports"
DATA_TMP="$NIGHTLY_ROOT/data/tmp"
DATA_MODELS="$NIGHTLY_ROOT/data/models"
DATA_CALIB="$NIGHTLY_ROOT/data/calib"
DATA_GOLD="$NIGHTLY_ROOT/data/gold"

PROJECT_MODEL_NAME="bge-m3-finetuned-v27-semreal-anchor"
PROJECT_CALIB_NAME="semantic_calibration_v27_semreal_anchor.json"

mkdir -p "$HOME/Library/LaunchAgents" "$LOGS_DIR" "$LAUNCHER_DIR" "$REPORTS_DIR" "$DATA_TMP" "$DATA_MODELS" "$DATA_CALIB" "$DATA_GOLD"
mkdir -p "$ROOT_DIR/models" "$ROOT_DIR/data"

archive_log_if_present() {
  local log_path="$1"
  local stamp
  stamp="$(date +%Y%m%d_%H%M%S)"
  if [[ -f "$log_path" ]]; then
    mv "$log_path" "${log_path}.${stamp}.bak"
  fi
}

archive_log_if_present "$STDOUT_LOG"
archive_log_if_present "$STDERR_LOG"

# Validate project model exists
if [[ ! -d "$ROOT_DIR/models/$PROJECT_MODEL_NAME" ]]; then
  echo "missing project model: $ROOT_DIR/models/$PROJECT_MODEL_NAME" >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/data/$PROJECT_CALIB_NAME" ]]; then
  echo "missing project calibration: $ROOT_DIR/data/$PROJECT_CALIB_NAME" >&2
  exit 1
fi

# Create wrapper script under HOME. Launchd can hit Operation-not-permitted
# restrictions when executing wrappers directly from an external project volume.
WRAPPER_SCRIPT="$LAUNCHER_DIR/nightly_launcher.sh"
cat > "$WRAPPER_SCRIPT" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export NIGHTLY_SCRIPT_ROOT="${ROOT_DIR}"
cd "${ROOT_DIR}"
exec /bin/bash "${ROOT_DIR}/scripts/nightly_train_v26.sh"
WRAPPER
chmod 755 "$WRAPPER_SCRIPT"

# Build plist
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${AGENT_ID}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${WRAPPER_SCRIPT}</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${HOME}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>NIGHTLY_ROOT</key>
    <string>${ROOT_DIR}/.nightly</string>
    <key>NIGHTLY_WORK_DIR</key>
    <string>${DATA_TMP}</string>
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
    <string>0.3</string>
    <key>NIGHTLY_MIN_ACC_IMPROVEMENT</key>
    <string>2.0</string>
    <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key>
    <string>0.0</string>
    <key>NIGHTLY_REQUIRE_NO_DEGRADE_ALL</key>
    <string>1</string>
    <key>NIGHTLY_REQUIRE_STRICT_IMPROVEMENT</key>
    <string>1</string>
    <key>NIGHTLY_TRAIN_PROFILE</key>
    <string>daily</string>
    <key>NIGHTLY_SUP_LOSS_MODE</key>
    <string>mixed</string>
    <key>NIGHTLY_SUP_MIN_TAG_ROWS</key>
    <string>antonym_mid:45</string>
    <key>NIGHTLY_BASE_SEED</key>
    <string>20260303</string>
    <key>NIGHTLY_TOTAL_RUNS</key>
    <string>3</string>
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
    <string>0</string>
    <key>NIGHTLY_ANCHOR_LEARNING_RATE</key>
    <string>1.5e-6</string>
    <key>SEM_MAX_PAIRS</key>
    <string>1600</string>
    <key>SEM_LEARNING_RATE</key>
    <string>1.8e-6</string>
    <key>SEM_UNSUP_PAIRS_JSONL</key>
    <string>${DATA_GOLD}/unsupervised_pairs_v26.jsonl</string>
    <key>SEM_GOLD_POOL_CSV</key>
    <string>${DATA_GOLD}/gold_v26_pool.csv</string>
    <key>SEM_GOLD_CALIB_CSV</key>
    <string>${DATA_GOLD}/gold_v26_calib.csv</string>
    <key>SEM_GOLD_EVAL_CSV</key>
    <string>${DATA_GOLD}/gold_v26_eval.csv</string>
    <key>SEM_GOLD_MANUAL_ANCHOR_CSV</key>
    <string>${DATA_GOLD}/gold_v26_manual_anchor.csv</string>
    <key>SEM_ANCHOR_TRAIN_CSV</key>
    <string>${DATA_GOLD}/gold_v26_manual_anchor.csv</string>
    <key>NIGHTLY_PROJECT_MODEL_NAME</key>
    <string>${PROJECT_MODEL_NAME}</string>
    <key>NIGHTLY_PROJECT_CALIB_NAME</key>
    <string>${PROJECT_CALIB_NAME}</string>
    <key>SEM_BASE_MODEL</key>
    <string>${DATA_MODELS}/${PROJECT_MODEL_NAME}</string>
    <key>SEM_OUTPUT_MODEL</key>
    <string>${DATA_MODELS}/bge-m3-finetuned-local-candidate</string>
    <key>SEM_ANCHOR_MODEL</key>
    <string>${DATA_MODELS}/bge-m3-finetuned-local-candidate-anchor</string>
    <key>SEM_BASE_CALIB</key>
    <string>${DATA_CALIB}/${PROJECT_CALIB_NAME}</string>
    <key>SEM_OUTPUT_CALIB</key>
    <string>${DATA_TMP}/semantic_calibration_local_candidate.json</string>
  </dict>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>23</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

chmod 644 "$PLIST_PATH"

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"

echo "installed: $PLIST_PATH"
echo "schedule: every day 23:00"
echo "project_root: $ROOT_DIR"
echo "nightly_root: $NIGHTLY_ROOT"
echo "wrapper_script: $WRAPPER_SCRIPT"
echo "logs: $STDOUT_LOG / $STDERR_LOG"
echo "reports: $REPORTS_DIR"
echo "train_profile: daily"
echo "total_runs: 3"
echo "model: $PROJECT_MODEL_NAME"
echo "calib: $PROJECT_CALIB_NAME"
echo "auto_promote: 1"
echo "check: launchctl list | grep ${AGENT_ID}"
