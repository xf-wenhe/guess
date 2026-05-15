#!/usr/bin/env python3
import json
import re
import sys
from collections import Counter
from pathlib import Path


PUZZLES_PATH = Path("assets/puzzles.json")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def main() -> int:
    try:
        puzzles = json.loads(PUZZLES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"puzzle data: failed to read {PUZZLES_PATH}: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    seen_answers: set[str] = set()
    category_counts: Counter[str] = Counter()

    if not isinstance(puzzles, list):
        print("puzzle data: root must be a JSON array", file=sys.stderr)
        return 1

    for idx, item in enumerate(puzzles):
        if not isinstance(item, dict):
            errors.append(f"#{idx}: item must be an object")
            continue

        answer = str(item.get("answer", "")).strip()
        category = str(item.get("category", "其他")).strip() or "其他"
        hints = item.get("hints")
        category_counts[category] += 1

        if not 2 <= len(answer) <= 5:
            errors.append(f"#{idx} {answer!r}: answer length must be 2-5")
        if answer in seen_answers:
            warnings.append(f"#{idx} {answer!r}: duplicate answer")
        seen_answers.add(answer)

        if not isinstance(hints, list) or not hints:
            errors.append(f"#{idx} {answer!r}: hints must be a non-empty list")
            continue

        hint_texts = [str(h).strip() for h in hints if isinstance(h, str)]
        if len(hint_texts) < 7:
            warnings.append(f"#{idx} {answer!r}: fewer than 7 raw hints")
        if len(set(hint_texts)) != len(hint_texts):
            warnings.append(f"#{idx} {answer!r}: duplicate raw hints")

        for hint in hint_texts:
            if hint == answer:
                errors.append(f"#{idx} {answer!r}: hint exactly reveals answer")
            if hint and not CJK_RE.search(hint):
                warnings.append(f"#{idx} {answer!r}: hint has no CJK text: {hint!r}")

    if errors:
        print("puzzle data: failed")
        for error in errors[:50]:
            print(f"- {error}")
        if len(errors) > 50:
            print(f"- ... {len(errors) - 50} more")
        return 1

    print(
        "puzzle data: ok "
        f"(puzzles={len(puzzles)}, categories={len(category_counts)}, "
        f"warnings={len(warnings)})"
    )
    for warning in warnings[:10]:
        print(f"warning: {warning}")
    if len(warnings) > 10:
        print(f"warning: ... {len(warnings) - 10} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
