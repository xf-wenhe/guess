#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

WORK_DIR="${NIGHTLY_WORK_DIR:-$ROOT_DIR/tmp}"
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

DRY_RUN="${NIGHTLY_DRY_RUN:-0}"
AUTO_PROMOTE="${NIGHTLY_AUTO_PROMOTE:-1}"
DELETE_OLD_ON_PROMOTE="${NIGHTLY_DELETE_OLD_ON_PROMOTE:-1}"

BASE_MODEL="${SEM_BASE_MODEL:-models/bge-m3-finetuned-v27-semreal-anchor}"
CANDIDATE_MODEL="${SEM_OUTPUT_MODEL:-models/bge-m3-finetuned-v28c-candidate}"
CANDIDATE_CALIB="${SEM_OUTPUT_CALIB:-data/semantic_calibration_v28c_candidate.json}"
PRODUCTION_MODEL="models/bge-m3-finetuned-v27-semreal-anchor"
PRODUCTION_CALIB="data/semantic_calibration_v27_semreal_anchor.json"

TRAIN_CSV="${SEM_TRAIN_CSV:-data/train_v28c_balanced.csv}"
GOLD_CALIB_CSV="${SEM_GOLD_CALIB_CSV:-data/gold_v28_calib.csv}"
GOLD_EVAL_CSV="${SEM_GOLD_EVAL_CSV:-data/gold_v28_eval.csv}"
REGRESSION_PAIRS="${SEM_REGRESSION_PAIRS:-data/regression_pairs_v23.json}"

EPOCHS="${SEM_EPOCHS:-3}"
BATCH_SIZE="${SEM_BATCH_SIZE:-8}"
LEARNING_RATE="${SEM_LR:-2e-5}"
MSE_WEIGHT="${SEM_MSE_WEIGHT:-0.5}"
CONTRASTIVE_WEIGHT="${SEM_CONTRASTIVE_WEIGHT:-0.5}"
CONTRASTIVE_MARGIN="${SEM_CONTRASTIVE_MARGIN:-0.5}"
HARD_NEG_BOOST="${SEM_HARD_NEG_BOOST:-3.0}"

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
