from __future__ import annotations

import json
import sys
from pathlib import Path

from hint_policy_common import (
    has_answer_overlap,
    has_early_reveal_hit,
    is_all_four_char_hints,
    load_hint_policy,
)


def main() -> None:
    policy = load_hint_policy()
    data = json.loads(Path("assets/puzzles.json").read_text(encoding="utf-8"))
    game_total = 0
    food_total = 0
    food_template_hits = 0
    food_style_hits = 0
    meta_hits = 0
    overlap_hits_all = 0
    overlap_hits_game = 0
    overlap_hits_non_game = 0
    non7_hint_items = 0
    duplicate_hint_items = 0
    generic_term_hits = 0
    forced_four_char_items = 0
    early_reveal_hits = 0
    early_reveal_items = 0
    early_reveal_violations = []
    global_hint_reuse_hits = 0
    same_category_hint_reuse_hits = 0
    global_hint_reuse_examples = []
    same_category_hint_reuse_examples = []
    total_items = 0
    global_hint_usage: dict[str, set[str]] = {}
    category_hint_usage: dict[str, set[str]] = {}

    for it in data:
        c = str(it.get("category", "")).strip()
        a = str(it.get("answer", "")).strip()
        raw_hints = [str(h).strip() for h in (it.get("hints") or [])]
        hs = raw_hints[:7]
        total_items += 1
        if len(raw_hints) != 7:
            non7_hint_items += 1
            continue
        if len(set(hs)) != len(hs):
            duplicate_hint_items += 1
        if policy.natural_language_guard.get(
            "forbid_forced_four_char_style"
        ) and is_all_four_char_hints(hs):
            forced_four_char_items += 1

        if c == "游戏":
            game_total += 1
        if c == "美食":
            food_total += 1
            expected_food_hints = policy.food_style_map.get(a)
            if expected_food_hints and hs == expected_food_hints[:7]:
                food_template_hits += 1
                food_style_hits += 1

        item_early_reveal = False
        for idx, h in enumerate(hs, start=1):
            if h in policy.meta_terms:
                meta_hits += 1
            if h in policy.generic_terms:
                generic_term_hits += 1
            if has_answer_overlap(a, h):
                overlap_hits_all += 1
                if c == "游戏":
                    overlap_hits_game += 1
                else:
                    overlap_hits_non_game += 1
            if has_early_reveal_hit(policy, c, a, idx, h):
                early_reveal_hits += 1
                item_early_reveal = True
                early_reveal_violations.append({
                    "category": c,
                    "answer": a,
                    "slot": idx,
                    "hint": h,
                })
            answer_key = f"{c}::{a}"
            global_hint_usage.setdefault(h, set()).add(answer_key)
            category_hint_usage.setdefault(f"{c}::{h}", set()).add(answer_key)
        if item_early_reveal:
            early_reveal_items += 1

    for hint, owners in sorted(global_hint_usage.items()):
        if len(owners) > 1:
            global_hint_reuse_hits += 1
            if len(global_hint_reuse_examples) < 200:
                global_hint_reuse_examples.append({
                    "hint": hint,
                    "answers": sorted(owners),
                })

    for scoped_hint, owners in sorted(category_hint_usage.items()):
        if len(owners) > 1:
            same_category_hint_reuse_hits += 1
            category, hint = scoped_hint.split("::", 1)
            if len(same_category_hint_reuse_examples) < 200:
                same_category_hint_reuse_examples.append({
                    "category": category,
                    "hint": hint,
                    "answers": sorted(owners),
                })

    report = {
        "game_total": game_total,
        "game_template_hits": None,
        "food_total": food_total,
        "food_template_hits": food_template_hits,
        "food_style_hits": food_style_hits,
        "meta_hits": meta_hits,
        "generic_term_hits": generic_term_hits,
        "char_overlap_hits_all": overlap_hits_all,
        "char_overlap_hits_game": overlap_hits_game,
        "char_overlap_hits_non_game": overlap_hits_non_game,
        "total_items": total_items,
        "universal_hint_count_target": int(
            policy.universal_constraints.get(
                "hint_count", policy.universal_rules.get("hint_count", 7)
            )
        ),
        "non7_hint_items": non7_hint_items,
        "duplicate_hint_items": duplicate_hint_items,
        "forced_four_char_items": forced_four_char_items,
        "global_hint_reuse_hits": global_hint_reuse_hits,
        "global_hint_reuse_examples": global_hint_reuse_examples,
        "same_category_hint_reuse_hits": same_category_hint_reuse_hits,
        "same_category_hint_reuse_examples": same_category_hint_reuse_examples,
        "early_reveal_guard_enabled": policy.early_reveal_enabled,
        "early_reveal_guard_hard_fail": policy.early_reveal_hard_fail,
        "early_reveal_guard_slots": policy.early_reveal_slots,
        "early_reveal_hits": early_reveal_hits,
        "early_reveal_items": early_reveal_items,
        "early_reveal_violations": early_reveal_violations[:200],
        "policy_file": "data/final_hint_policy_v1.json",
    }
    out_dir = Path("tmp/global_rules_v1")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "global_hint_rules_v1_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print(f"report={report_path}")

    hard_fail_hits = (
        meta_hits
        + generic_term_hits
        + overlap_hits_all
        + duplicate_hint_items
        + forced_four_char_items
        + global_hint_reuse_hits
        + same_category_hint_reuse_hits
    )

    if policy.early_reveal_enabled and policy.early_reveal_hard_fail and early_reveal_hits > 0:
        print(f"hard_fail: early_reveal_hits={early_reveal_hits}")
        sys.exit(1)
    if policy.validator_hard_fail and hard_fail_hits > 0:
        print(f"hard_fail: machine_check_hits={hard_fail_hits}")
        sys.exit(1)


if __name__ == "__main__":
    main()
