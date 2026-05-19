from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class HintPolicy:
    final_policy: dict
    universal_constraints: dict
    meta_terms: set[str]
    natural_language_guard: dict
    generic_terms: set[str]
    validator_hard_fail: bool
    early_reveal_enabled: bool
    early_reveal_hard_fail: bool
    early_reveal_slots: list[int]
    early_reveal_category_terms: dict[str, list[str]]
    early_reveal_answer_terms: dict[str, list[str]]
    food_style_map: dict
    universal_rules: dict

    @property
    def forbidden_hint_terms(self) -> set[str]:
        return self.meta_terms | self.generic_terms


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_hint_policy(
    policy_path: Path = Path("data/final_hint_policy_v1.json"),
    food_style_path: Path = Path("data/food_hint_style_map_v2.json"),
    universal_rules_path: Path = Path("data/universal_hint_rules_v1.json"),
) -> HintPolicy:
    final_policy = _read_json(policy_path, {})
    universal_constraints = final_policy.get("universal_constraints", {})
    natural_language_guard = universal_constraints.get("natural_language_guard", {})
    validator_machine_checks = universal_constraints.get("validator_machine_checks", {})
    early_reveal_guard = universal_constraints.get("early_reveal_guard", {})

    return HintPolicy(
        final_policy=final_policy,
        universal_constraints=universal_constraints,
        meta_terms={
            str(value).strip()
            for value in universal_constraints.get("forbidden_meta_terms", [])
            if str(value).strip()
        },
        natural_language_guard=natural_language_guard,
        generic_terms={
            str(value).strip()
            for value in natural_language_guard.get("forbidden_generic_terms", [])
            if str(value).strip()
        },
        validator_hard_fail=bool(
            validator_machine_checks.get("hard_fail_on_any_violation", False)
        ),
        early_reveal_enabled=bool(early_reveal_guard.get("enabled", False)),
        early_reveal_hard_fail=bool(
            early_reveal_guard.get("hard_fail_on_hit", False)
        ),
        early_reveal_slots=[
            int(value) for value in (early_reveal_guard.get("slots") or [1, 2, 3])
        ],
        early_reveal_category_terms={
            str(key): [str(value).strip() for value in values]
            for key, values in (early_reveal_guard.get("category_block_terms") or {}).items()
        },
        early_reveal_answer_terms={
            str(key): [str(value).strip() for value in values]
            for key, values in (early_reveal_guard.get("answer_block_terms") or {}).items()
        },
        food_style_map=_read_json(food_style_path, {}),
        universal_rules=_read_json(universal_rules_path, {}),
    )


def collect_hint_counts(puzzles: list[dict]) -> Counter[str]:
    return Counter(
        str(hint).strip()
        for item in puzzles
        for hint in (item.get("hints") or [])
        if str(hint).strip()
    )


def is_all_four_char_hints(hints: list[str]) -> bool:
    return bool(hints) and all(len(hint) == 4 for hint in hints)


def has_answer_overlap(answer: str, hint: str) -> bool:
    answer_chars = {char for char in answer if char.strip()}
    hint_chars = {char for char in hint if char.strip()}
    return bool(answer_chars & hint_chars)


def has_early_reveal_hit(
    policy: HintPolicy,
    category: str,
    answer: str,
    slot: int,
    hint: str,
) -> bool:
    if not policy.early_reveal_enabled:
        return False
    if slot not in policy.early_reveal_slots:
        return False
    key = f"{category}::{answer}"
    terms = list(policy.early_reveal_category_terms.get(category, []))
    terms += list(policy.early_reveal_answer_terms.get(key, []))
    return any(term and term in hint for term in terms)


def hint_quality_weight(
    answer: str,
    hint: str,
    hints: list[str],
    policy: HintPolicy,
    global_hint_counts: Counter[str],
) -> tuple[float, str]:
    cleaned_hint = str(hint).strip()
    if not cleaned_hint:
        return 0.0, "empty"

    penalties: list[str] = []
    if len(cleaned_hint) < 2 or len(cleaned_hint) > 8:
        penalties.append("length")
    if not CJK_RE.search(cleaned_hint):
        penalties.append("no_cjk")
    if has_answer_overlap(answer, cleaned_hint):
        penalties.append("answer_overlap")
    if hints.count(cleaned_hint) > 1:
        penalties.append("item_duplicate")
    if cleaned_hint in policy.forbidden_hint_terms:
        penalties.append("forbidden_term")

    reuse_count = global_hint_counts.get(cleaned_hint, 0)
    if reuse_count >= 10:
        penalties.append("very_high_reuse")
    elif reuse_count >= 4:
        penalties.append("high_reuse")

    weight = 1.0
    for penalty in penalties:
        if penalty in {"answer_overlap", "forbidden_term"}:
            weight *= 0.2
        elif penalty in {"length", "no_cjk", "item_duplicate", "very_high_reuse"}:
            weight *= 0.35
        else:
            weight *= 0.6

    return max(0.05, weight), "+".join(penalties) if penalties else "clean"
