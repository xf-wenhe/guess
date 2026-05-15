#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
SOURCE_ROOT="$ROOT_DIR"

AGENT_ID="com.guess.nightly-train-v26"
PLIST_PATH="$HOME/Library/LaunchAgents/${AGENT_ID}.plist"
RUNNER_DATA_REAL_DIR="${NIGHTLY_RUNNER_DATA_REAL_DIR:-$HOME/.guess_nightly/nightly_data}"
RUNNER_DATA_LINK_DIR="${NIGHTLY_RUNNER_DATA_LINK_DIR:-$RUNNER_DATA_REAL_DIR}"
RUNNER_DATA_DIR="${NIGHTLY_RUNNER_DATA_DIR:-$RUNNER_DATA_LINK_DIR}"
RUNNER_TMP_DIR="$RUNNER_DATA_DIR/tmp"
RUNNER_MODELS_DIR="$RUNNER_DATA_DIR/models"
RUNNER_CALIB_DIR="$RUNNER_DATA_DIR/calib"
RUNNER_GOLD_DIR="$RUNNER_DATA_DIR/gold"
RUNNER_WORKSPACES_DIR="${NIGHTLY_RUNNER_WORKSPACES_DIR:-$HOME/.guess_nightly/workspaces}"
RUNNER_ROOT="$RUNNER_WORKSPACES_DIR/guess_runtime"
LAUNCHD_LOG_DIR="${NIGHTLY_LAUNCHD_LOG_DIR:-$HOME/.guess_nightly/launchd_logs}"
STDOUT_LOG="$LAUNCHD_LOG_DIR/launchd_nightly_v26.out.log"
STDERR_LOG="$LAUNCHD_LOG_DIR/launchd_nightly_v26.err.log"

mkdir -p "$ROOT_DIR/tmp" "$HOME/Library/LaunchAgents" "$RUNNER_DATA_REAL_DIR" "$RUNNER_WORKSPACES_DIR" "$LAUNCHD_LOG_DIR"
if [[ "$RUNNER_DATA_LINK_DIR" != "$RUNNER_DATA_REAL_DIR" ]]; then
  ln -sfn "$RUNNER_DATA_REAL_DIR" "$RUNNER_DATA_LINK_DIR"
fi
mkdir -p "$RUNNER_TMP_DIR" "$RUNNER_MODELS_DIR" "$RUNNER_CALIB_DIR" "$RUNNER_GOLD_DIR"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude ".git/" \
    --exclude "build/" \
    --exclude "tmp/" \
    "$ROOT_DIR/" "$RUNNER_ROOT/"
else
  rm -rf "$RUNNER_ROOT"
  mkdir -p "$RUNNER_ROOT"
  cp -R "$ROOT_DIR/." "$RUNNER_ROOT/"
  rm -rf "$RUNNER_ROOT/.git" "$RUNNER_ROOT/build" "$RUNNER_ROOT/tmp"
fi

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
    <string>scripts/nightly_train_v26.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${RUNNER_ROOT}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <!-- 默认参数区（已注释，切换为稳态参数） -->
    <!--
    <key>NIGHTLY_TOTAL_RUNS</key>
    <string>3</string>
    <key>SEM_MAX_PAIRS</key>
    <string>1600</string>
    <key>SEM_LEARNING_RATE</key>
    <string>3e-6</string>
    -->
    <key>NIGHTLY_WORK_DIR</key>
    <string>${RUNNER_TMP_DIR}</string>
    <key>NIGHTLY_SYNC_BACK_ROOT</key>
    <string>${SOURCE_ROOT}</string>
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
    <string>4</string>
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

    <!-- 稳态参数区（如需切换，取消注释并注释上方同名参数）
    <key>NIGHTLY_TOTAL_RUNS</key>
    <string>2</string>
    <key>SEM_MAX_PAIRS</key>
    <string>1200</string>
    <key>SEM_LEARNING_RATE</key>
    <string>2e-6</string>
    -->
    <key>SEM_GOLD_POOL_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_pool.csv</string>
    <key>SEM_GOLD_CALIB_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_calib.csv</string>
    <key>SEM_GOLD_EVAL_CSV</key>
    <string>${RUNNER_GOLD_DIR}/gold_v26_eval.csv</string>
    <key>SEM_BASE_MODEL</key>
    <string>models/bge-m3-finetuned-v27-semreal-anchor</string>
    <key>SEM_OUTPUT_MODEL</key>
    <string>${RUNNER_MODELS_DIR}/bge-m3-finetuned-local-candidate</string>
    <key>SEM_ANCHOR_MODEL</key>
    <string>${RUNNER_MODELS_DIR}/bge-m3-finetuned-local-candidate-anchor</string>
    <key>SEM_BASE_CALIB</key>
    <string>data/semantic_calibration_v27_semreal_anchor.json</string>
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
echo "source_root: $ROOT_DIR"
echo "runner_root: $RUNNER_ROOT"
echo "strict gate: mae>=0.005 acc>=0.0 strict_improve=1 no_degrade_all=0 auto_promote=1 delete_old=1"
echo "strategy: nightly 4 rounds, per-round seed drift, each round gate+promote, reject->delete candidate, anchor finetune=1, max_pairs=1600, lr=1.8e-6, anchor_lr=1.5e-6"
echo "check: launchctl list | grep ${AGENT_ID}"
echo "logs: $STDOUT_LOG / $STDERR_LOG"
