#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_ROOT="${COPILOT_MEM_SRC:-$ROOT_DIR}"
DST_ROOT="${COPILOT_MEM_DST:-/Volumes/新/work/flutter/guess}"
DRY_RUN="${1:-}"

FILES=(
  ".github/copilot-memory.md"
  ".github/copilot-runbook.md"
  ".github/copilot-instructions.md"
)

if [[ ! -d "$SRC_ROOT" ]]; then
  echo "[sync] source root missing: $SRC_ROOT" >&2
  exit 1
fi
if [[ ! -d "$DST_ROOT" ]]; then
  echo "[sync] target root missing: $DST_ROOT" >&2
  exit 1
fi

for file in "${FILES[@]}"; do
  if [[ ! -f "$SRC_ROOT/$file" ]]; then
    echo "[sync] missing source file: $SRC_ROOT/$file" >&2
    exit 1
  fi
done

ts="$(date +%Y%m%d_%H%M%S)"
backup_dir="$DST_ROOT/.github/.copilot-memory-backup/$ts"
mkdir -p "$backup_dir"

echo "[sync] source=$SRC_ROOT"
echo "[sync] target=$DST_ROOT"
echo "[sync] backup=$backup_dir"

for file in "${FILES[@]}"; do
  src="$SRC_ROOT/$file"
  dst="$DST_ROOT/$file"
  mkdir -p "$(dirname "$dst")"

  if [[ -f "$dst" ]]; then
    cp -f "$dst" "$backup_dir/$(basename "$file")"
    echo "[sync] backup $(basename "$file")"
  fi

  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo "[sync] dry-run copy $src -> $dst"
  else
    cp -f "$src" "$dst"
    src_hash="$(shasum -a 256 "$src" | awk '{print $1}')"
    dst_hash="$(shasum -a 256 "$dst" | awk '{print $1}')"
    if [[ "$src_hash" != "$dst_hash" ]]; then
      echo "[sync] hash mismatch for $file" >&2
      exit 1
    fi
    echo "[sync] copied $file"
  fi
done

if [[ "$DRY_RUN" == "--dry-run" ]]; then
  echo "[sync] dry-run complete"
else
  echo "[sync] complete"
fi
