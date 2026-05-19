#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "[1/6] stop old embedding server on :8000"
lsof -ti tcp:8000 | xargs -r kill -9 || true

echo "[2/6] start embedding server"
mkdir -p tmp
LOG_FILE="tmp/preflight_embedding_server.log"
"$PYTHON_BIN" embedding_server.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "[3/6] health check"
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo "health: ok"
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
  echo "health: failed"
  echo "---- embedding server log ----"
  tail -n 120 "$LOG_FILE" || true
  exit 1
fi

echo "[4/6] regression check (expect 30/30)"
"$PYTHON_BIN" scripts/run_regression_pairs_v23.py | tail -n 8

echo "[5/6] puzzle structural/naturalness check"
"$PYTHON_BIN" scripts/validate_puzzle_data.py
"$PYTHON_BIN" tmp/puzzle_naturalness_diff_report.py >/dev/null
"$PYTHON_BIN" - <<'PY'
import os
import re
from pathlib import Path

text = Path('tmp/puzzle_naturalness_report.md').read_text(encoding='utf-8')

max_impacted = int(os.getenv('PREFLIGHT_MAX_NATURALNESS_IMPACTED', '10'))
max_filtered = int(os.getenv('PREFLIGHT_MAX_NATURALNESS_FILTERED', '15'))

impacted_match = re.search(r'受影响词条数:\s*(\d+)', text)
if impacted_match is None:
  raise SystemExit('naturalness check failed: missing 受影响词条数')
impacted = int(impacted_match.group(1))

filtered_total = 0
in_filter_section = False
for line in text.splitlines():
  if line.strip() == '## 过滤原因统计':
    in_filter_section = True
    continue
  if in_filter_section and line.startswith('## '):
    break
  if in_filter_section and line.startswith('- ') and ':' in line:
    name, value = line[2:].split(':', 1)
    value = value.strip()
    if name.strip() and value.isdigit():
      filtered_total += int(value)

if impacted > max_impacted:
  raise SystemExit(
    f'naturalness check failed: 受影响词条数={impacted} > {max_impacted}'
  )
if filtered_total > max_filtered:
  raise SystemExit(
    f'naturalness check failed: 过滤原因累计={filtered_total} > {max_filtered}'
  )

print(
  f'naturalness: ok (受影响词条数={impacted}, 过滤原因累计={filtered_total}, '
  f'阈值={max_impacted}/{max_filtered})'
)
PY

echo "[6/6] global hint quality gate"
"$PYTHON_BIN" scripts/validate_global_hint_rules_v1.py

echo "preflight done"
echo "next: flutter run -d macos"
