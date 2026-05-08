#!/usr/bin/env python3
import collections
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


SLOT_POOLS = {
    1: ["时令节点", "节庆色彩", "时节记忆", "节令变化", "节庆氛围", "传统时节"],
    2: ["假期安排", "家人团聚", "亲友相聚", "团圆时刻", "走亲访友", "行程计划"],
    3: ["礼俗延续", "民俗线索", "庆典场景", "庆祝方式", "传统活动", "仪式感强"],
    4: ["街巷热闹", "装饰明显", "节庆布置", "灯火明亮", "应景陈设", "现场氛围"],
    5: ["应景食物", "时令表达", "习俗环节", "节俗讲究", "时令提示", "节日符号"],
    6: ["人群聚集", "礼俗延续", "庆典场景", "节庆氛围", "假期安排", "时节记忆"],
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
    sub = [it for it in items if norm(it.get("category", "")) == "节日" and len((it.get("hints") or [])) >= 7]

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
        used_local = {norm(hints[6])}  # preserve slot7 anchor

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
    print(json.dumps({"category": "节日", "changed_items": changed, "total": len(sub)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
