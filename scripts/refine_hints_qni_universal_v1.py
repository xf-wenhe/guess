from __future__ import annotations

import argparse
import json
from pathlib import Path

from hint_quality_v29_common import detect_cross_domain


META_TERMS = {
    "标志性冲突",
    "代表性设定",
    "核心母题",
    "高光桥段",
    "知名剧情节点",
    "粉丝高共识",
    "答案锁定线索",
    "唯一锚点",
    "终局指向",
    "强辨识设定",
}

GENERIC_WEAK_TERMS = {
    "系列作品",
    "番剧作品",
    "虚构故事",
    "长篇连载",
    "观众熟知",
    "角色互动",
}

# QNI-style: weak -> strong, with late anchor hints.
OVERRIDE_HINTS = {
    ("动漫", "樱桃小丸子"): [
        "日本",
        "昭和",
        "家庭日常",
        "班级生活",
        "清水市",
        "三年四班",
        "友藏爷爷",
    ]
}

CATEGORY_POOL = {
    "动漫": [
        "日本",
        "连载作品",
        "家庭日常",
        "班级生活",
        "地域舞台",
        "人物关系",
        "核心锚点",
    ],
    "游戏": [
        "互动娱乐",
        "规则系统",
        "对战机制",
        "成长体系",
        "任务目标",
        "团队协作",
        "关键锚点",
    ],
    "美食": [
        "饮食文化",
        "烹饪方式",
        "口味层次",
        "食材组合",
        "地域特色",
        "食用场景",
        "经典代表",
    ],
}

DEFAULT_POOL = [
    "常见概念",
    "主题线索",
    "场景关联",
    "语义特征",
    "高辨识线索",
    "强关联线索",
    "答案锚点",
]


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def is_valid_hint(category: str, answer: str, hint: str, used: set[str]) -> bool:
    if not hint or hint in used:
        return False
    if hint in META_TERMS:
        return False
    if has_overlap(answer, hint):
        return False
    if detect_cross_domain(category, hint):
        return False
    return True


def choose_replacement(category: str, answer: str, slot_idx: int, used: set[str]) -> str | None:
    pool = CATEGORY_POOL.get(category, DEFAULT_POOL)

    ordered_candidates = []
    if slot_idx < len(pool):
        ordered_candidates.append(pool[slot_idx])
    ordered_candidates.extend(pool)
    ordered_candidates.extend(DEFAULT_POOL)

    for cand in ordered_candidates:
        if is_valid_hint(category, answer, cand, used):
            return cand
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine generic hints with universal QNI-style policy")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))

    touched_items = 0
    replaced_terms = 0
    overrides_applied = 0

    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        hints = [str(h).strip() for h in (item.get("hints") or [])[:7]]

        if len(hints) != 7:
            continue

        override = OVERRIDE_HINTS.get((category, answer))
        if override:
            item["hints"] = override
            touched_items += 1
            overrides_applied += 1
            continue

        used = set(hints)
        new_hints = hints[:]
        local_changed = False

        for i, h in enumerate(hints):
            if h not in GENERIC_WEAK_TERMS and h not in META_TERMS:
                continue

            used.discard(h)
            replacement = choose_replacement(category, answer, i, used)
            if replacement is None:
                used.add(h)
                continue

            new_hints[i] = replacement
            used.add(replacement)
            local_changed = True
            replaced_terms += 1

        if local_changed:
            item["hints"] = new_hints
            touched_items += 1

    if args.apply:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "total_items": len(data),
        "touched_items": touched_items,
        "replaced_terms": replaced_terms,
        "overrides_applied": overrides_applied,
        "apply": bool(args.apply),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
