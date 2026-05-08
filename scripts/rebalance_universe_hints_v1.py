#!/usr/bin/env python3
import collections
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


SLOT_POOLS = {
    1: ["夜空目标", "天区分布", "星系结构", "宇宙背景"],
    2: ["天体运行", "轨道变化", "运行方向", "周期规律"],
    3: ["观测窗口", "望远观测", "观测条件", "星图定位"],
    4: ["深空尺度", "空间距离", "宇宙背景", "天区分布"],
    5: ["光谱线索", "亮度差异", "天象变化", "引力影响"],
    6: ["观测条件", "星图定位", "周期规律", "望远观测"],
}


def pick_least_used(pool, used_local, answer_chars, counter):
    choices = []
    for raw in pool:
        h = norm(raw)
        if not h:
            continue
        if len(h) > 5:
            continue
        if h in used_local:
            continue
        if set(h) & answer_chars:
            continue
        choices.append(h)
    if not choices:
        return None
    choices.sort(key=lambda x: (counter[x], x))
    return choices[0]


def main() -> int:
    path = Path("assets/puzzles.json")
    items = json.loads(path.read_text(encoding="utf-8"))
    sub = [it for it in items if norm(it.get("category", "")) == "宇宙" and len((it.get("hints") or [])) >= 7]

    counters = {
        slot: collections.Counter(norm((it.get("hints") or [""] * 7)[slot - 1]) for it in sub)
        for slot in range(1, 7)
    }

    changed = 0
    for it in sub:
        answer = norm(it.get("answer", ""))
        answer_chars = {c for c in answer if c.strip()}
        hints = [str(x).strip() for x in (it.get("hints") or [])[:7]]
        new_hints = hints[:]
        used_local = {norm(hints[6])}

        for slot in range(1, 7):
            old = norm(new_hints[slot - 1])
            counters[slot][old] -= 1
            choice = pick_least_used(SLOT_POOLS[slot], used_local, answer_chars, counters[slot])
            if choice is None:
                choice = old
            new_hints[slot - 1] = choice
            counters[slot][choice] += 1
            used_local.add(choice)

        if new_hints != hints:
            it["hints"] = new_hints
            changed += 1

    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category": "宇宙", "changed_items": changed, "total": len(sub)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
