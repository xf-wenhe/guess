#!/usr/bin/env python3
import collections
import hashlib
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


POOLS = {
    "sky_location": ["夜空目标", "天区分布", "星系结构", "宇宙背景"],
    "motion_cycle": ["天体运行", "轨道变化", "运行方向", "周期规律"],
    "observation": ["观测窗口", "望远观测", "观测条件", "星图定位"],
    "scale_distance": ["深空尺度", "空间距离"],
    "signal_feature": ["光谱线索", "亮度差异", "天象变化", "引力影响"],
}


def classify(hint: str) -> str:
    h = norm(hint)
    for dim, pool in POOLS.items():
        if h in pool:
            return dim
    return "unknown"


def pick(pool, counter, used, answer_chars, seed):
    choices = []
    for raw in pool:
        h = norm(raw)
        if not h:
            continue
        if len(h) > 5:
            continue
        if h in used:
            continue
        if set(h) & answer_chars:
            continue
        choices.append(h)
    if not choices:
        return None
    rot = seed % len(choices)
    choices = choices[rot:] + choices[:rot]
    choices.sort(key=lambda x: (counter[x], x))
    return choices[0]


def main() -> int:
    path = Path("assets/puzzles.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    sub = [it for it in data if norm(it.get("category", "")) == "宇宙" and len((it.get("hints") or [])) >= 7]

    counter = collections.Counter()
    for it in sub:
        for h in (it.get("hints") or [])[:7]:
            counter[norm(h)] += 1

    changed = 0
    seen_full = set()
    for it in sub:
        answer = norm(it.get("answer", ""))
        answer_chars = {c for c in answer if c.strip()}
        old = [norm(h) for h in (it.get("hints") or [])[:7]]
        slot7 = old[6]
        slot7_dim = classify(slot7)
        seed = int(hashlib.sha256(f"universe::{answer}".encode("utf-8")).hexdigest(), 16)

        new = [""] * 7
        new[6] = slot7
        used = {slot7}

        plan = [
            (0, "sky_location"),
            (1, "motion_cycle"),
            (2, "observation"),
            (3, "scale_distance"),
            (4, "signal_feature"),
        ]

        for idx, dim in plan:
            cand = pick(POOLS[dim], counter, used, answer_chars, seed + idx * 17)
            if cand is None:
                cand = old[idx]
            new[idx] = cand
            used.add(cand)

        slot6_order = ["motion_cycle", "signal_feature", "scale_distance", "sky_location", "observation"]
        chosen = None
        for dim in slot6_order:
            if dim == slot7_dim:
                continue
            cand = pick(POOLS[dim], counter, used, answer_chars, seed + 101 + len(dim))
            if cand:
                chosen = cand
                break
        if chosen is None:
            chosen = old[5]
        new[5] = chosen

        if tuple(new) in seen_full:
            for dim in slot6_order:
                if dim == slot7_dim:
                    continue
                cand = pick(POOLS[dim], counter, set(new[:5] + [new[6]]), answer_chars, seed + 151 + len(dim))
                if cand and tuple(new[:5] + [cand, new[6]]) not in seen_full:
                    new[5] = cand
                    break

        seen_full.add(tuple(new))
        if new != old:
            it["hints"] = new
            changed += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category": "宇宙", "changed_items": changed, "total": len(sub)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
