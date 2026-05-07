#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def pick(pool, seed, used, answer_chars):
    size = len(pool)
    start = seed % size
    for i in range(size):
        cand = norm(pool[(start + i) % size])
        if not cand or cand in used:
            continue
        if len(cand) > 5:
            continue
        if set(cand) & answer_chars:
            continue
        return cand
    return None


FOOD_SLOT5 = [
    "饭桌常见", "聚餐常点", "节令餐桌", "夜宵常见", "店里现做", "吃法讲究", "热气上桌", "茶桌常见",
]

FOOD_SLOT6 = [
    "熟客会点", "餐桌主角", "招牌吃法", "摆盘显眼", "节日常见", "上桌很快", "多人会点", "常被点单",
]

LIFE_SLOT5 = [
    "手边就做", "顺路处理", "当天要做", "临时安排", "忙完再说", "顺手解决", "居家安排", "手边收尾",
]

LIFE_SLOT6 = [
    "起居变化", "生活反馈", "场景过渡", "顺手收尾", "当下感受", "后续安排", "忙后状态", "生活回响",
]


def repair(items, category, slot5_pool, slot6_pool, seed_tag):
    changed = 0
    for item in items:
        if norm(item.get("category", "")) != category:
            continue
        answer = norm(item.get("answer", ""))
        hints = [str(x).strip() for x in (item.get("hints") or [])[:7]]
        if len(hints) < 7:
            continue
        answer_chars = {c for c in answer if c.strip()}
        used = {norm(h) for i, h in enumerate(hints) if i not in [4, 5]}
        seed = int(hashlib.sha256(f"{seed_tag}::{answer}".encode("utf-8")).hexdigest(), 16)
        slot5 = pick(slot5_pool, seed + 5 * 41, used, answer_chars)
        if slot5 is None:
            raise SystemExit(f"cannot_pick_slot5:{category}:{answer}")
        used.add(slot5)
        slot6 = pick(slot6_pool, seed + 6 * 41, used, answer_chars)
        if slot6 is None:
            raise SystemExit(f"cannot_pick_slot6:{category}:{answer}")
        new_hints = hints[:]
        new_hints[4] = slot5
        new_hints[5] = slot6
        if new_hints != hints:
            item["hints"] = new_hints
            changed += 1
    return changed


def main() -> int:
    path = Path("assets/puzzles.json")
    items = json.loads(path.read_text(encoding="utf-8"))
    summary = {
        "food_changed": repair(items, "美食", FOOD_SLOT5, FOOD_SLOT6, "food-dim-fix"),
        "life_changed": repair(items, "生活", LIFE_SLOT5, LIFE_SLOT6, "life-dim-fix"),
    }
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
