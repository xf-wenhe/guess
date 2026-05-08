#!/usr/bin/env python3
import collections
import hashlib
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


POOLS = {
    "origin_context": ["上古传闻", "远古背景", "口耳相传", "神话源流"],
    "ritual_scene": ["传说场景", "古老仪式"],
    "entity_role": ["神祇相关", "奇异生灵", "异兽传说"],
    "story_structure": ["英雄叙事", "故事母题", "天地秩序"],
    "symbolic_mark": ["祭祀痕迹", "象征意味", "神异色彩"],
    "fate_power": ["因果轮回", "天命牵引", "神力显化"],
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
    sub = [it for it in data if norm(it.get("category", "")) == "神话" and len((it.get("hints") or [])) >= 7]

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
        seed = int(hashlib.sha256(f"myth::{answer}".encode("utf-8")).hexdigest(), 16)

        dims = ["origin_context", "entity_role", "symbolic_mark", "story_structure", "ritual_scene"]
        slot6_dim = "fate_power"
        if slot7_dim == "fate_power":
            slot6_dim = "origin_context"
        elif slot7_dim == "origin_context":
            slot6_dim = "fate_power"
        elif slot7_dim == "ritual_scene":
            dims[4] = "symbolic_mark"
            slot6_dim = "fate_power"

        new = [""] * 7
        new[6] = slot7
        used = {slot7}

        for idx, dim in enumerate(dims, start=1):
            cand = pick(POOLS[dim], counter, used, answer_chars, seed + idx * 11)
            if cand is None:
                cand = old[idx - 1]
            new[idx - 1] = cand
            used.add(cand)

        cand6 = pick(POOLS[slot6_dim], counter, used, answer_chars, seed + 66)
        if cand6 is None:
            # fallback: choose any dimension different from slot7
            for dim in ["fate_power", "origin_context", "story_structure", "entity_role", "symbolic_mark", "ritual_scene"]:
                if dim == slot7_dim:
                    continue
                cand6 = pick(POOLS[dim], counter, used, answer_chars, seed + 77 + len(dim))
                if cand6:
                    break
        if cand6 is None:
            cand6 = old[5]
        new[5] = cand6

        # avoid duplicate full sets by rotating slot6 if needed
        if tuple(new) in seen_full:
            for dim in ["fate_power", "origin_context", "story_structure", "entity_role", "symbolic_mark", "ritual_scene"]:
                if dim == slot7_dim:
                    continue
                alt = pick(POOLS[dim], counter, set(new[:5] + [new[6]]), answer_chars, seed + 101 + len(dim))
                if alt and tuple(new[:5] + [alt, new[6]]) not in seen_full:
                    new[5] = alt
                    break

        seen_full.add(tuple(new))
        if new != old:
            it["hints"] = new
            changed += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category": "神话", "changed_items": changed, "total": len(sub)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
