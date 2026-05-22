#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DEFAULT_NIGHTLY_ROOT="$ROOT_DIR/.nightly"
case "$ROOT_DIR" in
  */.nightly/workspaces/*)
    DEFAULT_NIGHTLY_ROOT="${ROOT_DIR%%/.nightly/workspaces/*}/.nightly"
    ;;
esac

NIGHTLY_ROOT="${NIGHTLY_ROOT:-$DEFAULT_NIGHTLY_ROOT}"
if [[ "$NIGHTLY_ROOT" != /* ]]; then
  NIGHTLY_ROOT="$ROOT_DIR/$NIGHTLY_ROOT"
fi

to_abs_path() {
  local p="$1"
  if [[ "$p" == /* ]]; then
    printf '%s' "$p"
  else
    printf '%s' "$ROOT_DIR/$p"
  fi
}

ensure_under_nightly() {
  local p="$1"
  case "$p" in
    "$NIGHTLY_ROOT"/*) return 0 ;;
    *)
      echo "[v28-nightly] path escapes NIGHTLY_ROOT: $p" >&2
      return 1
      ;;
  esac
}

assert_readable_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "[v28-nightly] missing file: $p" >&2
    return 1
  fi
  if [[ ! -r "$p" ]]; then
    echo "[v28-nightly] unreadable file: $p" >&2
    return 1
  fi
}

assert_writable_dir() {
  local d="$1"
  mkdir -p "$d"
  if [[ ! -w "$d" ]]; then
    echo "[v28-nightly] directory not writable: $d" >&2
    return 1
  fi
}

check_free_space() {
  local dir="$1"
  local min_gb="$2"
  local avail_kb
  avail_kb="$(df -Pk "$dir" | awk 'NR==2 {print $4}')"
  if [[ -z "$avail_kb" ]]; then
    echo "[v28-nightly] failed to read free space for: $dir" >&2
    return 1
  fi
  local min_kb
  min_kb="$((min_gb * 1024 * 1024))"
  if (( avail_kb < min_kb )); then
    echo "[v28-nightly] insufficient free space at $dir: available_kb=$avail_kb required_kb=$min_kb" >&2
    return 1
  fi
}

WORK_DIR="${NIGHTLY_WORK_DIR:-$NIGHTLY_ROOT/data/tmp}"
PROJECT_ROOT="${NIGHTLY_PROJECT_ROOT:-${NIGHTLY_ROOT%/.nightly}}"
SYNC_BACK_ROOT="${NIGHTLY_SYNC_BACK_ROOT:-$PROJECT_ROOT}"
WORK_DIR="$(to_abs_path "$WORK_DIR")"
PROJECT_ROOT="$(to_abs_path "$PROJECT_ROOT")"
SYNC_BACK_ROOT="$(to_abs_path "$SYNC_BACK_ROOT")"
mkdir -p "$WORK_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$WORK_DIR/nightly_train_v28_${STAMP}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[v28-nightly] start at $(date '+%F %T')"
echo "[v28-nightly] root=$ROOT_DIR"
echo "[v28-nightly] log=$LOG_FILE"

LOCK_DIR="$WORK_DIR/.nightly_train_v28.lock"
if [[ -d "$LOCK_DIR" ]]; then
  echo "[v28-nightly] another training is running, skip"
  exit 0
fi
mkdir -p "$LOCK_DIR"
cleanup() { rm -rf "$LOCK_DIR"; }
trap cleanup EXIT

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
PYTHON_BIN="$(to_abs_path "$PYTHON_BIN")"

DRY_RUN="${NIGHTLY_DRY_RUN:-0}"
AUTO_PROMOTE="${NIGHTLY_AUTO_PROMOTE:-1}"
DELETE_OLD_ON_PROMOTE="${NIGHTLY_DELETE_OLD_ON_PROMOTE:-1}"
ENFORCE_FREE_SPACE_CHECK="${NIGHTLY_ENFORCE_FREE_SPACE_CHECK:-1}"
MIN_FREE_GB="${NIGHTLY_MIN_FREE_GB:-24}"

BASE_MODEL="${SEM_BASE_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-v27-semreal-anchor}"
CANDIDATE_MODEL="${SEM_OUTPUT_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-v28c-candidate}"
CANDIDATE_CALIB="${SEM_OUTPUT_CALIB:-$NIGHTLY_ROOT/data/calib/semantic_calibration_v28c_candidate.json}"
PRODUCTION_MODEL="${SEM_PRODUCTION_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-v27-semreal-anchor}"
PRODUCTION_CALIB="${SEM_BASE_CALIB:-$NIGHTLY_ROOT/data/calib/semantic_calibration_v27_semreal_anchor.json}"

TRAIN_CSV="${SEM_TRAIN_CSV:-$ROOT_DIR/data/train_v28c_balanced.csv}"
GOLD_CALIB_CSV="${SEM_GOLD_CALIB_CSV:-$ROOT_DIR/data/gold_v28_calib.csv}"
GOLD_EVAL_CSV="${SEM_GOLD_EVAL_CSV:-$ROOT_DIR/data/gold_v28_eval.csv}"
REGRESSION_PAIRS="${SEM_REGRESSION_PAIRS:-$ROOT_DIR/data/regression_pairs_v23.json}"

EPOCHS="${SEM_EPOCHS:-3}"
BATCH_SIZE="${SEM_BATCH_SIZE:-8}"
LEARNING_RATE="${SEM_LR:-2e-5}"
MSE_WEIGHT="${SEM_MSE_WEIGHT:-0.5}"
CONTRASTIVE_WEIGHT="${SEM_CONTRASTIVE_WEIGHT:-0.5}"
CONTRASTIVE_MARGIN="${SEM_CONTRASTIVE_MARGIN:-0.5}"
HARD_NEG_BOOST="${SEM_HARD_NEG_BOOST:-3.0}"

TRAIN_CSV="$(to_abs_path "$TRAIN_CSV")"
GOLD_CALIB_CSV="$(to_abs_path "$GOLD_CALIB_CSV")"
GOLD_EVAL_CSV="$(to_abs_path "$GOLD_EVAL_CSV")"
REGRESSION_PAIRS="$(to_abs_path "$REGRESSION_PAIRS")"
BASE_MODEL="$(to_abs_path "$BASE_MODEL")"
CANDIDATE_MODEL="$(to_abs_path "$CANDIDATE_MODEL")"
CANDIDATE_CALIB="$(to_abs_path "$CANDIDATE_CALIB")"
PRODUCTION_MODEL="$(to_abs_path "$PRODUCTION_MODEL")"
PRODUCTION_CALIB="$(to_abs_path "$PRODUCTION_CALIB")"

echo "[v28-nightly][paths] PYTHON_BIN=$PYTHON_BIN"
echo "[v28-nightly][paths] NIGHTLY_ROOT=$NIGHTLY_ROOT"
echo "[v28-nightly][paths] PROJECT_ROOT=$PROJECT_ROOT"
echo "[v28-nightly][paths] WORK_DIR=$WORK_DIR"
echo "[v28-nightly][paths] SYNC_BACK_ROOT=$SYNC_BACK_ROOT"
echo "[v28-nightly][paths] TRAIN_CSV=$TRAIN_CSV"
echo "[v28-nightly][paths] GOLD_CALIB_CSV=$GOLD_CALIB_CSV"
echo "[v28-nightly][paths] GOLD_EVAL_CSV=$GOLD_EVAL_CSV"
echo "[v28-nightly][paths] REGRESSION_PAIRS=$REGRESSION_PAIRS"
echo "[v28-nightly][paths] BASE_MODEL=$BASE_MODEL"
echo "[v28-nightly][paths] CANDIDATE_MODEL=$CANDIDATE_MODEL"
echo "[v28-nightly][paths] CANDIDATE_CALIB=$CANDIDATE_CALIB"
echo "[v28-nightly][paths] PRODUCTION_MODEL=$PRODUCTION_MODEL"
echo "[v28-nightly][paths] PRODUCTION_CALIB=$PRODUCTION_CALIB"

ensure_under_nightly "$WORK_DIR"
ensure_under_nightly "$BASE_MODEL"
ensure_under_nightly "$CANDIDATE_MODEL"
ensure_under_nightly "$CANDIDATE_CALIB"
ensure_under_nightly "$PRODUCTION_MODEL"
ensure_under_nightly "$PRODUCTION_CALIB"

assert_writable_dir "$NIGHTLY_ROOT"
assert_writable_dir "$WORK_DIR"
assert_writable_dir "$(dirname "$CANDIDATE_MODEL")"
assert_writable_dir "$(dirname "$CANDIDATE_CALIB")"
assert_writable_dir "$(dirname "$PRODUCTION_MODEL")"
assert_writable_dir "$(dirname "$PRODUCTION_CALIB")"
assert_writable_dir "$(dirname "$SYNC_BACK_ROOT/models")"
assert_writable_dir "$(dirname "$SYNC_BACK_ROOT/data")"

if [[ "$SYNC_BACK_ROOT" != "$PROJECT_ROOT" && "$SYNC_BACK_ROOT" != "$NIGHTLY_ROOT/sync_back" ]]; then
  echo "[v28-nightly] unsupported NIGHTLY_SYNC_BACK_ROOT=$SYNC_BACK_ROOT (allowed: PROJECT_ROOT or $NIGHTLY_ROOT/sync_back)" >&2
  exit 1
fi

assert_readable_file "$TRAIN_CSV"
assert_readable_file "$GOLD_CALIB_CSV"
assert_readable_file "$GOLD_EVAL_CSV"
assert_readable_file "$REGRESSION_PAIRS"
assert_readable_file "$PRODUCTION_CALIB"
assert_readable_file "$BASE_MODEL/config_sentence_transformers.json"

if [[ "$ENFORCE_FREE_SPACE_CHECK" == "1" ]]; then
  check_free_space "$NIGHTLY_ROOT" "$MIN_FREE_GB"
fi

echo "[v28-nightly][df]"
df -h "$NIGHTLY_ROOT"

export TOKENIZERS_PARALLELISM=false
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0

step() {
  local name="$1"
  shift
  echo ""
  echo "[v28-nightly] === STEP: $name === at $(date '+%F %T')"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[v28-nightly] DRY RUN, would run: $*"
    return 0
  fi
  "$@"
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "[v28-nightly] FAILED (rc=$rc): $name"
    return $rc
  fi
  echo "[v28-nightly] DONE: $name"
  return 0
}

# ─── Phase 1: Data Build ───
step "build-antonym-pairs" "$PYTHON_BIN" scripts/build_v28_antonym_pairs.py
step "build-function-word-pairs" "$PYTHON_BIN" scripts/build_v28_function_word_pairs.py
step "build-category-graded" "$PYTHON_BIN" scripts/build_v28_category_graded.py
step "build-subset-pairs" "$PYTHON_BIN" scripts/build_v28_subset_pairs.py
step "build-synonym-expansion" "$PYTHON_BIN" scripts/build_v28_synonym_expansion.py
step "build-balanced-train" "$PYTHON_BIN" scripts/build_v28c_balanced_train.py
step "build-calib-supplement" "$PYTHON_BIN" scripts/build_v28_gold_calib_supplement.py

# ─── Phase 2: Train ───
step "train-v28c" env \
  SEM_TRAIN_CSV="$TRAIN_CSV" \
  SEM_BASE_MODEL="$BASE_MODEL" \
  SEM_OUTPUT_MODEL="$CANDIDATE_MODEL" \
  SEM_EPOCHS="$EPOCHS" \
  SEM_BATCH_SIZE="$BATCH_SIZE" \
  SEM_LR="$LEARNING_RATE" \
  SEM_MSE_WEIGHT="$MSE_WEIGHT" \
  SEM_CONTRASTIVE_WEIGHT="$CONTRASTIVE_WEIGHT" \
  SEM_CONTRASTIVE_MARGIN="$CONTRASTIVE_MARGIN" \
  SEM_HARD_NEG_BOOST="$HARD_NEG_BOOST" \
  "$PYTHON_BIN" scripts/train_v28c_mse_contrastive.py

# ─── Phase 3: Calibrate + Eval ───
step "calibrate-eval" env \
  SEM_MODEL_PATH="$CANDIDATE_MODEL" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$CANDIDATE_CALIB" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$WORK_DIR/v28c_eval_metrics_${STAMP}.json"

# ─── Phase 4: Regression Test ───
REGRESSION_LOG="$WORK_DIR/v28c_regression_${STAMP}.log"
step "regression-test" env \
  SEM_MODEL_PATH="$CANDIDATE_MODEL" \
  SEM_CALIB_PATH="$CANDIDATE_CALIB" \
  SEM_REGRESSION_PAIRS="$REGRESSION_PAIRS" \
  "$PYTHON_BIN" scripts/run_regression_pairs_v23.py | tee "$REGRESSION_LOG"

PASS_RATE=$(grep 'pass_rate=' "$REGRESSION_LOG" | tail -1 | sed 's/.*pass_rate=//' | tr -d '%')
echo "[v28-nightly] regression pass_rate=${PASS_RATE}%"

# ─── Phase 5: Promote Decision ───
echo ""
echo "[v28-nightly] === PROMOTE DECISION ==="
echo "[v28-nightly] candidate: $CANDIDATE_MODEL"
echo "[v28-nightly] regression: ${PASS_RATE}%"

if python3 -c "exit(0 if float('$PASS_RATE') >= 100.0 else 1)" 2>/dev/null; then
  echo "[v28-nightly] regression PASSED (100%)"

  METRICS_FILE="$WORK_DIR/v28c_eval_metrics_${STAMP}.json"
  if [[ -f "$METRICS_FILE" ]]; then
    CAL_MAE=$(python3 -c "import json;print(json.load(open('$METRICS_FILE'))['cal_mae'])")
    CAL_ACC=$(python3 -c "import json;print(json.load(open('$METRICS_FILE'))['cal_bucket_acc'])")
    echo "[v28-nightly] cal_mae=$CAL_MAE cal_bucket_acc=$CAL_ACC%"
  fi

  if [[ "$AUTO_PROMOTE" == "1" ]]; then
    echo "[v28-nightly] AUTO_PROMOTE=1, promoting candidate..."

    if [[ "$DELETE_OLD_ON_PROMOTE" == "1" ]]; then
      echo "[v28-nightly] backing up production model..."
      mv "$PRODUCTION_MODEL" "${PRODUCTION_MODEL}-backup-${STAMP}"
      mv "$PRODUCTION_CALIB" "${PRODUCTION_CALIB}-backup-${STAMP}"
    fi

    cp -r "$CANDIDATE_MODEL" "$PRODUCTION_MODEL"
    cp "$CANDIDATE_CALIB" "$PRODUCTION_CALIB"
    echo "[v28-nightly] PROMOTED to production!"

    if [[ -d "$PRODUCTION_MODEL" && -f "$PRODUCTION_CALIB" && -d "$SYNC_BACK_ROOT" ]]; then
      echo "[v28-nightly] rsync promoted artifacts to: $SYNC_BACK_ROOT"
      mkdir -p "$SYNC_BACK_ROOT/models/$(basename "$PRODUCTION_MODEL")" "$SYNC_BACK_ROOT/data"
      rsync -a --delete "$PRODUCTION_MODEL/" "$SYNC_BACK_ROOT/models/$(basename "$PRODUCTION_MODEL")/"
      rsync -a "$PRODUCTION_CALIB" "$SYNC_BACK_ROOT/data/$(basename "$PRODUCTION_CALIB")"
      echo "[v28-nightly] rsync done"
    else
      echo "[v28-nightly] skip sync-back: missing promoted artifacts or sync target"
    fi

    if [[ "$DELETE_OLD_ON_PROMOTE" == "1" ]]; then
      echo "[v28-nightly] cleaning up candidate..."
      rm -rf "$CANDIDATE_MODEL"
      echo "[v28-nightly] old backups retained with suffix -backup-${STAMP}"
    fi
  else
    echo "[v28-nightly] AUTO_PROMOTE=0, manual promotion required"
    echo "[v28-nightly] candidate ready at: $CANDIDATE_MODEL"
    echo "[v28-nightly] calib ready at: $CANDIDATE_CALIB"
  fi
else
  echo "[v28-nightly] regression FAILED (${PASS_RATE}%), NOT promoting"
  if [[ "$DELETE_OLD_ON_PROMOTE" == "1" ]]; then
    echo "[v28-nightly] cleaning up rejected candidate..."
    rm -rf "$CANDIDATE_MODEL"
    rm -f "$CANDIDATE_CALIB"
  fi
fi

echo ""
echo "[v28-nightly] done at $(date '+%F %T')"
