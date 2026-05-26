#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

STRICT_PROMOTION=1
if [[ "${1:-}" == "--allow-reject" ]]; then
  STRICT_PROMOTION=0
fi

NIGHTLY_ROOT="${NIGHTLY_ROOT:-$ROOT_DIR/.nightly}"
PROJECT_ROOT="${NIGHTLY_PROJECT_ROOT:-$ROOT_DIR}"
TMP_DIR="${NIGHTLY_WORK_DIR:-$NIGHTLY_ROOT/data/tmp}"

BASE_MODEL="${SEM_BASE_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-v27-semreal-anchor}"
BASE_CALIB="${SEM_BASE_CALIB:-$NIGHTLY_ROOT/data/calib/semantic_calibration_v27_semreal_anchor.json}"
OUTPUT_MODEL="${SEM_OUTPUT_MODEL:-$NIGHTLY_ROOT/data/models/bge-m3-finetuned-local-candidate}"
ANCHOR_MODEL="${SEM_ANCHOR_MODEL:-${OUTPUT_MODEL}-anchor}"

LOCAL_MODEL="${PROJECT_ROOT}/models/$(basename "$BASE_MODEL")"
LOCAL_CALIB="${PROJECT_ROOT}/data/$(basename "$BASE_CALIB")"

latest_summary="$(ls -t "$TMP_DIR"/nightly_round_summary_*.txt 2>/dev/null | head -n 1 || true)"
latest_log="$(ls -t "$TMP_DIR"/nightly_train_v26_*.log 2>/dev/null | head -n 1 || true)"

if [[ -z "$latest_summary" ]]; then
  echo "LATEST_SUMMARY=(missing)"
  echo "LATEST_LOG=${latest_log:-"(missing)"}"
  echo "PROMOTED=NO"
  echo "SYNC_MODEL=NO"
  echo "SYNC_CALIB=NO"
  echo "CANDIDATE_CLEANED=NO"
  echo "RESULT=FAIL"
  exit 1
fi

promoted_any="$(awk 'NR>1 { if ($9=="True" || $9=="true") p=1 } END { if (p) print "YES"; else print "NO" }' "$latest_summary")"

sync_model="SKIP"
sync_calib="SKIP"

if [[ "$promoted_any" == "YES" ]]; then
  if [[ -f "$BASE_MODEL/config_sentence_transformers.json" && -f "$LOCAL_MODEL/config_sentence_transformers.json" ]]; then
    src_model_sha="$(shasum -a 256 "$BASE_MODEL/config_sentence_transformers.json" | awk '{print $1}')"
    dst_model_sha="$(shasum -a 256 "$LOCAL_MODEL/config_sentence_transformers.json" | awk '{print $1}')"
    if [[ "$src_model_sha" == "$dst_model_sha" ]]; then
      sync_model="YES"
    else
      sync_model="NO"
    fi
  else
    sync_model="NO"
  fi

  if [[ -f "$BASE_CALIB" && -f "$LOCAL_CALIB" ]]; then
    src_calib_sha="$(shasum -a 256 "$BASE_CALIB" | awk '{print $1}')"
    dst_calib_sha="$(shasum -a 256 "$LOCAL_CALIB" | awk '{print $1}')"
    if [[ "$src_calib_sha" == "$dst_calib_sha" ]]; then
      sync_calib="YES"
    else
      sync_calib="NO"
    fi
  else
    sync_calib="NO"
  fi
fi

candidate_cleaned="YES"
if [[ -d "$OUTPUT_MODEL" || -d "$ANCHOR_MODEL" ]]; then
  candidate_cleaned="NO"
fi

result="PASS"
if [[ "$candidate_cleaned" != "YES" ]]; then
  result="FAIL"
fi
if [[ "$STRICT_PROMOTION" == "1" && "$promoted_any" != "YES" ]]; then
  result="FAIL"
fi
if [[ "$promoted_any" == "YES" && ( "$sync_model" != "YES" || "$sync_calib" != "YES" ) ]]; then
  result="FAIL"
fi

echo "LATEST_SUMMARY=$latest_summary"
echo "LATEST_LOG=${latest_log:-"(missing)"}"
echo "PROMOTED=$promoted_any"
echo "SYNC_MODEL=$sync_model"
echo "SYNC_CALIB=$sync_calib"
echo "CANDIDATE_CLEANED=$candidate_cleaned"
echo "RESULT=$result"

if [[ "$result" != "PASS" ]]; then
  exit 1
fi
