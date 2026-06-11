#!/usr/bin/env bash
set -euo pipefail

# Ensure Python stdout/stderr are unbuffered so progress bars (tqdm) and logs
# are visible even when launchd redirects output to files.
export PYTHONUNBUFFERED=1

ROOT_DIR="${NIGHTLY_SCRIPT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

NIGHTLY_ROOT="${NIGHTLY_ROOT:-$ROOT_DIR/.nightly}"
if [[ "$NIGHTLY_ROOT" != /* ]]; then
  NIGHTLY_ROOT="$ROOT_DIR/$NIGHTLY_ROOT"
fi

# HuggingFace cache on the external disk to avoid filling the system volume
export HF_HOME="${NIGHTLY_ROOT}/hf_cache"
mkdir -p "$HF_HOME"

to_abs_path() {
  local p="$1"
  if [[ "$p" == /* ]]; then
    printf '%s' "$p"
  else
    printf '%s' "$ROOT_DIR/$p"
  fi
}

assert_readable_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "[nightly] missing file: $p" >&2
    return 1
  fi
  if [[ ! -r "$p" ]]; then
    echo "[nightly] unreadable file: $p" >&2
    return 1
  fi
}

assert_writable_dir() {
  local d="$1"
  mkdir -p "$d"
  if [[ ! -w "$d" ]]; then
    echo "[nightly] directory not writable: $d" >&2
    return 1
  fi
}

check_free_space() {
  local dir="$1"
  local min_gb="$2"
  local avail_kb
  avail_kb="$(df -Pk "$dir" | awk 'NR==2 {print $4}')"
  if [[ -z "$avail_kb" ]]; then
    echo "[nightly] failed to read free space for: $dir" >&2
    return 1
  fi
  local min_kb
  min_kb="$((min_gb * 1024 * 1024))"
  if (( avail_kb < min_kb )); then
    echo "[nightly] insufficient free space at $dir: available_kb=$avail_kb required_kb=$min_kb" >&2
    return 1
  fi
}

# ---- path defaults (all under project root) ----

WORK_DIR="${NIGHTLY_WORK_DIR:-$NIGHTLY_ROOT/data/tmp}"
WORK_DIR="$(to_abs_path "$WORK_DIR")"
mkdir -p "$WORK_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$WORK_DIR/nightly_train_v26_${STAMP}.log"
SUMMARY_FILE="$WORK_DIR/nightly_round_summary_${STAMP}.txt"
LOCK_DIR="$WORK_DIR/.nightly_train_v26.lock"

mkdir -p "$WORK_DIR"

echo "[nightly] start at $(date '+%F %T')"
echo "[nightly] root=$ROOT_DIR"
echo "[nightly] log=$LOG_FILE"

if [[ -d "$LOCK_DIR" ]]; then
  echo "[nightly] another training is running, skip"
  exit 0
fi
mkdir -p "$LOCK_DIR"
cleanup() {
  rm -rf "$LOCK_DIR"
}
trap cleanup EXIT

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
PYTHON_BIN="$(to_abs_path "$PYTHON_BIN")"

# ---- tunable knobs ----

DRY_RUN="${NIGHTLY_DRY_RUN:-0}"
ENFORCE_FREE_SPACE_CHECK="${NIGHTLY_ENFORCE_FREE_SPACE_CHECK:-1}"
MIN_FREE_GB="${NIGHTLY_MIN_FREE_GB:-24}"
PUZZLES_JSON="${SEM_PUZZLES_JSON:-$ROOT_DIR/assets/puzzles.json}"
MANUAL_OVERRIDES_JSON="${SEM_MANUAL_OVERRIDES:-$ROOT_DIR/data/manual_similarity_overrides.json}"
SCORED_CSV="${SEM_SCORED_CSV:-$ROOT_DIR/data/semantic_scoring_user_input_template.csv}"

# Project model (the source of truth in models/)
PROJECT_MODEL_NAME="${NIGHTLY_PROJECT_MODEL_NAME:-bge-m3-finetuned-v27-semreal-anchor}"
PROJECT_MODEL_DIR="$ROOT_DIR/models/$PROJECT_MODEL_NAME"
PROJECT_CALIB_NAME="${NIGHTLY_PROJECT_CALIB_NAME:-semantic_calibration_v27_semreal_anchor.json}"
PROJECT_CALIB_PATH="$ROOT_DIR/data/$PROJECT_CALIB_NAME"

# Nightly work paths (inside .nightly/)
BASE_MODEL="${SEM_BASE_MODEL:-$NIGHTLY_ROOT/data/models/$PROJECT_MODEL_NAME}"
OUTPUT_MODEL="${SEM_OUTPUT_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-local-candidate}"
ANCHOR_MODEL="${SEM_ANCHOR_MODEL:-${OUTPUT_MODEL}-anchor}"
OUTPUT_CALIB="${SEM_OUTPUT_CALIB:-$NIGHTLY_ROOT/data/tmp/semantic_calibration_local_candidate.json}"
BASE_CALIB="${SEM_BASE_CALIB:-$NIGHTLY_ROOT/data/calib/$PROJECT_CALIB_NAME}"
ANCHOR_TRAIN_CSV="${SEM_ANCHOR_TRAIN_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_manual_anchor.csv}"
ENABLE_ANCHOR_FINETUNE="${NIGHTLY_ENABLE_ANCHOR_FINETUNE:-0}"
ANCHOR_BATCH_SIZE="${NIGHTLY_ANCHOR_BATCH_SIZE:-4}"
ANCHOR_EPOCHS="${NIGHTLY_ANCHOR_EPOCHS:-1}"
ANCHOR_WARMUP_STEPS="${NIGHTLY_ANCHOR_WARMUP_STEPS:-10}"
ANCHOR_LEARNING_RATE="${NIGHTLY_ANCHOR_LEARNING_RATE:-1.5e-6}"
AUTO_PROMOTE="${NIGHTLY_AUTO_PROMOTE:-1}"
DELETE_REJECTED_CANDIDATE="${NIGHTLY_DELETE_REJECTED_CANDIDATE:-1}"
DELETE_OLD_ON_PROMOTE="${NIGHTLY_DELETE_OLD_ON_PROMOTE:-1}"
MIN_MAE_IMPROVEMENT="${NIGHTLY_MIN_MAE_IMPROVEMENT:-0.3}"
MIN_ACC_IMPROVEMENT="${NIGHTLY_MIN_ACC_IMPROVEMENT:-2.0}"
REQUIRE_NO_DEGRADE_ALL="${NIGHTLY_REQUIRE_NO_DEGRADE_ALL:-1}"
REQUIRE_STRICT_IMPROVEMENT="${NIGHTLY_REQUIRE_STRICT_IMPROVEMENT:-1}"
TRAIN_DEVICE="${SEM_DEVICE:-${NIGHTLY_SEM_DEVICE:-auto}}"
ENABLE_SUPERVISED_FINETUNE="${NIGHTLY_ENABLE_SUPERVISED_FINETUNE:-1}"
ENABLE_UNSUP_PRETRAIN="${NIGHTLY_ENABLE_UNSUP_PRETRAIN:-0}"
SUPERVISED_TRAIN_SCRIPT="${NIGHTLY_SUPERVISED_TRAIN_SCRIPT:-scripts/train_v28c_mse_contrastive.py}"
BASE_TRAIN_CSV="${SEM_BASE_TRAIN_CSV:-$ROOT_DIR/data/train_v28c_balanced.csv}"
NIGHTLY_TRAIN_CSV="${SEM_NIGHTLY_TRAIN_CSV:-$NIGHTLY_ROOT/data/gold/train_v28c_nightly.csv}"
TRAIN_PROFILE="${NIGHTLY_TRAIN_PROFILE:-daily}"
if [[ "$TRAIN_PROFILE" == "full" ]]; then
  DEFAULT_SUP_BATCH_SIZE="8"
  DEFAULT_SUP_EPOCHS="2"
  DEFAULT_SUP_MAX_TRAIN_ROWS="0"
  DEFAULT_SUP_MAX_REPEAT="5"
  DEFAULT_SUP_LEARNING_RATE="2e-6"
  DEFAULT_TOTAL_RUNS="3"
elif [[ "$TRAIN_PROFILE" == "smoke" ]]; then
  DEFAULT_SUP_BATCH_SIZE="8"
  DEFAULT_SUP_EPOCHS="1"
  DEFAULT_SUP_MAX_TRAIN_ROWS="300"
  DEFAULT_SUP_MAX_REPEAT="3"
  DEFAULT_SUP_LEARNING_RATE="2e-6"
  DEFAULT_TOTAL_RUNS="1"
else
  DEFAULT_SUP_BATCH_SIZE="8"
  DEFAULT_SUP_EPOCHS="1"
  DEFAULT_SUP_MAX_TRAIN_ROWS="300"
  DEFAULT_SUP_MAX_REPEAT="3"
  DEFAULT_SUP_LEARNING_RATE="2e-6"
  DEFAULT_TOTAL_RUNS="3"
fi
SUP_BATCH_SIZE="${NIGHTLY_SUP_BATCH_SIZE:-$DEFAULT_SUP_BATCH_SIZE}"
SUP_EPOCHS="${NIGHTLY_SUP_EPOCHS:-$DEFAULT_SUP_EPOCHS}"
SUP_WARMUP_RATIO="${NIGHTLY_SUP_WARMUP_RATIO:-0.1}"
SUP_LEARNING_RATE="${NIGHTLY_SUP_LEARNING_RATE:-$DEFAULT_SUP_LEARNING_RATE}"
SUP_MAX_TRAIN_ROWS="${NIGHTLY_SUP_MAX_TRAIN_ROWS:-$DEFAULT_SUP_MAX_TRAIN_ROWS}"
SUP_HARD_NEG_BOOST="${NIGHTLY_SUP_HARD_NEG_BOOST:-2.0}"
SUP_MAX_REPEAT="${NIGHTLY_SUP_MAX_REPEAT:-$DEFAULT_SUP_MAX_REPEAT}"
SUP_ANGLE_MODE="${NIGHTLY_SUP_ANGLE_MODE:-cycle}"
SUP_LOSS_MODE="${NIGHTLY_SUP_LOSS_MODE:-mixed}"
SUP_CONTRASTIVE_MARGIN="${NIGHTLY_SUP_CONTRASTIVE_MARGIN:-0.5}"
SUP_CONTRASTIVE_SCOPE="${NIGHTLY_SUP_CONTRASTIVE_SCOPE:-selective}"
SUP_CONTRASTIVE_POS_THRESHOLD="${NIGHTLY_SUP_CONTRASTIVE_POS_THRESHOLD:-0.7}"
SUP_CONTRASTIVE_NEG_THRESHOLD="${NIGHTLY_SUP_CONTRASTIVE_NEG_THRESHOLD:-0.3}"
MIN_HARD_NEG_MAE_IMPROVEMENT="${NIGHTLY_MIN_HARD_NEG_MAE_IMPROVEMENT:-0.0}"
MIN_SYNONYM_RECALL_IMPROVEMENT="${NIGHTLY_MIN_SYNONYM_RECALL_IMPROVEMENT:-0.0}"
MIN_ANTONYM_MID_RECALL_IMPROVEMENT="${NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT:-0.0}"
TOTAL_RUNS="${NIGHTLY_TOTAL_RUNS:-$DEFAULT_TOTAL_RUNS}"
BASE_SEED="${NIGHTLY_BASE_SEED:-20260303}"
CONTINUE_ON_ROUND_ERROR="${NIGHTLY_CONTINUE_ON_ROUND_ERROR:-1}"
MAX_PAIRS="${SEM_MAX_PAIRS:-8000}"
BATCH_SIZE="${SEM_BATCH_SIZE:-16}"
EPOCHS="${SEM_EPOCHS:-1}"
WARMUP_STEPS="${SEM_WARMUP_STEPS:-50}"
LEARNING_RATE="${SEM_LEARNING_RATE:-1.8e-6}"
UNSUP_PAIRS_JSONL="${SEM_UNSUP_PAIRS_JSONL:-$NIGHTLY_ROOT/data/gold/unsupervised_pairs_v26.jsonl}"
GOLD_POOL_CSV="${SEM_GOLD_POOL_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_pool.csv}"
GOLD_CALIB_CSV="${SEM_GOLD_CALIB_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_calib.csv}"
GOLD_EVAL_CSV="${SEM_GOLD_EVAL_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_eval.csv}"
BUILD_TIMEOUT_SEC="${NIGHTLY_BUILD_TIMEOUT_SEC:-1200}"
PRETRAIN_TIMEOUT_SEC="${NIGHTLY_PRETRAIN_TIMEOUT_SEC:-10800}"
SUPERVISED_TIMEOUT_SEC="${NIGHTLY_SUPERVISED_TIMEOUT_SEC:-21600}"
ANCHOR_TIMEOUT_SEC="${NIGHTLY_ANCHOR_TIMEOUT_SEC:-7200}"
EVAL_TIMEOUT_SEC="${NIGHTLY_EVAL_TIMEOUT_SEC:-1800}"
REGRESSION_TIMEOUT_SEC="${NIGHTLY_REGRESSION_TIMEOUT_SEC:-1200}"

# Resolve to absolute
BASE_MODEL="$(to_abs_path "$BASE_MODEL")"
OUTPUT_MODEL="$(to_abs_path "$OUTPUT_MODEL")"
ANCHOR_MODEL="$(to_abs_path "$ANCHOR_MODEL")"
OUTPUT_CALIB="$(to_abs_path "$OUTPUT_CALIB")"
BASE_CALIB="$(to_abs_path "$BASE_CALIB")"
ANCHOR_TRAIN_CSV="$(to_abs_path "$ANCHOR_TRAIN_CSV")"
UNSUP_PAIRS_JSONL="$(to_abs_path "$UNSUP_PAIRS_JSONL")"
GOLD_POOL_CSV="$(to_abs_path "$GOLD_POOL_CSV")"
GOLD_CALIB_CSV="$(to_abs_path "$GOLD_CALIB_CSV")"
GOLD_EVAL_CSV="$(to_abs_path "$GOLD_EVAL_CSV")"
BASE_TRAIN_CSV="$(to_abs_path "$BASE_TRAIN_CSV")"
NIGHTLY_TRAIN_CSV="$(to_abs_path "$NIGHTLY_TRAIN_CSV")"
PUZZLES_JSON="$(to_abs_path "$PUZZLES_JSON")"
MANUAL_OVERRIDES_JSON="$(to_abs_path "$MANUAL_OVERRIDES_JSON")"
SCORED_CSV="$(to_abs_path "$SCORED_CSV")"

echo "[nightly][paths] PYTHON_BIN=$PYTHON_BIN"
echo "[nightly][paths] ROOT_DIR=$ROOT_DIR"
echo "[nightly][paths] NIGHTLY_ROOT=$NIGHTLY_ROOT"
echo "[nightly][paths] WORK_DIR=$WORK_DIR"
echo "[nightly][paths] PROJECT_MODEL_DIR=$PROJECT_MODEL_DIR"
echo "[nightly][paths] PROJECT_CALIB_PATH=$PROJECT_CALIB_PATH"
echo "[nightly][paths] BASE_MODEL=$BASE_MODEL"
echo "[nightly][paths] OUTPUT_MODEL=$OUTPUT_MODEL"
echo "[nightly][paths] ANCHOR_MODEL=$ANCHOR_MODEL"
echo "[nightly][paths] BASE_CALIB=$BASE_CALIB"
echo "[nightly][paths] OUTPUT_CALIB=$OUTPUT_CALIB"
echo "[nightly][paths] ANCHOR_TRAIN_CSV=$ANCHOR_TRAIN_CSV"
echo "[nightly][paths] UNSUP_PAIRS_JSONL=$UNSUP_PAIRS_JSONL"
echo "[nightly][paths] GOLD_CALIB_CSV=$GOLD_CALIB_CSV"
echo "[nightly][paths] GOLD_EVAL_CSV=$GOLD_EVAL_CSV"
echo "[nightly][paths] BASE_TRAIN_CSV=$BASE_TRAIN_CSV"
echo "[nightly][paths] NIGHTLY_TRAIN_CSV=$NIGHTLY_TRAIN_CSV"
echo "[nightly][config] TRAIN_DEVICE=$TRAIN_DEVICE train_profile=$TRAIN_PROFILE supervised=$ENABLE_SUPERVISED_FINETUNE unsup_pretrain=$ENABLE_UNSUP_PRETRAIN anchor=$ENABLE_ANCHOR_FINETUNE"
echo "[nightly][config] TOTAL_RUNS=$TOTAL_RUNS sup_rows=$SUP_MAX_TRAIN_ROWS sup_epochs=$SUP_EPOCHS sup_batch=$SUP_BATCH_SIZE sup_lr=$SUP_LEARNING_RATE sup_max_repeat=$SUP_MAX_REPEAT sup_angle_mode=$SUP_ANGLE_MODE sup_loss_mode=$SUP_LOSS_MODE sup_contrastive_scope=$SUP_CONTRASTIVE_SCOPE"
echo "[nightly][paths] PUZZLES_JSON=$PUZZLES_JSON"
echo "[nightly][paths] MANUAL_OVERRIDES_JSON=$MANUAL_OVERRIDES_JSON"
echo "[nightly][paths] SCORED_CSV=$SCORED_CSV"

device_prefix() {
  if [[ "$TRAIN_DEVICE" == "auto" || -z "$TRAIN_DEVICE" ]]; then
    printf ''
  elif [[ "$TRAIN_DEVICE" == "cpu" ]]; then
    printf 'SEM_DEVICE=cpu ACCELERATE_USE_CPU=true '
  else
    printf 'SEM_DEVICE=%q ' "$TRAIN_DEVICE"
  fi
}

# Validate inputs
assert_readable_file "$PUZZLES_JSON"
assert_readable_file "$MANUAL_OVERRIDES_JSON"
assert_readable_file "$SCORED_CSV"
assert_readable_file "$BASE_TRAIN_CSV"
assert_readable_file "$PROJECT_MODEL_DIR/config_sentence_transformers.json"
assert_readable_file "$PROJECT_CALIB_PATH"

assert_writable_dir "$NIGHTLY_ROOT"
assert_writable_dir "$WORK_DIR"
assert_writable_dir "$(dirname "$BASE_MODEL")"
assert_writable_dir "$(dirname "$OUTPUT_MODEL")"
assert_writable_dir "$(dirname "$ANCHOR_MODEL")"
assert_writable_dir "$(dirname "$BASE_CALIB")"
assert_writable_dir "$(dirname "$OUTPUT_CALIB")"

if [[ "$ENFORCE_FREE_SPACE_CHECK" == "1" ]]; then
  check_free_space "$NIGHTLY_ROOT" "$MIN_FREE_GB"
fi

echo "[nightly][df]"
df -h "$NIGHTLY_ROOT"

# sync project calib into nightly once
mkdir -p "$(dirname "$BASE_CALIB")"
cp "$PROJECT_CALIB_PATH" "$BASE_CALIB"

# ---- helpers ----

run_with_timeout() {
  local cmd="$1"
  local timeout_sec="$2"
  local start_ts now_ts pid

  kill_process_tree() {
    local root_pid="$1"
    local sig="$2"
    local child
    while IFS= read -r child; do
      [[ -n "$child" ]] || continue
      kill_process_tree "$child" "$sig"
    done < <(pgrep -P "$root_pid" 2>/dev/null || true)
    kill "-$sig" "$root_pid" 2>/dev/null || true
  }

  if [[ "$timeout_sec" -le 0 ]]; then
    eval "$cmd"
    return $?
  fi

  (
    eval "$cmd"
  ) &
  pid=$!
  start_ts="$(date +%s)"

  while kill -0 "$pid" 2>/dev/null; do
    now_ts="$(date +%s)"
    if (( now_ts - start_ts >= timeout_sec )); then
      echo "[nightly] timeout after ${timeout_sec}s, kill pid=$pid"
      kill_process_tree "$pid" TERM
      sleep 2
      if kill -0 "$pid" 2>/dev/null; then
        kill_process_tree "$pid" KILL
      fi
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 5
  done

  wait "$pid"
}

run_cmd() {
  local cmd="$1"
  local timeout_sec="${2:-0}"
  echo "[nightly] $cmd"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  run_with_timeout "$cmd" "$timeout_sec"
}

if ! [[ "$TOTAL_RUNS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[nightly] invalid NIGHTLY_TOTAL_RUNS=$TOTAL_RUNS, fallback to $DEFAULT_TOTAL_RUNS"
  TOTAL_RUNS="$DEFAULT_TOTAL_RUNS"
fi

echo "[nightly] guard: hint/answer char overlap"
"$PYTHON_BIN" scripts/guard_hint_answer_overlap_v1.py --input "$PUZZLES_JSON" --max-print 200

printf "round\tstage\tbase_mae\tcand_mae\tbase_acc\tcand_acc\treg_ok\taccepted\tpromoted\n" > "$SUMMARY_FILE"

# Per-round results for best-round selection
declare -a ROUND_RESULTS  # "round|stage|model|calib|mae|acc|raw_mae|raw_acc|accepted"
declare -a ROUND_DIAGNOSTICS  # "round|stage|base_metrics_json|candidate_metrics_json|regression_out"
declare -a ROUND_BUILD_STATS  # "round|build_stats_json"

# ---- run single round ----

run_single_round() {
  local round="$1"
  local round_stamp="${STAMP}_r${round}"
  local round_seed="$((BASE_SEED + round - 1))"

  # Per-round model paths (suffixed with _r<N>)
  local round_output_model="${OUTPUT_MODEL}_r${round}"
  local round_unsup_model="${OUTPUT_MODEL}-unsup_r${round}"
  local round_anchor_model="${ANCHOR_MODEL}_r${round}"
  local round_output_calib="${WORK_DIR}/semantic_calibration_local_candidate_${round_stamp}.json"
  local round_base_model="${BASE_MODEL}_r${round}"
  local round_base_calib="${WORK_DIR}/semantic_calibration_base_${round_stamp}.json"

  local pretrain_metrics_json="$WORK_DIR/nightly_pretrain_metrics_${round_stamp}.json"
  local anchor_metrics_json="$WORK_DIR/nightly_anchor_metrics_${round_stamp}.json"
  local base_metrics_json="$WORK_DIR/nightly_base_metrics_${round_stamp}.json"
  local nightly_metrics_json="$WORK_DIR/nightly_candidate_metrics_${round_stamp}.json"
  local regression_out="$WORK_DIR/nightly_regression_${round_stamp}.txt"
  local build_stats_json="$WORK_DIR/nightly_build_stats_${round_stamp}.json"

  local candidate_model="$round_base_model"
  local candidate_stage="base"

  echo "[nightly] ===== round ${round}/${TOTAL_RUNS} ====="
  echo "[nightly] round_seed=${round_seed}"

  # Copy base model from project models/ for this round
  echo "[nightly] copy round base model from project: $PROJECT_MODEL_DIR -> $round_base_model"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[nightly] (dry-run) skip base model copy"
  else
    rm -rf "$round_base_model"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --delete "$PROJECT_MODEL_DIR/" "$round_base_model/"
    else
      cp -R "$PROJECT_MODEL_DIR/" "$round_base_model/"
    fi
  fi

  # Build supervised nightly data, fixed calib/eval split, and optional unsup pairs.
  run_cmd "SEM_SEED=$round_seed \
    SEM_PUZZLES_JSON=$PUZZLES_JSON \
    SEM_MANUAL_OVERRIDES=$MANUAL_OVERRIDES_JSON \
    SEM_SCORED_CSV=$SCORED_CSV \
    SEM_BASE_TRAIN_CSV=$BASE_TRAIN_CSV \
    SEM_OUTPUT_TRAIN_CSV=$NIGHTLY_TRAIN_CSV \
    SEM_GOLD_POOL_CSV=$GOLD_POOL_CSV \
    SEM_GOLD_CALIB_CSV=$GOLD_CALIB_CSV \
    SEM_GOLD_EVAL_CSV=$GOLD_EVAL_CSV \
    SEM_UNSUP_PAIRS_JSONL=$UNSUP_PAIRS_JSONL \
    SEM_BUILD_STATS_JSON=$build_stats_json \
    $PYTHON_BIN scripts/build_nightly_semantic_sets.py" "$BUILD_TIMEOUT_SEC" || return $?
  ROUND_BUILD_STATS+=("${round}|${build_stats_json}")

  if [[ "$ENABLE_UNSUP_PRETRAIN" == "1" ]]; then
    run_cmd "TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
      $(device_prefix) \
      SEM_SEED=$round_seed \
      SEM_UNSUP_PAIRS_JSONL=$UNSUP_PAIRS_JSONL \
      SEM_BASE_MODEL=$candidate_model \
      SEM_OUTPUT_MODEL=$round_unsup_model \
      SEM_MAX_PAIRS=$MAX_PAIRS SEM_BATCH_SIZE=$BATCH_SIZE SEM_EPOCHS=$EPOCHS SEM_WARMUP_STEPS=$WARMUP_STEPS SEM_LEARNING_RATE=$LEARNING_RATE \
      $PYTHON_BIN scripts/pretrain_v26_unsupervised.py" "$PRETRAIN_TIMEOUT_SEC" || return $?
    candidate_model="$round_unsup_model"
    candidate_stage="unsup"

    run_cmd "$(device_prefix)SEM_MODEL_PATH=$candidate_model \
      SEM_CALIB_CSV=$GOLD_CALIB_CSV \
      SEM_EVAL_CSV=$GOLD_EVAL_CSV \
      SEM_CALIB_JSON=$round_output_calib \
      $PYTHON_BIN scripts/eval_v26_gold.py --json-out $pretrain_metrics_json" "$EVAL_TIMEOUT_SEC" || return $?
  fi

  if [[ "$ENABLE_SUPERVISED_FINETUNE" == "1" ]]; then
    supervised_cmd="TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
      $(device_prefix) \
      SEM_SEED=$round_seed \
      SEM_TRAIN_CSV=$NIGHTLY_TRAIN_CSV \
      SEM_BASE_MODEL=$candidate_model \
      SEM_OUTPUT_MODEL=$round_output_model \
      SEM_BATCH_SIZE=$SUP_BATCH_SIZE \
      SEM_EPOCHS=$SUP_EPOCHS \
      SEM_WARMUP_RATIO=$SUP_WARMUP_RATIO \
      SEM_LR=$SUP_LEARNING_RATE \
      SEM_MAX_TRAIN_ROWS=$SUP_MAX_TRAIN_ROWS \
      SEM_HARD_NEG_BOOST=$SUP_HARD_NEG_BOOST \
      SEM_MAX_REPEAT=$SUP_MAX_REPEAT \
      SEM_ANGLE_MODE=$SUP_ANGLE_MODE \
      SEM_LOSS_MODE=$SUP_LOSS_MODE \
      SEM_CONTRASTIVE_MARGIN=$SUP_CONTRASTIVE_MARGIN \
      SEM_CONTRASTIVE_SCOPE=$SUP_CONTRASTIVE_SCOPE \
      SEM_CONTRASTIVE_POS_THRESHOLD=$SUP_CONTRASTIVE_POS_THRESHOLD \
      SEM_CONTRASTIVE_NEG_THRESHOLD=$SUP_CONTRASTIVE_NEG_THRESHOLD \
      $PYTHON_BIN $SUPERVISED_TRAIN_SCRIPT"
    if ! run_cmd "$supervised_cmd" "$SUPERVISED_TIMEOUT_SEC"; then
      if [[ "$TRAIN_DEVICE" == "auto" || -z "$TRAIN_DEVICE" ]]; then
        echo "[nightly] supervised training failed on auto device, retry with SEM_DEVICE=cpu"
        rm -rf "$round_output_model"
        supervised_cpu_cmd="TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
          SEM_DEVICE=cpu \
          ACCELERATE_USE_CPU=true \
          SEM_SEED=$round_seed \
          SEM_TRAIN_CSV=$NIGHTLY_TRAIN_CSV \
          SEM_BASE_MODEL=$candidate_model \
          SEM_OUTPUT_MODEL=$round_output_model \
          SEM_BATCH_SIZE=$SUP_BATCH_SIZE \
          SEM_EPOCHS=$SUP_EPOCHS \
          SEM_WARMUP_RATIO=$SUP_WARMUP_RATIO \
          SEM_LR=$SUP_LEARNING_RATE \
          SEM_MAX_TRAIN_ROWS=$SUP_MAX_TRAIN_ROWS \
          SEM_HARD_NEG_BOOST=$SUP_HARD_NEG_BOOST \
          SEM_MAX_REPEAT=$SUP_MAX_REPEAT \
          SEM_ANGLE_MODE=$SUP_ANGLE_MODE \
          SEM_LOSS_MODE=$SUP_LOSS_MODE \
          SEM_CONTRASTIVE_MARGIN=$SUP_CONTRASTIVE_MARGIN \
          SEM_CONTRASTIVE_SCOPE=$SUP_CONTRASTIVE_SCOPE \
          SEM_CONTRASTIVE_POS_THRESHOLD=$SUP_CONTRASTIVE_POS_THRESHOLD \
          SEM_CONTRASTIVE_NEG_THRESHOLD=$SUP_CONTRASTIVE_NEG_THRESHOLD \
          $PYTHON_BIN $SUPERVISED_TRAIN_SCRIPT"
        run_cmd "$supervised_cpu_cmd" "$SUPERVISED_TIMEOUT_SEC" || return $?
      else
        return 1
      fi
    fi
    candidate_model="$round_output_model"
    if [[ "$candidate_stage" == "unsup" ]]; then
      candidate_stage="unsup+supervised"
    else
      candidate_stage="supervised"
    fi

    run_cmd "$(device_prefix)SEM_MODEL_PATH=$candidate_model \
      SEM_CALIB_CSV=$GOLD_CALIB_CSV \
      SEM_EVAL_CSV=$GOLD_EVAL_CSV \
      SEM_CALIB_JSON=$round_output_calib \
      $PYTHON_BIN scripts/eval_v26_gold.py --json-out $pretrain_metrics_json" "$EVAL_TIMEOUT_SEC" || return $?
  fi

  # Anchor finetune
  if [[ "$ENABLE_ANCHOR_FINETUNE" == "1" ]]; then
    run_cmd "SEM_TRAIN_CSV=$ANCHOR_TRAIN_CSV \
      $(device_prefix) \
      SEM_BASE_MODEL=$candidate_model \
      SEM_OUTPUT_MODEL=$round_anchor_model \
      SEM_BATCH_SIZE=$ANCHOR_BATCH_SIZE \
      SEM_EPOCHS=$ANCHOR_EPOCHS \
      SEM_WARMUP_STEPS=$ANCHOR_WARMUP_STEPS \
      SEM_LEARNING_RATE=$ANCHOR_LEARNING_RATE \
      $PYTHON_BIN scripts/finetune_v19_split.py" "$ANCHOR_TIMEOUT_SEC" || return $?

    candidate_model="$round_anchor_model"
    candidate_stage="anchor"
    run_cmd "$(device_prefix)SEM_MODEL_PATH=$candidate_model \
      SEM_CALIB_CSV=$GOLD_CALIB_CSV \
      SEM_EVAL_CSV=$GOLD_EVAL_CSV \
      SEM_CALIB_JSON=$round_output_calib \
      $PYTHON_BIN scripts/eval_v26_gold.py --json-out $anchor_metrics_json" "$EVAL_TIMEOUT_SEC" || return $?

    if [[ "$DRY_RUN" != "1" ]]; then
      selection_output="$(PRETRAIN_METRICS_JSON="$pretrain_metrics_json" ANCHOR_METRICS_JSON="$anchor_metrics_json" $PYTHON_BIN - <<'PY'
import json, os
from pathlib import Path
pre = json.loads(Path(os.environ['PRETRAIN_METRICS_JSON']).read_text(encoding='utf-8'))
anc = json.loads(Path(os.environ['ANCHOR_METRICS_JSON']).read_text(encoding='utf-8'))
pre_mae = float(pre['cal_mae']); pre_acc = float(pre['cal_bucket_acc'])
anc_mae = float(anc['cal_mae']); anc_acc = float(anc['cal_bucket_acc'])
pre_raw_mae = float(pre['raw_mae']); pre_raw_acc = float(pre['raw_bucket_acc'])
anc_raw_mae = float(anc['raw_mae']); anc_raw_acc = float(anc['raw_bucket_acc'])
use_anchor = (
  anc_mae <= pre_mae and anc_acc >= pre_acc
  and anc_raw_mae <= pre_raw_mae and anc_raw_acc >= pre_raw_acc
  and (anc_mae < pre_mae or anc_acc > pre_acc or anc_raw_mae < pre_raw_mae or anc_raw_acc > pre_raw_acc)
)
print(f'use_anchor={use_anchor}')
PY
)"
      echo "$selection_output"
      use_anchor="$(echo "$selection_output" | awk -F= '/^use_anchor=/{print $2}')"
      if [[ "$use_anchor" != "True" && "$use_anchor" != "true" ]]; then
        candidate_model="$round_output_model"
        candidate_stage="pretrain"
        if [[ -d "$round_anchor_model" && "$round_anchor_model" != "$round_output_model" ]]; then
          echo "[nightly] remove unselected anchor candidate=$round_anchor_model"
          rm -rf "$round_anchor_model"
        fi
      fi
    fi
  fi

  echo "[nightly] selected_candidate_stage=$candidate_stage"
  echo "[nightly] selected_candidate_model=$candidate_model"

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[nightly] (dry-run) skip metric gating and promotion for round $round"
    run_cmd "SEM_MODEL_PATH=$candidate_model SEM_CALIB_PATH=$round_output_calib $PYTHON_BIN scripts/run_regression_pairs_v23.py | tail -n 12" "$REGRESSION_TIMEOUT_SEC" || return $?
    printf "%s\t%s\t-\t-\t-\t-\t-\tDRY_RUN\t-\n" "$round" "$candidate_stage" >> "$SUMMARY_FILE"
    # Still record for best-round selection in dry-run
    ROUND_RESULTS+=("${round}|${candidate_stage}|${candidate_model}|${round_output_calib}|-|-|-|-|DRY_RUN")
    return 0
  fi

  # Gate: candidate vs base model for this round
  echo "[nightly] evaluate base metrics for round $round"
  env $(device_prefix) \
  SEM_MODEL_PATH="$round_base_model" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$round_base_calib" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$base_metrics_json" || return $?

  echo "[nightly] evaluate nightly metrics for round $round"
  env $(device_prefix) \
  SEM_MODEL_PATH="$candidate_model" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$round_output_calib" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$nightly_metrics_json" || return $?

  echo "[nightly] run nightly regression for round $round"
  run_cmd "SEM_MODEL_PATH=$candidate_model SEM_CALIB_PATH=$round_output_calib $PYTHON_BIN scripts/run_regression_pairs_v23.py > $regression_out" "$REGRESSION_TIMEOUT_SEC" || return $?
  tail -n 12 "$regression_out"

  python_gate_output="$(BASE_METRICS_JSON="$base_metrics_json" NIGHTLY_METRICS_JSON="$nightly_metrics_json" REGRESSION_OUT="$regression_out" MIN_MAE_IMPROVEMENT="$MIN_MAE_IMPROVEMENT" MIN_ACC_IMPROVEMENT="$MIN_ACC_IMPROVEMENT" MIN_HARD_NEG_MAE_IMPROVEMENT="$MIN_HARD_NEG_MAE_IMPROVEMENT" MIN_SYNONYM_RECALL_IMPROVEMENT="$MIN_SYNONYM_RECALL_IMPROVEMENT" MIN_ANTONYM_MID_RECALL_IMPROVEMENT="$MIN_ANTONYM_MID_RECALL_IMPROVEMENT" REQUIRE_NO_DEGRADE_ALL="$REQUIRE_NO_DEGRADE_ALL" REQUIRE_STRICT_IMPROVEMENT="$REQUIRE_STRICT_IMPROVEMENT" $PYTHON_BIN - <<'PY'
import json, os, re
from pathlib import Path
base = json.loads(Path(os.environ['BASE_METRICS_JSON']).read_text(encoding='utf-8'))
cand = json.loads(Path(os.environ['NIGHTLY_METRICS_JSON']).read_text(encoding='utf-8'))
reg = Path(os.environ['REGRESSION_OUT']).read_text(encoding='utf-8')
min_mae = float(os.environ['MIN_MAE_IMPROVEMENT'])
min_acc = float(os.environ['MIN_ACC_IMPROVEMENT'])
min_hard_mae = float(os.environ['MIN_HARD_NEG_MAE_IMPROVEMENT'])
min_syn_recall = float(os.environ['MIN_SYNONYM_RECALL_IMPROVEMENT'])
min_antonym_recall = float(os.environ['MIN_ANTONYM_MID_RECALL_IMPROVEMENT'])
require_no_degrade_all = os.environ.get('REQUIRE_NO_DEGRADE_ALL', '1') == '1'
require_strict_improvement = os.environ.get('REQUIRE_STRICT_IMPROVEMENT', '1') == '1'

b_mae = float(base['cal_mae']); b_acc = float(base['cal_bucket_acc'])
c_mae = float(cand['cal_mae']); c_acc = float(cand['cal_bucket_acc'])
b_raw_mae = float(base['raw_mae']); b_raw_acc = float(base['raw_bucket_acc'])
c_raw_mae = float(cand['raw_mae']); c_raw_acc = float(cand['raw_bucket_acc'])

mae_ok = c_mae <= (b_mae - min_mae)
acc_ok = c_acc >= (b_acc + min_acc)
raw_mae_no_degrade = c_raw_mae <= b_raw_mae
raw_acc_no_degrade = c_raw_acc >= b_raw_acc
cal_mae_no_degrade = c_mae <= b_mae
cal_acc_no_degrade = c_acc >= b_acc
no_degrade_all = raw_mae_no_degrade and raw_acc_no_degrade and cal_mae_no_degrade and cal_acc_no_degrade
strict_improve = (c_mae < b_mae or c_acc > b_acc or c_raw_mae < b_raw_mae or c_raw_acc > b_raw_acc)

base_groups = base.get('group_metrics') or {}
cand_groups = cand.get('group_metrics') or {}
base_hard = base_groups.get('hard_negative') or {}
cand_hard = cand_groups.get('hard_negative') or {}
base_syn = base_groups.get('synonym_alias') or {}
cand_syn = cand_groups.get('synonym_alias') or {}
base_ant = base_groups.get('antonym') or {}
cand_ant = cand_groups.get('antonym') or {}

b_hard_mae = float(base_hard.get('cal_mae', 0.0))
c_hard_mae = float(cand_hard.get('cal_mae', 0.0))
b_syn_recall = float(base_syn.get('recall_at_70', 0.0))
c_syn_recall = float(cand_syn.get('recall_at_70', 0.0))
b_ant_recall = float(base_ant.get('mid_score_recall_40_60', 0.0))
c_ant_recall = float(cand_ant.get('mid_score_recall_40_60', 0.0))
b_ant_strict_recall = float(base_ant.get('mid_score_recall_45_55', 0.0))
c_ant_strict_recall = float(cand_ant.get('mid_score_recall_45_55', 0.0))
b_ant_strict_recall = float(base_ant.get('mid_score_recall_45_55', 0.0))
c_ant_strict_recall = float(cand_ant.get('mid_score_recall_45_55', 0.0))
hard_negative_ok = True
if int(base_hard.get('count', 0)) > 0 and int(cand_hard.get('count', 0)) > 0:
  hard_negative_ok = c_hard_mae <= (b_hard_mae - min_hard_mae)
synonym_recall_ok = True
if int(base_syn.get('count', 0)) > 0 and int(cand_syn.get('count', 0)) > 0:
  synonym_recall_ok = c_syn_recall >= (b_syn_recall + min_syn_recall)
antonym_mid_recall_ok = True
antonym_strict_mid_recall_ok = True
if int(base_ant.get('count', 0)) > 0 and int(cand_ant.get('count', 0)) > 0:
  antonym_mid_recall_ok = c_ant_recall >= (b_ant_recall + min_antonym_recall)
  antonym_strict_mid_recall_ok = c_ant_strict_recall >= (b_ant_strict_recall + min_antonym_recall)

match = re.search(r'passed=(\d+)', reg)
passed = int(match.group(1)) if match else -1
total_match = re.search(r'total=(\d+)', reg)
total = int(total_match.group(1)) if total_match else -1
reg_ok = total > 0 and passed == total

accepted = mae_ok and acc_ok and reg_ok and hard_negative_ok and synonym_recall_ok and antonym_mid_recall_ok and antonym_strict_mid_recall_ok
if require_no_degrade_all:
  accepted = accepted and no_degrade_all
if require_strict_improvement:
  accepted = accepted and strict_improve

print(f'base_cal_mae={b_mae:.4f}')
print(f'base_cal_bucket_acc={b_acc:.2f}')
print(f'cand_cal_mae={c_mae:.4f}')
print(f'cand_cal_bucket_acc={c_acc:.2f}')
print(f'base_raw_mae={b_raw_mae:.4f}')
print(f'base_raw_bucket_acc={b_raw_acc:.2f}')
print(f'cand_raw_mae={c_raw_mae:.4f}')
print(f'cand_raw_bucket_acc={c_raw_acc:.2f}')
print(f'mae_ok={mae_ok}')
print(f'acc_ok={acc_ok}')
print(f'raw_mae_no_degrade={raw_mae_no_degrade}')
print(f'raw_acc_no_degrade={raw_acc_no_degrade}')
print(f'cal_mae_no_degrade={cal_mae_no_degrade}')
print(f'cal_acc_no_degrade={cal_acc_no_degrade}')
print(f'no_degrade_all={no_degrade_all}')
print(f'strict_improve={strict_improve}')
print(f'base_hard_negative_cal_mae={b_hard_mae:.4f}')
print(f'cand_hard_negative_cal_mae={c_hard_mae:.4f}')
print(f'hard_negative_ok={hard_negative_ok}')
print(f'base_synonym_recall_at70={b_syn_recall:.2f}')
print(f'cand_synonym_recall_at70={c_syn_recall:.2f}')
print(f'synonym_recall_ok={synonym_recall_ok}')
print(f'base_antonym_mid_recall_40_60={b_ant_recall:.2f}')
print(f'cand_antonym_mid_recall_40_60={c_ant_recall:.2f}')
print(f'antonym_mid_recall_ok={antonym_mid_recall_ok}')
print(f'base_antonym_mid_recall_45_55={b_ant_strict_recall:.2f}')
print(f'cand_antonym_mid_recall_45_55={c_ant_strict_recall:.2f}')
print(f'antonym_strict_mid_recall_ok={antonym_strict_mid_recall_ok}')
print(f'regression_passed={passed}')
print(f'regression_total={total}')
print(f'regression_ok={reg_ok}')
print(f'accepted={accepted}')
PY
)"

  echo "$python_gate_output"

  accepted="$(echo "$python_gate_output" | awk -F= '/^accepted=/{print $2}')"
  base_mae_val="$(echo "$python_gate_output" | awk -F= '/^base_cal_mae=/{print $2}')"
  base_acc_val="$(echo "$python_gate_output" | awk -F= '/^base_cal_bucket_acc=/{print $2}')"
  cand_mae_val="$(echo "$python_gate_output" | awk -F= '/^cand_cal_mae=/{print $2}')"
  cand_acc_val="$(echo "$python_gate_output" | awk -F= '/^cand_cal_bucket_acc=/{print $2}')"
  reg_ok_val="$(echo "$python_gate_output" | awk -F= '/^regression_ok=/{print $2}')"

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "$round" "$candidate_stage" "$base_mae_val" "$cand_mae_val" "$base_acc_val" "$cand_acc_val" "$reg_ok_val" "$accepted" "deferred" >> "$SUMMARY_FILE"

  # Record for best-round selection
  ROUND_RESULTS+=("${round}|${candidate_stage}|${candidate_model}|${round_output_calib}|${cand_mae_val}|${cand_acc_val}|${cand_mae_val}|${cand_acc_val}|${accepted}")
  ROUND_DIAGNOSTICS+=("${round}|${candidate_stage}|${base_metrics_json}|${nightly_metrics_json}|${regression_out}")

  # Clean up round base model (candidate kept for now)
  if [[ -d "$round_base_model" ]]; then
    rm -rf "$round_base_model"
  fi
}

# ---- run all rounds ----

for ((round=1; round<=TOTAL_RUNS; round++)); do
  if ! run_single_round "$round"; then
    echo "[nightly] round ${round} failed"
    printf "%s\tround_error\t-\t-\t-\t-\tFalse\tERROR\tFalse\n" "$round" >> "$SUMMARY_FILE"
    if [[ "$CONTINUE_ON_ROUND_ERROR" != "1" ]]; then
      echo "[nightly] stop on round error"
      exit 1
    fi
    echo "[nightly] continue to next round"
  fi
done

echo "[nightly] all rounds finished at $(date '+%F %T')"
echo "[nightly] round_summary=$SUMMARY_FILE"
echo "=== Round Summary ==="
cat "$SUMMARY_FILE"

# ---- best-round selection & promotion ----

REPORTS_DIR="$NIGHTLY_ROOT/reports"
mkdir -p "$REPORTS_DIR"
PROMOTION_REPORT="$REPORTS_DIR/nightly_promotion_${STAMP}.md"

append_metrics_diagnostics() {
  local title="$1"
  local base_metrics="$2"
  local cand_metrics="$3"
  local out="$4"
  if [[ ! -f "$base_metrics" || ! -f "$cand_metrics" ]]; then
    return 0
  fi
  DIAG_TITLE="$title" BASE_METRICS_JSON="$base_metrics" CAND_METRICS_JSON="$cand_metrics" METRICS_REPORT_OUT="$out" $PYTHON_BIN - <<'PY'
import json, os
from pathlib import Path

title = os.environ['DIAG_TITLE']
out = Path(os.environ['METRICS_REPORT_OUT'])
base = json.loads(Path(os.environ['BASE_METRICS_JSON']).read_text(encoding='utf-8'))
cand = json.loads(Path(os.environ['CAND_METRICS_JSON']).read_text(encoding='utf-8'))

groups = sorted(set((base.get('group_metrics') or {}) | (cand.get('group_metrics') or {})))
lines = [
    "",
    f"## {title}",
    "",
    "| group | base_mae | cand_mae | base_acc | cand_acc | extra |",
    "|-------|----------|----------|----------|----------|-------|",
]
for group in groups:
    b = (base.get('group_metrics') or {}).get(group, {})
    c = (cand.get('group_metrics') or {}).get(group, {})
    extra = ""
    if group == "synonym_alias":
        extra = f"recall@70 {b.get('recall_at_70', '-')} -> {c.get('recall_at_70', '-')}"
    elif group == "hard_negative":
        extra = f"low@30 {b.get('low_score_precision_at_30', '-')} -> {c.get('low_score_precision_at_30', '-')}"
    elif group == "antonym":
        extra = (
            f"mid@40-60 {b.get('mid_score_recall_40_60', '-')} -> {c.get('mid_score_recall_40_60', '-')}; "
            f"strict@45-55 {b.get('mid_score_recall_45_55', '-')} -> {c.get('mid_score_recall_45_55', '-')}"
        )
    lines.append(
        f"| {group} | {b.get('cal_mae', '-')} | {c.get('cal_mae', '-')} | "
        f"{b.get('cal_bucket_acc', '-')} | {c.get('cal_bucket_acc', '-')} | {extra} |"
    )

lines.extend([
    "",
    "### 候选最差样本",
    "",
    "| answer | input | target | candidate | error | group | tag |",
    "|--------|-------|--------|-----------|-------|-------|-----|",
])
for case in (cand.get('worst_cases') or [])[:10]:
    lines.append(
        f"| {case.get('answer', '')} | {case.get('user_input', '')} | {case.get('target', '')} | "
        f"{case.get('cal_pred', '')} | {case.get('abs_error', '')} | {case.get('group', '')} | {case.get('relation_tag', '')} |"
    )

base_conf = {
    (item.get('target_bucket'), item.get('cal_bucket')): item
    for item in (base.get('bucket_confusion') or [])
}
cand_conf = {
    (item.get('target_bucket'), item.get('cal_bucket')): item
    for item in (cand.get('bucket_confusion') or [])
}
conf_keys = sorted(
    set(base_conf) | set(cand_conf),
    key=lambda key: (
        -int((cand_conf.get(key) or base_conf.get(key) or {}).get('count') or 0),
        str(key[0]),
        str(key[1]),
    ),
)
if conf_keys:
    lines.extend([
        "",
        "### 校准桶错分 Top",
        "",
        "| target_bucket | predicted_bucket | base_count | cand_count | cand_avg_error | top_tags | top_groups | examples |",
        "|---------------|------------------|------------|------------|----------------|----------|------------|----------|",
    ])
    for key in conf_keys[:10]:
        b = base_conf.get(key) or {}
        c = cand_conf.get(key) or {}
        examples = ", ".join(c.get('examples') or b.get('examples') or [])
        top_tags = ", ".join(
            f"{item.get('tag')}:{item.get('count')}"
            for item in (c.get('top_tags') or b.get('top_tags') or [])
        )
        top_groups = ", ".join(
            f"{item.get('group')}:{item.get('count')}"
            for item in (c.get('top_groups') or b.get('top_groups') or [])
        )
        lines.append(
            f"| {key[0]} | {key[1]} | {b.get('count', 0)} | {c.get('count', 0)} | "
            f"{c.get('avg_abs_error', '-')} | {top_tags} | {top_groups} | {examples} |"
        )

with out.open('a', encoding='utf-8') as file:
    file.write("\n".join(lines) + "\n")
PY
}

append_build_stats() {
  local title="$1"
  local stats_json="$2"
  local out="$3"
  if [[ ! -f "$stats_json" ]]; then
    return 0
  fi
  BUILD_STATS_TITLE="$title" BUILD_STATS_JSON="$stats_json" BUILD_STATS_REPORT_OUT="$out" "$PYTHON_BIN" - <<'PY'
import json, os
from pathlib import Path

title = os.environ["BUILD_STATS_TITLE"]
stats = json.loads(Path(os.environ["BUILD_STATS_JSON"]).read_text(encoding="utf-8"))
out = Path(os.environ["BUILD_STATS_REPORT_OUT"])

lines = [
    "",
    f"## {title}",
    "",
    "| item | value |",
    "|------|-------|",
]
for key in ("train_rows", "gold_pool", "train_gold", "train_patch", "calib", "eval", "fixed_holdout", "unsup_pairs"):
    lines.append(f"| {key} | {stats.get(key, '-')} |")

lines.extend([
    "",
    "### Gold Buckets",
    "",
    "| bucket | count |",
    "|--------|-------|",
])
for bucket, count in (stats.get("gold_buckets") or {}).items():
    lines.append(f"| {bucket} | {count} |")

lines.extend([
    "",
    "### Top Train Tags",
    "",
    "| tag | count |",
    "|-----|-------|",
])
for tag, count in (stats.get("top_train_tags") or {}).items():
    lines.append(f"| {tag} | {count} |")

with out.open("a", encoding="utf-8") as file:
    file.write("\n".join(lines) + "\n")
PY
}

append_device_log_excerpt() {
  local out="$1"
  {
    echo ""
    echo "## 设备日志摘录"
    echo ""
    echo '```text'
    grep -Ei '(^|\s)(SEM_DEVICE|TRAIN_DEVICE|device=|using device|retry with SEM_DEVICE=cpu|ACCELERATE_USE_CPU|mps|cuda|cpu)(\s|$|=|:)' "$LOG_FILE" | tail -n 40 || true
    echo '```'
  } >> "$out"
}

# Find the best accepted round by lowest cal_mae
BEST_ROUND=""
BEST_STAGE=""
BEST_MODEL=""
BEST_CALIB=""
BEST_MAE="999"
BEST_ACC=""
BEST_RAW_MAE=""
BEST_RAW_ACC=""
ANY_ACCEPTED=0

for entry in ${ROUND_RESULTS[@]+"${ROUND_RESULTS[@]}"}; do
  IFS='|' read -r r stage model calib mae acc raw_mae raw_acc accepted <<< "$entry"
  if [[ "$accepted" == "True" || "$accepted" == "true" ]]; then
    ANY_ACCEPTED=1
    if (( $(echo "$mae < $BEST_MAE" | bc -l) )); then
      BEST_ROUND="$r"
      BEST_STAGE="$stage"
      BEST_MODEL="$model"
      BEST_CALIB="$calib"
      BEST_MAE="$mae"
      BEST_ACC="$acc"
      BEST_RAW_MAE="$raw_mae"
      BEST_RAW_ACC="$raw_acc"
    fi
  fi
done

# Build promotion report content
{
  echo "# Nightly Promotion Report - ${STAMP}"
  echo ""
  echo "**时间**: $(date '+%F %T') CST"
  echo "**模型**: $PROJECT_MODEL_NAME"
  echo "**总轮次**: $TOTAL_RUNS"
  echo ""
  echo "## 运行配置"
  echo ""
  echo "| item | value |"
  echo "|------|-------|"
  echo "| dry_run | $DRY_RUN |"
  echo "| train_profile | $TRAIN_PROFILE |"
  echo "| requested_device | $TRAIN_DEVICE |"
  echo "| supervised | $ENABLE_SUPERVISED_FINETUNE |"
  echo "| unsup_pretrain | $ENABLE_UNSUP_PRETRAIN |"
  echo "| anchor | $ENABLE_ANCHOR_FINETUNE |"
  echo "| sup_rows | $SUP_MAX_TRAIN_ROWS |"
  echo "| sup_epochs | $SUP_EPOCHS |"
  echo "| sup_batch | $SUP_BATCH_SIZE |"
  echo "| sup_lr | $SUP_LEARNING_RATE |"
  echo "| sup_angle_mode | $SUP_ANGLE_MODE |"
  echo "| sup_loss_mode | $SUP_LOSS_MODE |"
  echo "| sup_contrastive_scope | $SUP_CONTRASTIVE_SCOPE |"
  echo ""
  echo "## 晋升门控"
  echo ""
  echo "| gate | value |"
  echo "|------|-------|"
  echo "| min_cal_mae_improvement | $MIN_MAE_IMPROVEMENT |"
  echo "| min_cal_bucket_acc_improvement | $MIN_ACC_IMPROVEMENT |"
  echo "| require_no_degrade_all | $REQUIRE_NO_DEGRADE_ALL |"
  echo "| require_strict_improvement | $REQUIRE_STRICT_IMPROVEMENT |"
  echo "| min_hard_negative_mae_improvement | $MIN_HARD_NEG_MAE_IMPROVEMENT |"
  echo "| min_synonym_recall_improvement | $MIN_SYNONYM_RECALL_IMPROVEMENT |"
  echo "| min_antonym_mid_recall_improvement | $MIN_ANTONYM_MID_RECALL_IMPROVEMENT |"
  echo "| regression_gate | passed == total |"
  echo ""
  echo "## 各轮结果"
  echo ""
  echo "| 轮次 | stage | base_mae | cand_mae | base_acc | cand_acc | reg_ok | accepted |"
  echo "|------|-------|----------|----------|----------|----------|--------|----------|"
  for entry in ${ROUND_RESULTS[@]+"${ROUND_RESULTS[@]}"}; do
    IFS='|' read -r r stage model calib mae acc raw_mae raw_acc accepted <<< "$entry"
    printf "| %s | %s | %s | %s | %s | %s | %s | %s |\n" "$r" "$stage" "-" "$mae" "-" "$acc" "-" "$accepted"
  done
} > "$PROMOTION_REPORT"

for build_stats_json in "$WORK_DIR"/nightly_build_stats_"${STAMP}"_r*.json; do
  [[ -f "$build_stats_json" ]] || continue
  stats_base="$(basename "$build_stats_json")"
  stats_round="${stats_base##*_r}"
  stats_round="${stats_round%.json}"
  append_build_stats "训练数据分布 Round $stats_round" "$build_stats_json" "$PROMOTION_REPORT"
done

if [[ "$DRY_RUN" == "1" ]]; then
  echo "" >> "$PROMOTION_REPORT"
  echo "**结果**: DRY_RUN - 未实际晋升" >> "$PROMOTION_REPORT"
  echo "[nightly] dry-run complete, no promotion"
elif [[ "$ANY_ACCEPTED" == "0" ]]; then
  echo "" >> "$PROMOTION_REPORT"
  echo "**结果**: 无轮次通过门控，未晋升" >> "$PROMOTION_REPORT"
  echo "[nightly] no accepted rounds, no promotion"

  for entry in ${ROUND_DIAGNOSTICS[@]+"${ROUND_DIAGNOSTICS[@]}"}; do
    IFS='|' read -r r stage base_metrics cand_metrics regression_out <<< "$entry"
    append_metrics_diagnostics "拒绝诊断 Round $r ($stage)" "$base_metrics" "$cand_metrics" "$PROMOTION_REPORT"
  done

  # Delete all nightly artifacts (models, calibs, gold) except logs
  echo "[nightly] cleaning up nightly artifacts (no promotion)"
  for entry in ${ROUND_RESULTS[@]+"${ROUND_RESULTS[@]}"}; do
    IFS='|' read -r r stage model calib mae acc raw_mae raw_acc accepted <<< "$entry"
    if [[ -n "$model" && -d "$model" ]]; then
      rm -rf "$model"
    fi
    if [[ -n "$calib" && -f "$calib" ]]; then
      rm -f "$calib"
    fi
  done
  # Also clean up any stray anchor models
  for ((r=1; r<=TOTAL_RUNS; r++)); do
    rm -rf "${OUTPUT_MODEL}_r${r}" "${OUTPUT_MODEL}-unsup_r${r}" "${ANCHOR_MODEL}_r${r}" "${BASE_MODEL}_r${r}" || true
  done
else
  echo "" >> "$PROMOTION_REPORT"
  echo "**最佳轮次**: $BEST_ROUND ($BEST_STAGE)" >> "$PROMOTION_REPORT"
  echo "**最佳 MAE**: $BEST_MAE" >> "$PROMOTION_REPORT"
  echo "**最佳 Acc**: $BEST_ACC" >> "$PROMOTION_REPORT"

  # Evaluate best candidate against the project model
  echo "[nightly] evaluating best round $BEST_ROUND candidate against project model"
  PROJECT_EVAL_CALIB="$WORK_DIR/semantic_calibration_project_${STAMP}.json"
  PROJECT_BASE_METRICS="$WORK_DIR/nightly_project_base_metrics_${STAMP}.json"
  BEST_CAND_METRICS="$WORK_DIR/nightly_best_cand_metrics_${STAMP}.json"

  env $(device_prefix) \
  SEM_MODEL_PATH="$PROJECT_MODEL_DIR" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$PROJECT_EVAL_CALIB" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$PROJECT_BASE_METRICS" || true

  # Candidate metrics (already have them from round result, but re-evaluate for consistency)
  env $(device_prefix) \
  SEM_MODEL_PATH="$BEST_MODEL" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$BEST_CALIB" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$BEST_CAND_METRICS" || true

  # Run regression on best candidate
  echo "[nightly] run regression on best candidate"
  BEST_REGRESSION="$WORK_DIR/nightly_best_regression_${STAMP}.txt"
  SEM_MODEL_PATH="$BEST_MODEL" SEM_CALIB_PATH="$BEST_CALIB" \
    "$PYTHON_BIN" scripts/run_regression_pairs_v23.py > "$BEST_REGRESSION" 2>&1 || true
  tail -n 12 "$BEST_REGRESSION"

  # Gate against project model
  best_gate_output="$(BASE_METRICS_JSON="$PROJECT_BASE_METRICS" NIGHTLY_METRICS_JSON="$BEST_CAND_METRICS" REGRESSION_OUT="$BEST_REGRESSION" MIN_MAE_IMPROVEMENT="$MIN_MAE_IMPROVEMENT" MIN_ACC_IMPROVEMENT="$MIN_ACC_IMPROVEMENT" MIN_HARD_NEG_MAE_IMPROVEMENT="$MIN_HARD_NEG_MAE_IMPROVEMENT" MIN_SYNONYM_RECALL_IMPROVEMENT="$MIN_SYNONYM_RECALL_IMPROVEMENT" MIN_ANTONYM_MID_RECALL_IMPROVEMENT="$MIN_ANTONYM_MID_RECALL_IMPROVEMENT" REQUIRE_NO_DEGRADE_ALL="$REQUIRE_NO_DEGRADE_ALL" REQUIRE_STRICT_IMPROVEMENT="$REQUIRE_STRICT_IMPROVEMENT" $PYTHON_BIN - <<'PY'
import json, os, re
from pathlib import Path
base = json.loads(Path(os.environ['BASE_METRICS_JSON']).read_text(encoding='utf-8'))
cand = json.loads(Path(os.environ['NIGHTLY_METRICS_JSON']).read_text(encoding='utf-8'))
reg = Path(os.environ['REGRESSION_OUT']).read_text(encoding='utf-8')
min_mae = float(os.environ['MIN_MAE_IMPROVEMENT'])
min_acc = float(os.environ['MIN_ACC_IMPROVEMENT'])
min_hard_mae = float(os.environ['MIN_HARD_NEG_MAE_IMPROVEMENT'])
min_syn_recall = float(os.environ['MIN_SYNONYM_RECALL_IMPROVEMENT'])
min_antonym_recall = float(os.environ['MIN_ANTONYM_MID_RECALL_IMPROVEMENT'])
require_no_degrade_all = os.environ.get('REQUIRE_NO_DEGRADE_ALL', '1') == '1'
require_strict_improvement = os.environ.get('REQUIRE_STRICT_IMPROVEMENT', '1') == '1'

b_mae = float(base['cal_mae']); b_acc = float(base['cal_bucket_acc'])
c_mae = float(cand['cal_mae']); c_acc = float(cand['cal_bucket_acc'])
b_raw_mae = float(base['raw_mae']); b_raw_acc = float(base['raw_bucket_acc'])
c_raw_mae = float(cand['raw_mae']); c_raw_acc = float(cand['raw_bucket_acc'])

mae_ok = c_mae <= (b_mae - min_mae)
acc_ok = c_acc >= (b_acc + min_acc)
raw_mae_no_degrade = c_raw_mae <= b_raw_mae
raw_acc_no_degrade = c_raw_acc >= b_raw_acc
cal_mae_no_degrade = c_mae <= b_mae
cal_acc_no_degrade = c_acc >= b_acc
no_degrade_all = raw_mae_no_degrade and raw_acc_no_degrade and cal_mae_no_degrade and cal_acc_no_degrade
strict_improve = (c_mae < b_mae or c_acc > b_acc or c_raw_mae < b_raw_mae or c_raw_acc > b_raw_acc)

base_groups = base.get('group_metrics') or {}
cand_groups = cand.get('group_metrics') or {}
base_hard = base_groups.get('hard_negative') or {}
cand_hard = cand_groups.get('hard_negative') or {}
base_syn = base_groups.get('synonym_alias') or {}
cand_syn = cand_groups.get('synonym_alias') or {}
base_ant = base_groups.get('antonym') or {}
cand_ant = cand_groups.get('antonym') or {}

b_hard_mae = float(base_hard.get('cal_mae', 0.0))
c_hard_mae = float(cand_hard.get('cal_mae', 0.0))
b_syn_recall = float(base_syn.get('recall_at_70', 0.0))
c_syn_recall = float(cand_syn.get('recall_at_70', 0.0))
b_ant_recall = float(base_ant.get('mid_score_recall_40_60', 0.0))
c_ant_recall = float(cand_ant.get('mid_score_recall_40_60', 0.0))
hard_negative_ok = True
if int(base_hard.get('count', 0)) > 0 and int(cand_hard.get('count', 0)) > 0:
  hard_negative_ok = c_hard_mae <= (b_hard_mae - min_hard_mae)
synonym_recall_ok = True
if int(base_syn.get('count', 0)) > 0 and int(cand_syn.get('count', 0)) > 0:
  synonym_recall_ok = c_syn_recall >= (b_syn_recall + min_syn_recall)
antonym_mid_recall_ok = True
antonym_strict_mid_recall_ok = True
if int(base_ant.get('count', 0)) > 0 and int(cand_ant.get('count', 0)) > 0:
  antonym_mid_recall_ok = c_ant_recall >= (b_ant_recall + min_antonym_recall)
  antonym_strict_mid_recall_ok = c_ant_strict_recall >= (b_ant_strict_recall + min_antonym_recall)

match = re.search(r'passed=(\d+)', reg)
passed = int(match.group(1)) if match else -1
total_match = re.search(r'total=(\d+)', reg)
total = int(total_match.group(1)) if total_match else -1
reg_ok = total > 0 and passed == total

accepted = mae_ok and acc_ok and reg_ok and hard_negative_ok and synonym_recall_ok and antonym_mid_recall_ok and antonym_strict_mid_recall_ok
if require_no_degrade_all:
  accepted = accepted and no_degrade_all
if require_strict_improvement:
  accepted = accepted and strict_improve

print(f'project_cal_mae={b_mae:.4f}')
print(f'project_cal_bucket_acc={b_acc:.2f}')
print(f'best_cal_mae={c_mae:.4f}')
print(f'best_cal_bucket_acc={c_acc:.2f}')
print(f'project_raw_mae={b_raw_mae:.4f}')
print(f'project_raw_bucket_acc={b_raw_acc:.2f}')
print(f'best_raw_mae={c_raw_mae:.4f}')
print(f'best_raw_bucket_acc={c_raw_acc:.2f}')
print(f'project_hard_negative_cal_mae={b_hard_mae:.4f}')
print(f'best_hard_negative_cal_mae={c_hard_mae:.4f}')
print(f'hard_negative_ok={hard_negative_ok}')
print(f'project_synonym_recall_at70={b_syn_recall:.2f}')
print(f'best_synonym_recall_at70={c_syn_recall:.2f}')
print(f'synonym_recall_ok={synonym_recall_ok}')
print(f'project_antonym_mid_recall_40_60={b_ant_recall:.2f}')
print(f'best_antonym_mid_recall_40_60={c_ant_recall:.2f}')
print(f'antonym_mid_recall_ok={antonym_mid_recall_ok}')
print(f'project_antonym_mid_recall_45_55={b_ant_strict_recall:.2f}')
print(f'best_antonym_mid_recall_45_55={c_ant_strict_recall:.2f}')
print(f'antonym_strict_mid_recall_ok={antonym_strict_mid_recall_ok}')
print(f'regression_passed={passed}')
print(f'regression_total={total}')
print(f'regression_ok={reg_ok}')
print(f'accepted={accepted}')
print(f'mae_ok={mae_ok}')
print(f'acc_ok={acc_ok}')
PY
)"

  echo "$best_gate_output"
  best_accepted="$(echo "$best_gate_output" | awk -F= '/^accepted=/{print $2}')"
  proj_mae="$(echo "$best_gate_output" | awk -F= '/^project_cal_mae=/{print $2}')"
  proj_acc="$(echo "$best_gate_output" | awk -F= '/^project_cal_bucket_acc=/{print $2}')"
  best_mae_val="$(echo "$best_gate_output" | awk -F= '/^best_cal_mae=/{print $2}')"
  best_acc_val="$(echo "$best_gate_output" | awk -F= '/^best_cal_bucket_acc=/{print $2}')"

  {
    echo ""
    echo "## 项目模型对比"
    echo ""
    echo "| 指标 | 项目模型 (models/) | 最佳候选 (轮次 $BEST_ROUND) |"
    echo "|------|---------------------|------------------------------|"
    echo "| cal_mae | $proj_mae | $best_mae_val |"
    echo "| cal_acc | $proj_acc | $best_acc_val |"
    echo ""
  } >> "$PROMOTION_REPORT"

  append_metrics_diagnostics "分组指标" "$PROJECT_BASE_METRICS" "$BEST_CAND_METRICS" "$PROMOTION_REPORT"

  if [[ "$best_accepted" == "True" || "$best_accepted" == "true" ]]; then
    if [[ "$AUTO_PROMOTE" == "1" ]]; then
      echo "[nightly] PROMOTING: best round $BEST_ROUND -> models/$PROJECT_MODEL_NAME"
      echo "**结果**: 已晋升轮次 $BEST_ROUND" >> "$PROMOTION_REPORT"
      echo "" >> "$PROMOTION_REPORT"
      echo "**提升**: cal_mae $proj_mae → $best_mae_val, cal_acc $proj_acc → $best_acc_val" >> "$PROMOTION_REPORT"

      # Replace project model
      if [[ -d "$PROJECT_MODEL_DIR" ]]; then
        rm -rf "$PROJECT_MODEL_DIR"
      fi
      if command -v rsync >/dev/null 2>&1; then
        rsync -a "$BEST_MODEL/" "$PROJECT_MODEL_DIR/"
      else
        cp -R "$BEST_MODEL/" "$PROJECT_MODEL_DIR/"
      fi

      # Replace project calibration
      if [[ -f "$BEST_CALIB" ]]; then
        cp "$BEST_CALIB" "$PROJECT_CALIB_PATH"
      fi

      echo "[nightly] promoted: model=$PROJECT_MODEL_DIR calib=$PROJECT_CALIB_PATH"
    else
      echo "**结果**: AUTO_PROMOTE=off, 未晋升" >> "$PROMOTION_REPORT"
      echo "[nightly] auto promote disabled, best candidate kept at $BEST_MODEL"
    fi
  else
    echo "**结果**: 最佳轮次未通过项目模型门控，未晋升" >> "$PROMOTION_REPORT"
    echo "[nightly] best candidate rejected vs project model, no promotion"
  fi

  # Clean up all nightly artifacts except logs
  echo "[nightly] cleaning up nightly artifacts"
  for entry in ${ROUND_RESULTS[@]+"${ROUND_RESULTS[@]}"}; do
    IFS='|' read -r r stage model calib mae acc raw_mae raw_acc accepted <<< "$entry"
    if [[ -n "$model" && -d "$model" ]]; then
      rm -rf "$model"
    fi
    if [[ -n "$calib" && -f "$calib" ]]; then
      rm -f "$calib"
    fi
  done
  for ((r=1; r<=TOTAL_RUNS; r++)); do
    rm -rf "${OUTPUT_MODEL}_r${r}" "${OUTPUT_MODEL}-unsup_r${r}" "${ANCHOR_MODEL}_r${r}" "${BASE_MODEL}_r${r}" || true
  done
  rm -f "$PROJECT_EVAL_CALIB" "$PROJECT_BASE_METRICS" "$BEST_CAND_METRICS" "$BEST_REGRESSION"
fi

append_device_log_excerpt "$PROMOTION_REPORT"

echo "[nightly] promotion report: $PROMOTION_REPORT"
cat "$PROMOTION_REPORT"

echo "[nightly] done at $(date '+%F %T')"
