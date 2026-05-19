#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from hint_policy_common import (
    CJK_RE,
    has_answer_overlap,
    has_early_reveal_hit,
    is_all_four_char_hints,
    load_hint_policy,
)

TARGET_STRENGTHS = [30, 40, 50, 60, 70, 80, 90]
MAX_HINT_CHARS = 6

TEMPLATE_FRAGMENTS = {
    "关键线索",
    "场景线索",
    "阶段提示",
    "答案映射",
    "主要特征",
    "典型特征",
    "核心要素",
    "动漫作品",
    "热门番剧",
    "经典作品",
    "高能片段",
    "人气角色",
    "故事主线",
    "角色关系",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _hint_len(hint: str) -> int:
    return len("".join(ch for ch in hint if ch.strip()))


def _owner_key(item: dict[str, Any]) -> str:
    return f"{_norm(item.get('category'))}::{_norm(item.get('answer'))}"


def _find_target(puzzles: list[dict[str, Any]], answer: str) -> tuple[int, dict[str, Any]] | None:
    for idx, item in enumerate(puzzles):
        if _norm(item.get("answer")) == answer:
            return idx, item
    return None


def _hint_owners(
    puzzles: list[dict[str, Any]],
    target_index: int,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    global_owners: dict[str, list[str]] = {}
    category_owners: dict[str, list[str]] = {}
    for idx, item in enumerate(puzzles):
        if idx == target_index:
            continue
        category = _norm(item.get("category"))
        owner = _owner_key(item)
        for raw_hint in item.get("hints") or []:
            hint = _norm(raw_hint)
            if not hint:
                continue
            global_owners.setdefault(hint, []).append(owner)
            category_owners.setdefault(f"{category}::{hint}", []).append(owner)
    return global_owners, category_owners


def _check_review_payload(
    review_path: Path,
    answer: str,
    hints: list[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{"type": "review_json_invalid", "message": str(exc)}]

    if _norm(payload.get("answer")) != answer:
        issues.append({
            "type": "review_answer_mismatch",
            "message": f"expected answer={answer}",
        })

    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != 7:
        return issues + [{
            "type": "review_rows_invalid",
            "message": "review rows must contain exactly 7 items",
        }]

    seen_dimensions: set[str] = set()
    strengths: list[int] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append({"type": "review_row_invalid", "slot": idx + 1})
            continue
        hint = _norm(row.get("hint"))
        dimension = _norm(row.get("dimension"))
        basis = _norm(row.get("basis"))
        risk = _norm(row.get("early_lock_risk"))
        raw_strength = row.get("target_strength")

        if hint != hints[idx]:
            issues.append({
                "type": "review_hint_mismatch",
                "slot": idx + 1,
                "hint": hint,
                "expected": hints[idx],
            })
        if not dimension:
            issues.append({"type": "review_missing_dimension", "slot": idx + 1})
        elif dimension in seen_dimensions:
            issues.append({
                "type": "review_duplicate_dimension",
                "slot": idx + 1,
                "dimension": dimension,
            })
        seen_dimensions.add(dimension)

        try:
            strength = int(raw_strength)
            strengths.append(strength)
        except (TypeError, ValueError):
            issues.append({"type": "review_invalid_strength", "slot": idx + 1})

        if not basis:
            issues.append({"type": "review_missing_basis", "slot": idx + 1})
        if idx < 6 and risk not in {"低", "low", "medium", "中"}:
            issues.append({
                "type": "review_early_lock_risk_unclear",
                "slot": idx + 1,
                "risk": risk,
            })

    if strengths and strengths != TARGET_STRENGTHS:
        issues.append({
            "type": "review_strength_ladder_invalid",
            "strengths": strengths,
            "expected": TARGET_STRENGTHS,
        })
    return issues


def check_answer(
    puzzles: list[dict[str, Any]],
    target_index: int,
    policy,
    review_path: Path | None = None,
    require_review: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    item = puzzles[target_index]
    category = _norm(item.get("category"))
    answer = _norm(item.get("answer"))
    hints = [_norm(hint) for hint in (item.get("hints") or [])]
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if len(hints) != 7:
        issues.append({"type": "hint_count", "count": len(hints), "expected": 7})

    hints7 = hints[:7]
    if len(hints7) == 7:
        if is_all_four_char_hints(hints7):
            issues.append({"type": "forced_four_char_style", "hints": hints7})
        lengths = [_hint_len(hint) for hint in hints7]
        if len(set(lengths)) == 1:
            issues.append({"type": "uniform_hint_length", "length": lengths[0]})

    duplicate_counts = Counter(hints7)
    for hint, count in duplicate_counts.items():
        if hint and count > 1:
            issues.append({"type": "same_item_duplicate", "hint": hint, "count": count})

    global_owners, category_owners = _hint_owners(puzzles, target_index)
    for idx, hint in enumerate(hints7, start=1):
        if not hint:
            issues.append({"type": "empty_hint", "slot": idx})
            continue
        if not CJK_RE.search(hint):
            issues.append({"type": "no_cjk", "slot": idx, "hint": hint})
        hint_length = _hint_len(hint)
        if hint_length < 2 or hint_length > MAX_HINT_CHARS:
            issues.append({
                "type": "hint_length",
                "slot": idx,
                "hint": hint,
                "length": hint_length,
                "allowed": f"2-{MAX_HINT_CHARS}",
            })
        if has_answer_overlap(answer, hint):
            issues.append({
                "type": "answer_char_overlap",
                "slot": idx,
                "hint": hint,
                "common": sorted(set(answer) & set(hint)),
            })
        if hint in policy.forbidden_hint_terms:
            issues.append({"type": "forbidden_policy_term", "slot": idx, "hint": hint})
        matched_template = [term for term in TEMPLATE_FRAGMENTS if term in hint]
        if matched_template:
            issues.append({
                "type": "template_fragment",
                "slot": idx,
                "hint": hint,
                "matched": sorted(matched_template),
            })
        owners = global_owners.get(hint, [])
        if owners:
            issues.append({
                "type": "global_hint_reuse",
                "slot": idx,
                "hint": hint,
                "owners": owners[:20],
                "owner_count": len(owners),
            })
        scoped_owners = category_owners.get(f"{category}::{hint}", [])
        if scoped_owners:
            issues.append({
                "type": "category_hint_reuse",
                "slot": idx,
                "hint": hint,
                "owners": scoped_owners[:20],
                "owner_count": len(scoped_owners),
            })
        if has_early_reveal_hit(policy, category, answer, idx, hint):
            issues.append({"type": "early_reveal_hit", "slot": idx, "hint": hint})

    if require_review and review_path is None:
        issues.append({
            "type": "manual_review_missing",
            "message": "strict closure requires --review-json",
        })
    if review_path is not None:
        issues.extend(_check_review_payload(review_path, answer, hints7))
    else:
        warnings.append({
            "type": "manual_review_not_checked",
            "message": (
                "dimension split, target strengths, basis, and early-lock risk "
                "must be reviewed before declaring Xuanheng closure"
            ),
        })

    report = {
        "category": category,
        "answer": answer,
        "hints": hints7,
        "auto_gate_passed": not issues,
        "manual_review_checked": review_path is not None,
    }
    return report, issues, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict Xuanheng single-answer gate")
    parser.add_argument("answer", help="answer to check")
    parser.add_argument("--puzzles", default="assets/puzzles.json")
    parser.add_argument("--review-json", default="")
    parser.add_argument("--require-review", action="store_true")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    puzzles_path = Path(args.puzzles)
    puzzles = json.loads(puzzles_path.read_text(encoding="utf-8"))
    found = _find_target(puzzles, args.answer)
    if found is None:
        print(f"not_found answer={args.answer}")
        return 2
    target_index, _ = found

    review_path = Path(args.review_json) if args.review_json else None
    report, issues, warnings = check_answer(
        puzzles,
        target_index,
        load_hint_policy(),
        review_path=review_path,
        require_review=args.require_review,
    )
    payload = {**report, "issues": issues, "warnings": warnings}

    print(f"answer={report['answer']} category={report['category']}")
    print(f"hints={report['hints']}")
    if issues:
        print(f"FAIL issues={len(issues)}")
        for issue in issues:
            print(json.dumps(issue, ensure_ascii=False))
    else:
        print("PASS auto hard gates")
    if warnings:
        print(f"WARN warnings={len(warnings)}")
        for warning in warnings:
            print(json.dumps(warning, ensure_ascii=False))

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"json_out={out}")

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
