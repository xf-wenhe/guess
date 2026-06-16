from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

POLICY_PATH = Path("data/final_hint_policy_v1.json")
CJK_RE = re.compile(r"[\u3400-\u9FFF]")
POLICY_DEFAULTS: dict[str, Any] = {
    "natural_language_guard": {},
    "universal_rules": {},
    "universal_constraints": {},
    "early_reveal_enabled": False,
    "early_reveal_hard_fail": False,
    "early_reveal_slots": [1, 2, 3],
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8")
    return json.loads(text)


class HintPolicy:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.meta_terms = set(payload.get("meta_terms", []))
        self.generic_terms = set(payload.get("generic_terms", []))
        self.forbidden_hint_terms = set(payload.get("forbidden_hint_terms", []))
        self.food_style_map = payload.get("food_style_map", {})
        self.natural_language_guard = payload.get("natural_language_guard", {})
        self.universal_rules = payload.get("universal_rules", {})
        self.universal_constraints = payload.get("universal_constraints", {})
        self.early_reveal_enabled = bool(payload.get("early_reveal_enabled", False))
        self.early_reveal_hard_fail = bool(payload.get("early_reveal_hard_fail", False))
        self.early_reveal_slots = payload.get("early_reveal_slots", [1, 2, 3])


def load_hint_policy(policy_path: Path = POLICY_PATH) -> HintPolicy:
    payload = _read_json(policy_path, POLICY_DEFAULTS)
    if not isinstance(payload, dict):
        payload = POLICY_DEFAULTS
    return HintPolicy(payload)


def has_answer_overlap(answer: str, hint: str) -> bool:
    return bool(set(answer) & set(hint))


def has_early_reveal_hit(policy: HintPolicy, category: str, answer: str, slot: int, hint: str) -> bool:
    if not policy.early_reveal_enabled:
        return False
    if slot not in policy.early_reveal_slots:
        return False
    if not answer or len(answer) < 2:
        return False
    return answer.startswith(hint) or answer.endswith(hint)


def is_all_four_char_hints(hints: list[str]) -> bool:
    if not hints:
        return False
    return all(len(hint) == 4 for hint in hints)
