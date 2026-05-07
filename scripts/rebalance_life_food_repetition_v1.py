#!/usr/bin/env python3
import collections
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def pick_least_used(pool, used_local, answer_chars, counter):
    candidates = []
    for item in pool:
        h = norm(item)
        if not h:
            continue
        if len(h) > 5:
            continue
        if h in used_local:
            continue
        if set(h) & answer_chars:
            continue
        candidates.append(h)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (counter[x], x))
    return candidates[0]


FOOD_SLOT_POOLS = {
    1: ["餐桌日常", "饮食选择", "热食场景", "口味偏好", "饭点常见", "家常餐食", "日常吃食", "夜宵常见", "外卖常点"],
    2: ["食材处理", "做法起手", "风味铺垫", "调味方向", "香气先出"],
    3: ["咀嚼反馈", "层次变化", "味型成形", "热度状态", "口感走向", "香味外扩", "主料搭配", "口感分层"],
    4: ["回味落点", "搭配习惯", "入口留香", "熟度判断", "质地表现", "口味收束", "蘸料习惯", "口味分流"],
}

LIFE_SLOT_POOLS = {
    1: ["日常节律", "居家场景", "手边小事", "生活片刻", "时间安排", "当天事务", "起居片段", "日常步骤", "居家日常", "手边事务", "日程安排", "当天节奏"],
    2: ["按序进行", "顺手处理", "场景切换", "固定习惯", "经常会做", "临时决定", "马上处理", "当天安排"],
    3: ["动作细节", "步骤衔接", "前后连贯", "习惯维持", "流程推进", "收尾动作", "状态调整", "过程衔接"],
    4: ["结果反馈", "完成状态", "场景收束", "日常闭环", "实际用途", "生活需要", "效率提升", "即时可感"],
}


def rebalance_category(items, category, slot_pools):
    index_items = [it for it in items if norm(it.get("category", "")) == category and len((it.get("hints") or [])) >= 7]
    counters = {slot: collections.Counter(norm(it["hints"][slot - 1]) for it in index_items) for slot in [1, 2, 3, 4]}

    changed = 0
    for it in index_items:
        answer = norm(it.get("answer", ""))
        answer_chars = {c for c in answer if c.strip()}
        hints = [str(x).strip() for x in it.get("hints")[:7]]
        new_hints = hints[:]
        used_local = {norm(x) for x in hints[4:]}  # keep slots 5-7 untouched

        for slot in [1, 2, 3, 4]:
            old = norm(new_hints[slot - 1])
            counters[slot][old] -= 1
            choice = pick_least_used(slot_pools[slot], used_local, answer_chars, counters[slot])
            if choice is None:
                choice = old
            new_hints[slot - 1] = choice
            counters[slot][choice] += 1
            used_local.add(choice)

        if new_hints != hints:
            it["hints"] = new_hints
            changed += 1

    return changed


def main() -> int:
    path = Path("assets/puzzles.json")
    items = json.loads(path.read_text(encoding="utf-8"))
    summary = {
        "food_changed": rebalance_category(items, "美食", FOOD_SLOT_POOLS),
        "life_changed": rebalance_category(items, "生活", LIFE_SLOT_POOLS),
    }
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
