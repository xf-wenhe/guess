from __future__ import annotations

import json
import sys
from pathlib import Path

FINAL_POLICY = json.loads(Path("data/final_hint_policy_v1.json").read_text(encoding="utf-8"))
UNIVERSAL_CONSTRAINTS = FINAL_POLICY.get("universal_constraints", {})
META_TERMS = set(UNIVERSAL_CONSTRAINTS.get("forbidden_meta_terms", []))
NATURAL_LANGUAGE_GUARD = UNIVERSAL_CONSTRAINTS.get("natural_language_guard", {})
GENERIC_TERMS = set(NATURAL_LANGUAGE_GUARD.get("forbidden_generic_terms", []))
VALIDATOR_MACHINE_CHECKS = UNIVERSAL_CONSTRAINTS.get("validator_machine_checks", {})
VALIDATOR_HARD_FAIL = bool(VALIDATOR_MACHINE_CHECKS.get("hard_fail_on_any_violation", False))
EARLY_REVEAL_GUARD = UNIVERSAL_CONSTRAINTS.get("early_reveal_guard", {})
EARLY_REVEAL_ENABLED = bool(EARLY_REVEAL_GUARD.get("enabled", False))
EARLY_REVEAL_HARD_FAIL = bool(EARLY_REVEAL_GUARD.get("hard_fail_on_hit", False))
EARLY_REVEAL_SLOTS = [int(x) for x in (EARLY_REVEAL_GUARD.get("slots") or [1, 2, 3])]
EARLY_REVEAL_CATEGORY_TERMS = {
    str(k): [str(v).strip() for v in vals]
    for k, vals in (EARLY_REVEAL_GUARD.get("category_block_terms") or {}).items()
}
EARLY_REVEAL_ANSWER_TERMS = {
    str(k): [str(v).strip() for v in vals]
    for k, vals in (EARLY_REVEAL_GUARD.get("answer_block_terms") or {}).items()
}
FOOD_STYLE_MAP = json.loads(Path("data/food_hint_style_map_v2.json").read_text(encoding="utf-8"))
UNIVERSAL_RULES = json.loads(Path("data/universal_hint_rules_v1.json").read_text(encoding="utf-8"))


def is_all_four_char_hints(hints: list[str]) -> bool:
    return bool(hints) and all(len(h) == 4 for h in hints)

def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def has_early_reveal_hit(category: str, answer: str, slot: int, hint: str) -> bool:
    if not EARLY_REVEAL_ENABLED:
        return False
    if slot not in EARLY_REVEAL_SLOTS:
        return False
    key = f"{category}::{answer}"
    terms = list(EARLY_REVEAL_CATEGORY_TERMS.get(category, [])) + list(EARLY_REVEAL_ANSWER_TERMS.get(key, []))
    return any(term and term in hint for term in terms)


def main() -> None:
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
        if NATURAL_LANGUAGE_GUARD.get("forbid_forced_four_char_style") and is_all_four_char_hints(hs):
            forced_four_char_items += 1

        if c == "游戏":
            game_total += 1
        if c == "美食":
            food_total += 1
            expected_food_hints = FOOD_STYLE_MAP.get(a)
            if expected_food_hints and hs == expected_food_hints[:7]:
                food_template_hits += 1
                food_style_hits += 1

        item_early_reveal = False
        for idx, h in enumerate(hs, start=1):
            if h in META_TERMS:
                meta_hits += 1
            if h in GENERIC_TERMS:
                generic_term_hits += 1
            if has_overlap(a, h):
                overlap_hits_all += 1
                if c == "游戏":
                    overlap_hits_game += 1
                else:
                    overlap_hits_non_game += 1
            if has_early_reveal_hit(c, a, idx, h):
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
        "universal_hint_count_target": int(UNIVERSAL_CONSTRAINTS.get("hint_count", UNIVERSAL_RULES.get("hint_count", 7))),
        "non7_hint_items": non7_hint_items,
        "duplicate_hint_items": duplicate_hint_items,
        "forced_four_char_items": forced_four_char_items,
        "global_hint_reuse_hits": global_hint_reuse_hits,
        "global_hint_reuse_examples": global_hint_reuse_examples,
        "same_category_hint_reuse_hits": same_category_hint_reuse_hits,
        "same_category_hint_reuse_examples": same_category_hint_reuse_examples,
        "early_reveal_guard_enabled": EARLY_REVEAL_ENABLED,
        "early_reveal_guard_hard_fail": EARLY_REVEAL_HARD_FAIL,
        "early_reveal_guard_slots": EARLY_REVEAL_SLOTS,
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

    if EARLY_REVEAL_ENABLED and EARLY_REVEAL_HARD_FAIL and early_reveal_hits > 0:
        print(f"hard_fail: early_reveal_hits={early_reveal_hits}")
        sys.exit(1)
    if VALIDATOR_HARD_FAIL and hard_fail_hits > 0:
        print(f"hard_fail: machine_check_hits={hard_fail_hits}")
        sys.exit(1)


if __name__ == "__main__":
    main()
