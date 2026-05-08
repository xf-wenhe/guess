#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[compat] scripts/preflight_v23.sh -> scripts/preflight_v26.sh"
exec bash scripts/preflight_v26.sh
