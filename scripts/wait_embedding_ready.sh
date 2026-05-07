#!/usr/bin/env bash
set -euo pipefail

READY_URL="${EMBEDDING_READY_URL:-http://127.0.0.1:8000/ready}"
HEALTH_URL="${EMBEDDING_HEALTH_URL:-http://127.0.0.1:8000/health}"
MAX_ATTEMPTS="${EMBEDDING_READY_MAX_ATTEMPTS:-120}"
SLEEP_SECONDS="${EMBEDDING_READY_INTERVAL_SEC:-0.4}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

started_server=0

for ((i=1; i<=MAX_ATTEMPTS; i++)); do
  ready_resp="$(curl -sS "$READY_URL" 2>/dev/null || true)"
  if [[ -n "$ready_resp" ]]; then
    echo "$ready_resp"
  fi

  if echo "$ready_resp" | grep -Eq '"ready"[[:space:]]*:[[:space:]]*true'; then
    echo "embedding server is ready"
    exit 0
  fi

  if [[ "$ready_resp" == *"Not Found"* ]] || [[ "$ready_resp" == *'"detail":"Not Found"'* ]]; then
    health_resp="$(curl -fsS "$HEALTH_URL" 2>/dev/null || true)"
    if [[ -n "$health_resp" ]]; then
      echo "$health_resp"
      echo "ready endpoint unavailable, health ok"
      exit 0
    fi
  fi

  if [[ "$started_server" -eq 0 ]] && ! lsof -ti tcp:8000 >/dev/null 2>&1; then
    mkdir -p tmp
    nohup "$PYTHON_BIN" embedding_server.py > tmp/wait_embedding_server.log 2>&1 &
    started_server=1
    echo "embedding server started by wait task"
  fi

  sleep "$SLEEP_SECONDS"
done

echo "timeout waiting for /ready"
exit 1
