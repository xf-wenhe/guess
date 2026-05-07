from __future__ import annotations

import argparse
import json
from pathlib import Path


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def pick_from_candidates(
    answer: str,
    used: set[str],
    forbidden: set[str],
    candidates: list[str],
) -> str | None:
    for c in candidates:
        cand = str(c).strip()
        if not cand:
            continue
        if cand in used:
            continue
        if cand in forbidden:
            continue
        if has_overlap(answer, cand):
            continue
        return cand
    return None


def in_slot_pool(hint: str, pool: list[str]) -> bool:
    if hint in pool:
        return True
    # Allow light fuzzy match so existing concrete variants can be reused in the same slot.
    for p in pool:
        if not p:
            continue
        if p in hint or hint in p:
            return True
    return False


def stable_seed(text: str) -> int:
    return sum(ord(ch) for ch in text)


def rotate_pool(pool: list[str], seed: int) -> list[str]:
    if not pool:
        return []
    k = seed % len(pool)
    return pool[k:] + pool[:k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply anime Conan-style 7-slot hints v1")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--rules", default="data/anime_conan_style_rules_v1.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    data = json.loads(input_path.read_text(encoding="utf-8"))

    category = str(rules.get("category", "动漫"))
    sample_answer = str(rules.get("sample_answer", "名侦探柯南"))
    sample_hints = [str(x).strip() for x in rules.get("sample_hints", [])[:7]]
    forbidden = {str(x).strip() for x in rules.get("forbidden_terms", []) if str(x).strip()}

    slots = rules.get("slots", {})
    slot_pools = [
        [str(x).strip() for x in slots.get("1_region", []) if str(x).strip()],
        [str(x).strip() for x in slots.get("2_theme", []) if str(x).strip()],
        [str(x).strip() for x in slots.get("3_role", []) if str(x).strip()],
        [str(x).strip() for x in slots.get("4_prop", []) if str(x).strip()],
        [str(x).strip() for x in slots.get("5_setting", []) if str(x).strip()],
        [str(x).strip() for x in slots.get("6_source", []) if str(x).strip()],
        [str(x).strip() for x in slots.get("7_anchor", []) if str(x).strip()],
    ]

    changed = 0
    total = 0
    fallback_count = 0

    for item in data:
        if item.get("category") != category:
            continue
        answer = str(item.get("answer", "")).strip()
        old_hints = [str(h).strip() for h in (item.get("hints") or [])[:7]]
        if not answer:
            continue
        total += 1

        if answer == sample_answer and len(sample_hints) == 7:
            new_hints = sample_hints[:]
        else:
            used: set[str] = set()
            new_hints: list[str] = []
            seed = stable_seed(answer)

            for i, pool in enumerate(slot_pools):
                slot_old = [h for h in old_hints if in_slot_pool(h, pool)]
                rotated = rotate_pool(pool, seed + i * 17)
                ordered_candidates = rotated + [h for h in slot_old if h not in rotated]
                picked = pick_from_candidates(answer, used, forbidden, ordered_candidates)
                if picked is None:
                    fallback_count += 1
                    picked = f"动漫线索{i + 1}"
                    if has_overlap(answer, picked) or picked in used:
                        picked = f"番剧线索{i + 1}"

                used.add(picked)
                new_hints.append(picked)

        if new_hints != old_hints:
            item["hints"] = new_hints
            changed += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "category": category,
                "total": total,
                "changed_items": changed,
                "fallback_slots": fallback_count,
                "apply": bool(args.apply),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()