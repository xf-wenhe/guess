#!/usr/bin/env python3
import collections
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


SLOT_POOLS = {
    1: ["上古传闻", "远古背景", "口耳相传", "神话源流", "传说场景", "古老仪式"],
    2: ["神祇相关", "奇异生灵", "异兽传说", "英雄叙事", "故事母题", "天地秩序"],
    3: ["祭祀痕迹", "象征意味", "因果轮回", "天命牵引", "神异色彩", "神力显化"],
    4: ["传说场景", "天地秩序", "故事母题", "英雄叙事", "神祇相关", "神话源流"],
    5: ["异兽传说", "神异色彩", "上古传闻", "象征意味", "祭祀痕迹", "奇异生灵"],
    6: ["因果轮回", "天命牵引", "口耳相传", "古老仪式", "神力显化", "远古背景"],
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
    sub = [it for it in items if norm(it.get("category", "")) == "神话" and len((it.get("hints") or [])) >= 7]

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
    print(json.dumps({"category": "神话", "changed_items": changed, "total": len(sub)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
