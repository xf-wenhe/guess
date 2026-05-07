from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def has_overlap(answer: str, hint: str) -> tuple[bool, str]:
    answer_chars = {ch for ch in answer if ch.strip()}
    hint_chars = {ch for ch in hint if ch.strip()}
    overlap = "".join(sorted(answer_chars & hint_chars))
    return bool(overlap), overlap


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail if any hint (first 7) shares characters with answer."
    )
    parser.add_argument("--input", default="assets/puzzles.json", help="Path to puzzles json")
    parser.add_argument("--category", default="", help="Optional category filter")
    parser.add_argument("--max-print", type=int, default=100, help="Max violation lines to print")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    total_items = 0
    scanned_items = 0
    non7_hint_items = 0
    violations: list[tuple[str, str, int, str, str]] = []

    for it in data:
        total_items += 1
        category = str(it.get("category", "")).strip()
        answer = str(it.get("answer", "")).strip()
        if args.category and category != args.category:
            continue
        scanned_items += 1

        hints = [str(h).strip() for h in (it.get("hints") or [])]
        if len(hints) < 7:
            non7_hint_items += 1
            continue

        for idx, hint in enumerate(hints[:7], start=1):
            hit, overlap = has_overlap(answer, hint)
            if hit:
                violations.append((category, answer, idx, hint, overlap))

    summary = {
        "input": args.input,
        "category_filter": args.category or None,
        "total_items": total_items,
        "scanned_items": scanned_items,
        "non7_hint_items": non7_hint_items,
        "violations": len(violations),
    }
    print(json.dumps(summary, ensure_ascii=False))

    if violations:
        print("overlap_violations:")
        for row in violations[: max(args.max_print, 0)]:
            category, answer, slot, hint, overlap = row
            print(f"{category}\t{answer}\tslot{slot}\t{hint}\tchars={overlap}")
        if len(violations) > args.max_print:
            print(f"... {len(violations) - args.max_print} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
