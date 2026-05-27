#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${NIGHTLY_SCRIPT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
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
      echo "[nightly] path escapes NIGHTLY_ROOT: $p" >&2
      return 1
      ;;
  esac
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

WORK_DIR="${NIGHTLY_WORK_DIR:-$NIGHTLY_ROOT/data/tmp}"
PROJECT_ROOT="${NIGHTLY_PROJECT_ROOT:-${NIGHTLY_ROOT%/.nightly}}"
SYNC_BACK_ROOT="${NIGHTLY_SYNC_BACK_ROOT:-$PROJECT_ROOT}"
WORK_DIR="$(to_abs_path "$WORK_DIR")"
PROJECT_ROOT="$(to_abs_path "$PROJECT_ROOT")"
SYNC_BACK_ROOT="$(to_abs_path "$SYNC_BACK_ROOT")"
mkdir -p "$WORK_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$WORK_DIR/nightly_train_v26_${STAMP}.log"
SUMMARY_FILE="$WORK_DIR/nightly_round_summary_${STAMP}.txt"
LOCK_DIR="$WORK_DIR/.nightly_train_v26.lock"

exec > >(tee -a "$LOG_FILE") 2>&1

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

DRY_RUN="${NIGHTLY_DRY_RUN:-0}"
ENFORCE_FREE_SPACE_CHECK="${NIGHTLY_ENFORCE_FREE_SPACE_CHECK:-1}"
MIN_FREE_GB="${NIGHTLY_MIN_FREE_GB:-24}"
PUZZLES_JSON="${SEM_PUZZLES_JSON:-$ROOT_DIR/assets/puzzles.json}"
MANUAL_OVERRIDES_JSON="${SEM_MANUAL_OVERRIDES:-$ROOT_DIR/data/manual_similarity_overrides.json}"
SCORED_CSV="${SEM_SCORED_CSV:-$ROOT_DIR/data/semantic_scoring_user_input_template.csv}"

BASE_MODEL="${SEM_BASE_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-v27-semreal-anchor}"
OUTPUT_MODEL="${SEM_OUTPUT_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-local-candidate}"
ANCHOR_MODEL="${SEM_ANCHOR_MODEL:-${OUTPUT_MODEL}-anchor}"
OUTPUT_CALIB="${SEM_OUTPUT_CALIB:-$NIGHTLY_ROOT/data/calib/semantic_calibration_local_candidate.json}"
BASE_CALIB="${SEM_BASE_CALIB:-$NIGHTLY_ROOT/data/calib/semantic_calibration_v27_semreal_anchor.json}"
ANCHOR_TRAIN_CSV="${SEM_ANCHOR_TRAIN_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_manual_anchor.csv}"
ENABLE_ANCHOR_FINETUNE="${NIGHTLY_ENABLE_ANCHOR_FINETUNE:-1}"
ANCHOR_BATCH_SIZE="${NIGHTLY_ANCHOR_BATCH_SIZE:-4}"
ANCHOR_EPOCHS="${NIGHTLY_ANCHOR_EPOCHS:-1}"
ANCHOR_WARMUP_STEPS="${NIGHTLY_ANCHOR_WARMUP_STEPS:-10}"
ANCHOR_LEARNING_RATE="${NIGHTLY_ANCHOR_LEARNING_RATE:-1.5e-6}"
AUTO_PROMOTE="${NIGHTLY_AUTO_PROMOTE:-1}"
DELETE_OLD_ON_PROMOTE="${NIGHTLY_DELETE_OLD_ON_PROMOTE:-1}"
DELETE_REJECTED_CANDIDATE="${NIGHTLY_DELETE_REJECTED_CANDIDATE:-1}"
MIN_MAE_IMPROVEMENT="${NIGHTLY_MIN_MAE_IMPROVEMENT:-0.0}"
MIN_ACC_IMPROVEMENT="${NIGHTLY_MIN_ACC_IMPROVEMENT:-0.0}"
REQUIRE_NO_DEGRADE_ALL="${NIGHTLY_REQUIRE_NO_DEGRADE_ALL:-0}"
REQUIRE_STRICT_IMPROVEMENT="${NIGHTLY_REQUIRE_STRICT_IMPROVEMENT:-1}"
TOTAL_RUNS="${NIGHTLY_TOTAL_RUNS:-1}"
BASE_SEED="${NIGHTLY_BASE_SEED:-20260303}"
CONTINUE_ON_ROUND_ERROR="${NIGHTLY_CONTINUE_ON_ROUND_ERROR:-1}"
MAX_PAIRS="${SEM_MAX_PAIRS:-1600}"
BATCH_SIZE="${SEM_BATCH_SIZE:-8}"
EPOCHS="${SEM_EPOCHS:-1}"
WARMUP_STEPS="${SEM_WARMUP_STEPS:-50}"
LEARNING_RATE="${SEM_LEARNING_RATE:-1.8e-6}"
UNSUP_PAIRS_JSONL="${SEM_UNSUP_PAIRS_JSONL:-$NIGHTLY_ROOT/data/gold/unsupervised_pairs_v26.jsonl}"
GOLD_CALIB_CSV="${SEM_GOLD_CALIB_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_calib.csv}"
GOLD_EVAL_CSV="${SEM_GOLD_EVAL_CSV:-$NIGHTLY_ROOT/data/gold/gold_v26_eval.csv}"
BUILD_TIMEOUT_SEC="${NIGHTLY_BUILD_TIMEOUT_SEC:-1200}"
PRETRAIN_TIMEOUT_SEC="${NIGHTLY_PRETRAIN_TIMEOUT_SEC:-10800}"
ANCHOR_TIMEOUT_SEC="${NIGHTLY_ANCHOR_TIMEOUT_SEC:-7200}"
EVAL_TIMEOUT_SEC="${NIGHTLY_EVAL_TIMEOUT_SEC:-1800}"
REGRESSION_TIMEOUT_SEC="${NIGHTLY_REGRESSION_TIMEOUT_SEC:-1200}"

BASE_MODEL="$(to_abs_path "$BASE_MODEL")"
OUTPUT_MODEL="$(to_abs_path "$OUTPUT_MODEL")"
ANCHOR_MODEL="$(to_abs_path "$ANCHOR_MODEL")"
OUTPUT_CALIB="$(to_abs_path "$OUTPUT_CALIB")"
BASE_CALIB="$(to_abs_path "$BASE_CALIB")"
ANCHOR_TRAIN_CSV="$(to_abs_path "$ANCHOR_TRAIN_CSV")"
UNSUP_PAIRS_JSONL="$(to_abs_path "$UNSUP_PAIRS_JSONL")"
GOLD_CALIB_CSV="$(to_abs_path "$GOLD_CALIB_CSV")"
GOLD_EVAL_CSV="$(to_abs_path "$GOLD_EVAL_CSV")"
PUZZLES_JSON="$(to_abs_path "$PUZZLES_JSON")"
MANUAL_OVERRIDES_JSON="$(to_abs_path "$MANUAL_OVERRIDES_JSON")"
SCORED_CSV="$(to_abs_path "$SCORED_CSV")"

echo "[nightly][paths] PYTHON_BIN=$PYTHON_BIN"
echo "[nightly][paths] NIGHTLY_ROOT=$NIGHTLY_ROOT"
echo "[nightly][paths] PROJECT_ROOT=$PROJECT_ROOT"
echo "[nightly][paths] WORK_DIR=$WORK_DIR"
echo "[nightly][paths] SYNC_BACK_ROOT=$SYNC_BACK_ROOT"
echo "[nightly][paths] BASE_MODEL=$BASE_MODEL"
echo "[nightly][paths] OUTPUT_MODEL=$OUTPUT_MODEL"
echo "[nightly][paths] ANCHOR_MODEL=$ANCHOR_MODEL"
echo "[nightly][paths] BASE_CALIB=$BASE_CALIB"
echo "[nightly][paths] OUTPUT_CALIB=$OUTPUT_CALIB"
echo "[nightly][paths] ANCHOR_TRAIN_CSV=$ANCHOR_TRAIN_CSV"
echo "[nightly][paths] UNSUP_PAIRS_JSONL=$UNSUP_PAIRS_JSONL"
echo "[nightly][paths] GOLD_CALIB_CSV=$GOLD_CALIB_CSV"
echo "[nightly][paths] GOLD_EVAL_CSV=$GOLD_EVAL_CSV"
echo "[nightly][paths] PUZZLES_JSON=$PUZZLES_JSON"
echo "[nightly][paths] MANUAL_OVERRIDES_JSON=$MANUAL_OVERRIDES_JSON"
echo "[nightly][paths] SCORED_CSV=$SCORED_CSV"

ensure_under_nightly "$WORK_DIR"
ensure_under_nightly "$BASE_MODEL"
ensure_under_nightly "$OUTPUT_MODEL"
ensure_under_nightly "$ANCHOR_MODEL"
ensure_under_nightly "$BASE_CALIB"
ensure_under_nightly "$OUTPUT_CALIB"
ensure_under_nightly "$ANCHOR_TRAIN_CSV"
ensure_under_nightly "$UNSUP_PAIRS_JSONL"
ensure_under_nightly "$GOLD_CALIB_CSV"
ensure_under_nightly "$GOLD_EVAL_CSV"
assert_readable_file "$PUZZLES_JSON"
assert_readable_file "$MANUAL_OVERRIDES_JSON"
assert_readable_file "$SCORED_CSV"

assert_writable_dir "$NIGHTLY_ROOT"
assert_writable_dir "$WORK_DIR"
assert_writable_dir "$(dirname "$OUTPUT_MODEL")"
assert_writable_dir "$(dirname "$ANCHOR_MODEL")"
assert_writable_dir "$(dirname "$OUTPUT_CALIB")"
assert_writable_dir "$(dirname "$SYNC_BACK_ROOT/models")"
assert_writable_dir "$(dirname "$SYNC_BACK_ROOT/data")"

if [[ "$SYNC_BACK_ROOT" != "$PROJECT_ROOT" && "$SYNC_BACK_ROOT" != "$NIGHTLY_ROOT/sync_back" ]]; then
  echo "[nightly] unsupported NIGHTLY_SYNC_BACK_ROOT=$SYNC_BACK_ROOT (allowed: PROJECT_ROOT or $NIGHTLY_ROOT/sync_back)" >&2
  exit 1
fi

assert_readable_file "$BASE_CALIB"
assert_readable_file "$BASE_MODEL/config_sentence_transformers.json"
assert_readable_file "$PROJECT_ROOT/models/$(basename "$BASE_MODEL")/config_sentence_transformers.json"
assert_readable_file "$PROJECT_ROOT/data/$(basename "$BASE_CALIB")"

if [[ "$DRY_RUN" != "1" ]]; then
  assert_readable_file "$ANCHOR_TRAIN_CSV"
fi

if [[ "$ENFORCE_FREE_SPACE_CHECK" == "1" ]]; then
  check_free_space "$NIGHTLY_ROOT" "$MIN_FREE_GB"
fi

echo "[nightly][df]"
df -h "$NIGHTLY_ROOT"

echo "[nightly] sync base artifacts from project to nightly root"
rsync -a --delete "$PROJECT_ROOT/models/$(basename "$BASE_MODEL")/" "$BASE_MODEL/"
rsync -a "$PROJECT_ROOT/data/$(basename "$BASE_CALIB")" "$BASE_CALIB"

CURRENT_ROUND=""
CURRENT_ROUND_OUTPUT_MODEL=""
CURRENT_ROUND_ANCHOR_MODEL=""
CURRENT_ROUND_OUTPUT_CALIB=""

cleanup_current_round_artifacts() {
  local reason="$1"
  if [[ "$DELETE_REJECTED_CANDIDATE" != "1" ]]; then
    return
  fi
  if [[ -n "$CURRENT_ROUND_OUTPUT_MODEL" && -d "$CURRENT_ROUND_OUTPUT_MODEL" && "$CURRENT_ROUND_OUTPUT_MODEL" != "$BASE_MODEL" ]]; then
    echo "[nightly] cleanup($reason): remove round${CURRENT_ROUND} candidate=$CURRENT_ROUND_OUTPUT_MODEL"
    rm -rf "$CURRENT_ROUND_OUTPUT_MODEL"
  fi
  if [[ -n "$CURRENT_ROUND_ANCHOR_MODEL" && -d "$CURRENT_ROUND_ANCHOR_MODEL" && "$CURRENT_ROUND_ANCHOR_MODEL" != "$BASE_MODEL" ]]; then
    echo "[nightly] cleanup($reason): remove round${CURRENT_ROUND} anchor=$CURRENT_ROUND_ANCHOR_MODEL"
    rm -rf "$CURRENT_ROUND_ANCHOR_MODEL"
  fi
  if [[ -n "$CURRENT_ROUND_OUTPUT_CALIB" && -f "$CURRENT_ROUND_OUTPUT_CALIB" && "$CURRENT_ROUND_OUTPUT_CALIB" != "$BASE_CALIB" ]]; then
    echo "[nightly] cleanup($reason): remove round${CURRENT_ROUND} calib=$CURRENT_ROUND_OUTPUT_CALIB"
    rm -f "$CURRENT_ROUND_OUTPUT_CALIB"
  fi
}

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
  echo "[nightly] invalid NIGHTLY_TOTAL_RUNS=$TOTAL_RUNS, fallback to 3"
  TOTAL_RUNS="3"
fi

echo "[nightly] guard: hint/answer char overlap"
"$PYTHON_BIN" scripts/guard_hint_answer_overlap_v1.py --input "$PUZZLES_JSON" --max-print 200

printf "round\tstage\tbase_mae\tcand_mae\tbase_acc\tcand_acc\treg_ok\taccepted\tpromoted\n" > "$SUMMARY_FILE"
PROMOTED_ANY=0

run_single_round() {
  local round="$1"
  local round_stamp="${STAMP}_r${round}"
  local round_seed="$((BASE_SEED + round - 1))"
  local round_output_model="$OUTPUT_MODEL"
  local round_anchor_model="$ANCHOR_MODEL"
  local round_output_calib="$OUTPUT_CALIB"
  local pretrain_metrics_json="$WORK_DIR/nightly_pretrain_metrics_${round_stamp}.json"
  local anchor_metrics_json="$WORK_DIR/nightly_anchor_metrics_${round_stamp}.json"
  local base_metrics_json="$WORK_DIR/nightly_base_metrics_${round_stamp}.json"
  local nightly_metrics_json="$WORK_DIR/nightly_candidate_metrics_${round_stamp}.json"
  local regression_out="$WORK_DIR/nightly_regression_${round_stamp}.txt"
  local candidate_model="$round_output_model"
  local candidate_stage="pretrain"

  CURRENT_ROUND="$round"
  CURRENT_ROUND_OUTPUT_MODEL="$round_output_model"
  CURRENT_ROUND_ANCHOR_MODEL="$round_anchor_model"
  CURRENT_ROUND_OUTPUT_CALIB="$round_output_calib"

  # Defensive cleanup in case previous interrupted runs left stale artifacts.
  cleanup_current_round_artifacts "round-start"

  echo "[nightly] ===== round ${round}/${TOTAL_RUNS} ====="
  echo "[nightly] round_seed=${round_seed}"

  run_cmd "SEM_SEED=$round_seed \
    SEM_PUZZLES_JSON=$PUZZLES_JSON \
    SEM_MANUAL_OVERRIDES=$MANUAL_OVERRIDES_JSON \
    SEM_SCORED_CSV=$SCORED_CSV \
    SEM_GOLD_MANUAL_ANCHOR_CSV=$ANCHOR_TRAIN_CSV \
    $PYTHON_BIN scripts/build_v26_gold_and_unsup.py" "$BUILD_TIMEOUT_SEC" || return $?

  run_cmd "TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
    SEM_SEED=$round_seed \
    SEM_UNSUP_PAIRS_JSONL=$UNSUP_PAIRS_JSONL \
    SEM_BASE_MODEL=$BASE_MODEL \
    SEM_OUTPUT_MODEL=$round_output_model \
    SEM_MAX_PAIRS=$MAX_PAIRS SEM_BATCH_SIZE=$BATCH_SIZE SEM_EPOCHS=$EPOCHS SEM_WARMUP_STEPS=$WARMUP_STEPS SEM_LEARNING_RATE=$LEARNING_RATE \
    $PYTHON_BIN scripts/pretrain_v26_unsupervised.py" "$PRETRAIN_TIMEOUT_SEC" || return $?

  run_cmd "SEM_MODEL_PATH=$round_output_model \
    SEM_CALIB_CSV=$GOLD_CALIB_CSV \
    SEM_EVAL_CSV=$GOLD_EVAL_CSV \
    SEM_CALIB_JSON=$round_output_calib \
    $PYTHON_BIN scripts/eval_v26_gold.py --json-out $pretrain_metrics_json" "$EVAL_TIMEOUT_SEC" || return $?

  if [[ "$ENABLE_ANCHOR_FINETUNE" == "1" ]]; then
    run_cmd "SEM_TRAIN_CSV=$ANCHOR_TRAIN_CSV \
      SEM_BASE_MODEL=$round_output_model \
      SEM_OUTPUT_MODEL=$round_anchor_model \
      SEM_BATCH_SIZE=$ANCHOR_BATCH_SIZE \
      SEM_EPOCHS=$ANCHOR_EPOCHS \
      SEM_WARMUP_STEPS=$ANCHOR_WARMUP_STEPS \
      SEM_LEARNING_RATE=$ANCHOR_LEARNING_RATE \
      $PYTHON_BIN scripts/finetune_v19_split.py" "$ANCHOR_TIMEOUT_SEC" || return $?

    candidate_model="$round_anchor_model"
    candidate_stage="anchor"
    run_cmd "SEM_MODEL_PATH=$candidate_model \
      SEM_CALIB_CSV=$GOLD_CALIB_CSV \
      SEM_EVAL_CSV=$GOLD_EVAL_CSV \
      SEM_CALIB_JSON=$round_output_calib \
      $PYTHON_BIN scripts/eval_v26_gold.py --json-out $anchor_metrics_json" "$EVAL_TIMEOUT_SEC" || return $?

    if [[ "$DRY_RUN" != "1" ]]; then
      selection_output="$(PRETRAIN_METRICS_JSON="$pretrain_metrics_json" ANCHOR_METRICS_JSON="$anchor_metrics_json" $PYTHON_BIN - <<'PY'
import json
import os
from pathlib import Path

pre = json.loads(Path(os.environ['PRETRAIN_METRICS_JSON']).read_text(encoding='utf-8'))
anc = json.loads(Path(os.environ['ANCHOR_METRICS_JSON']).read_text(encoding='utf-8'))
pre_mae = float(pre['cal_mae'])
pre_acc = float(pre['cal_bucket_acc'])
anc_mae = float(anc['cal_mae'])
anc_acc = float(anc['cal_bucket_acc'])
pre_raw_mae = float(pre['raw_mae'])
pre_raw_acc = float(pre['raw_bucket_acc'])
anc_raw_mae = float(anc['raw_mae'])
anc_raw_acc = float(anc['raw_bucket_acc'])
use_anchor = (
  anc_mae <= pre_mae
  and anc_acc >= pre_acc
  and anc_raw_mae <= pre_raw_mae
  and anc_raw_acc >= pre_raw_acc
  and (
    anc_mae < pre_mae
    or anc_acc > pre_acc
    or anc_raw_mae < pre_raw_mae
    or anc_raw_acc > pre_raw_acc
  )
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
    return 0
  fi

  echo "[nightly] evaluate base metrics"
  SEM_MODEL_PATH="$BASE_MODEL" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$BASE_CALIB" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$base_metrics_json" || return $?

  echo "[nightly] evaluate nightly metrics"
  SEM_MODEL_PATH="$candidate_model" \
  SEM_CALIB_CSV="$GOLD_CALIB_CSV" \
  SEM_EVAL_CSV="$GOLD_EVAL_CSV" \
  SEM_CALIB_JSON="$round_output_calib" \
  "$PYTHON_BIN" scripts/eval_v26_gold.py --json-out "$nightly_metrics_json" || return $?

  echo "[nightly] run nightly regression"
  run_cmd "SEM_MODEL_PATH=$candidate_model SEM_CALIB_PATH=$round_output_calib $PYTHON_BIN scripts/run_regression_pairs_v23.py > $regression_out" "$REGRESSION_TIMEOUT_SEC" || return $?
  tail -n 12 "$regression_out"

  python_gate_output="$(BASE_METRICS_JSON="$base_metrics_json" NIGHTLY_METRICS_JSON="$nightly_metrics_json" REGRESSION_OUT="$regression_out" MIN_MAE_IMPROVEMENT="$MIN_MAE_IMPROVEMENT" MIN_ACC_IMPROVEMENT="$MIN_ACC_IMPROVEMENT" REQUIRE_NO_DEGRADE_ALL="$REQUIRE_NO_DEGRADE_ALL" REQUIRE_STRICT_IMPROVEMENT="$REQUIRE_STRICT_IMPROVEMENT" $PYTHON_BIN - <<'PY'
import json
from pathlib import Path
import os
import re

base_json = Path(os.environ['BASE_METRICS_JSON'])
cand_json = Path(os.environ['NIGHTLY_METRICS_JSON'])
reg_txt = Path(os.environ['REGRESSION_OUT'])
min_mae = float(os.environ['MIN_MAE_IMPROVEMENT'])
min_acc = float(os.environ['MIN_ACC_IMPROVEMENT'])
require_no_degrade_all = os.environ.get('REQUIRE_NO_DEGRADE_ALL', '1') == '1'
require_strict_improvement = os.environ.get('REQUIRE_STRICT_IMPROVEMENT', '1') == '1'

base = json.loads(base_json.read_text(encoding='utf-8'))
cand = json.loads(cand_json.read_text(encoding='utf-8'))
reg = reg_txt.read_text(encoding='utf-8')

base_mae = float(base['cal_mae'])
base_acc = float(base['cal_bucket_acc'])
cand_mae = float(cand['cal_mae'])
cand_acc = float(cand['cal_bucket_acc'])
base_raw_mae = float(base['raw_mae'])
base_raw_acc = float(base['raw_bucket_acc'])
cand_raw_mae = float(cand['raw_mae'])
cand_raw_acc = float(cand['raw_bucket_acc'])

mae_ok = cand_mae <= (base_mae - min_mae)
acc_ok = cand_acc >= (base_acc + min_acc)
raw_mae_no_degrade = cand_raw_mae <= base_raw_mae
raw_acc_no_degrade = cand_raw_acc >= base_raw_acc
cal_mae_no_degrade = cand_mae <= base_mae
cal_acc_no_degrade = cand_acc >= base_acc
no_degrade_all = raw_mae_no_degrade and raw_acc_no_degrade and cal_mae_no_degrade and cal_acc_no_degrade
strict_improve = (cand_mae < base_mae or cand_acc > base_acc or cand_raw_mae < base_raw_mae or cand_raw_acc > base_raw_acc)

match = re.search(r'passed=(\d+)', reg)
passed = int(match.group(1)) if match else -1
reg_ok = passed == 30

accepted = mae_ok and acc_ok and reg_ok
if require_no_degrade_all:
  accepted = accepted and no_degrade_all
if require_strict_improvement:
  accepted = accepted and strict_improve

print(f'base_cal_mae={base_mae:.4f}')
print(f'base_cal_bucket_acc={base_acc:.2f}')
print(f'cand_cal_mae={cand_mae:.4f}')
print(f'cand_cal_bucket_acc={cand_acc:.2f}')
print(f'base_raw_mae={base_raw_mae:.4f}')
print(f'base_raw_bucket_acc={base_raw_acc:.2f}')
print(f'cand_raw_mae={cand_raw_mae:.4f}')
print(f'cand_raw_bucket_acc={cand_raw_acc:.2f}')
print(f'mae_ok={mae_ok}')
print(f'acc_ok={acc_ok}')
print(f'raw_mae_no_degrade={raw_mae_no_degrade}')
print(f'raw_acc_no_degrade={raw_acc_no_degrade}')
print(f'cal_mae_no_degrade={cal_mae_no_degrade}')
print(f'cal_acc_no_degrade={cal_acc_no_degrade}')
print(f'no_degrade_all={no_degrade_all}')
print(f'strict_improve={strict_improve}')
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
  promoted="False"

  if [[ "$accepted" == "True" || "$accepted" == "true" ]]; then
    echo "[nightly] round ${round}: candidate accepted"
    if [[ "$AUTO_PROMOTE" == "1" ]]; then
      echo "[nightly] round ${round}: auto promote enabled"
      if [[ "$candidate_model" != "$BASE_MODEL" ]]; then
        echo "[nightly] round ${round}: delete old default model and switch to latest"
        rm -rf "$BASE_MODEL"
        mv "$candidate_model" "$BASE_MODEL"
      fi

      if [[ "$round_output_calib" != "$BASE_CALIB" ]]; then
        rm -f "$BASE_CALIB"
        mv "$round_output_calib" "$BASE_CALIB"
      fi

      echo "[nightly] round ${round}: promoted default model=$BASE_MODEL"
      echo "[nightly] round ${round}: promoted default calib=$BASE_CALIB"
      promoted="True"
      PROMOTED_ANY=1
    else
      echo "[nightly] round ${round}: auto promote disabled, keep as candidate only"
    fi
  else
    echo "[nightly] round ${round}: candidate rejected, keep current default"
    if [[ "$DELETE_REJECTED_CANDIDATE" == "1" ]]; then
      if [[ "$candidate_model" != "$BASE_MODEL" && -d "$candidate_model" ]]; then
        echo "[nightly] delete rejected candidate model=$candidate_model"
        rm -rf "$candidate_model"
      fi
      if [[ "$round_output_model" != "$BASE_MODEL" && "$round_output_model" != "$candidate_model" && -d "$round_output_model" ]]; then
        echo "[nightly] delete intermediate candidate model=$round_output_model"
        rm -rf "$round_output_model"
      fi
      if [[ "$round_anchor_model" != "$BASE_MODEL" && "$round_anchor_model" != "$candidate_model" && -d "$round_anchor_model" ]]; then
        echo "[nightly] delete intermediate anchor model=$round_anchor_model"
        rm -rf "$round_anchor_model"
      fi
      if [[ "$round_output_calib" != "$BASE_CALIB" && -f "$round_output_calib" ]]; then
        echo "[nightly] delete rejected candidate calib=$round_output_calib"
        rm -f "$round_output_calib"
      fi
    fi
  fi

  if [[ "$AUTO_PROMOTE" == "1" && ( "$accepted" == "True" || "$accepted" == "true" ) ]]; then
    if [[ -d "$round_output_model" && "$round_output_model" != "$BASE_MODEL" ]]; then
      rm -rf "$round_output_model"
    fi
    if [[ -d "$round_anchor_model" && "$round_anchor_model" != "$BASE_MODEL" ]]; then
      rm -rf "$round_anchor_model"
    fi
  fi

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "$round" "$candidate_stage" "$base_mae_val" "$cand_mae_val" "$base_acc_val" "$cand_acc_val" "$reg_ok_val" "$accepted" "$promoted" >> "$SUMMARY_FILE"

  CURRENT_ROUND=""
  CURRENT_ROUND_OUTPUT_MODEL=""
  CURRENT_ROUND_ANCHOR_MODEL=""
  CURRENT_ROUND_OUTPUT_CALIB=""
}

for ((round=1; round<=TOTAL_RUNS; round++)); do
  if ! run_single_round "$round"; then
    echo "[nightly] round ${round} failed"
    cleanup_current_round_artifacts "round-error"
    printf "%s\tround_error\t-\t-\t-\t-\tFalse\tERROR\tFalse\n" "$round" >> "$SUMMARY_FILE"
    CURRENT_ROUND=""
    CURRENT_ROUND_OUTPUT_MODEL=""
    CURRENT_ROUND_ANCHOR_MODEL=""
    CURRENT_ROUND_OUTPUT_CALIB=""
    if [[ "$CONTINUE_ON_ROUND_ERROR" != "1" ]]; then
      echo "[nightly] stop on round error because NIGHTLY_CONTINUE_ON_ROUND_ERROR=$CONTINUE_ON_ROUND_ERROR"
      exit 1
    fi
    echo "[nightly] continue to next round"
  fi
done

echo "[nightly] done at $(date '+%F %T')"
echo "[nightly] final_base_model=$BASE_MODEL"
echo "[nightly] final_base_calib=$BASE_CALIB"
echo "[nightly] round_summary=$SUMMARY_FILE"
cat "$SUMMARY_FILE"

# 自动同步晋升产物到开发仓库（仅当本次运行发生晋升）
if [[ "$PROMOTED_ANY" == "1" && -d "$BASE_MODEL" && -f "$BASE_CALIB" ]]; then
  if [[ -n "$SYNC_BACK_ROOT" && -d "$SYNC_BACK_ROOT" ]]; then
    echo "[nightly] rsync晋升模型到目标目录: $SYNC_BACK_ROOT"
    mkdir -p "$SYNC_BACK_ROOT/models/$(basename "$BASE_MODEL")" "$SYNC_BACK_ROOT/data"
    rsync -a --delete "$BASE_MODEL/" "$SYNC_BACK_ROOT/models/$(basename "$BASE_MODEL")/"
    rsync -a "$BASE_CALIB" "$SYNC_BACK_ROOT/data/$(basename "$BASE_CALIB")"
    echo "[nightly] rsync完成"
  else
    echo "[nightly] skip sync-back: NIGHTLY_SYNC_BACK_ROOT is empty or missing"
  fi
else
  echo "[nightly] skip sync-back: no promotion in this run"
fi
