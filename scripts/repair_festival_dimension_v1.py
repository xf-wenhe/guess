#!/usr/bin/env python3
import collections
import hashlib
import json
import re
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


POOLS = {
    "season_context": ["时令节点", "节庆色彩", "时节记忆", "节令变化", "节庆氛围", "传统时节"],
    "social_scene": ["假期安排", "家人团聚", "亲友相聚", "团圆时刻", "走亲访友", "行程计划", "人群聚集"],
    "ritual_custom": ["礼俗延续", "民俗线索", "庆典场景", "庆祝方式", "传统活动", "仪式感强", "习俗环节", "节俗讲究"],
    "visual_scene": ["街巷热闹", "装饰明显", "节庆布置", "灯火明亮", "应景陈设", "现场氛围"],
    "symbol_hint": ["应景食物", "时令表达", "时令提示", "节日符号"],
}


def classify_festival(hint: str) -> str:
    h = norm(hint)
    if any(token in h for token in ["时令", "时节", "节令", "传统时节", "节庆"]):
        return "season_context"
    if any(token in h for token in ["家人", "亲友", "团圆", "走亲", "假期", "行程", "人群"]):
        return "social_scene"
    if any(token in h for token in ["礼俗", "民俗", "庆典", "庆祝", "传统活动", "仪式", "习俗", "节俗"]):
        return "ritual_custom"
    if any(token in h for token in ["街巷", "装饰", "布置", "灯火", "陈设", "现场"]):
        return "visual_scene"
    if any(token in h for token in ["应景", "时令表达", "时令提示", "符号", "食物"]):
        return "symbol_hint"
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


def pick_many(pool, counter, used, answer_chars, seed):
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
        return []
    rot = seed % len(choices)
    choices = choices[rot:] + choices[:rot]
    choices.sort(key=lambda x: (counter[x], x))
    return choices


def main() -> int:
    path = Path("assets/puzzles.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    sub = [x for x in data if norm(x.get("category", "")) == "节日" and len((x.get("hints") or [])) >= 7]

    pool_counter = collections.Counter()
    for it in sub:
        for h in (it.get("hints") or [])[:7]:
            pool_counter[norm(h)] += 1

    changed = 0
    seen_full = collections.Counter()
    for it in sub:
        answer = norm(it.get("answer", ""))
        answer_chars = {c for c in answer if c.strip()}
        old = [norm(h) for h in (it.get("hints") or [])[:7]]
        slot7 = old[6]
        slot7_dim = classify_festival(slot7)

        seed = int(hashlib.sha256(f"festival::{answer}".encode("utf-8")).hexdigest(), 16)
        used = {slot7}
        new = [""] * 7
        new[6] = slot7

        plan = [
            (0, "season_context"),
            (1, "social_scene"),
            (2, "ritual_custom"),
            (3, "visual_scene"),
            (4, "symbol_hint"),
        ]
        local_dim_count = collections.Counter([slot7_dim])

        for idx, dim in plan:
            pick_hint = pick(POOLS[dim], pool_counter, used, answer_chars, seed + idx * 13)
            if pick_hint is None:
                pick_hint = old[idx]
            new[idx] = pick_hint
            used.add(pick_hint)
            local_dim_count[dim] += 1

        # slot6: choose a dimension that does not collide with slot7 and keeps per-dim <=2
        dim_order = ["social_scene", "ritual_custom", "visual_scene", "season_context", "symbol_hint"]
        chosen = None
        slot6_dim = None
        for dim in dim_order:
            if dim == slot7_dim:
                continue
            if local_dim_count[dim] >= 2:
                continue
            cand = pick(POOLS[dim], pool_counter, used, answer_chars, seed + 6 * 17 + len(dim))
            if cand:
                chosen = cand
                slot6_dim = dim
                local_dim_count[dim] += 1
                break
        if chosen is None:
            chosen = old[5]
            slot6_dim = classify_festival(chosen)
        new[5] = chosen

        # final uniqueness fallback
        if len(set(new)) < 7:
            for dim in ["season_context", "social_scene", "ritual_custom", "visual_scene", "symbol_hint"]:
                if len(set(new)) == 7:
                    break
                cand = pick(POOLS[dim], pool_counter, set(new), answer_chars, seed + 97)
                if cand:
                    new[5] = cand

        # avoid full-set duplication by trying alternate slot6 candidates
        full_key = tuple(new)
        if seen_full[full_key] > 0:
            alt_dims = ["social_scene", "ritual_custom", "visual_scene", "season_context", "symbol_hint"]
            alt_used = set(new)
            alt_used.discard(new[5])
            for dim in alt_dims:
                if dim == slot7_dim:
                    continue
                if dim == slot6_dim and seen_full[full_key] > 0:
                    # still allow same dimension with alternate token
                    pass
                for cand in pick_many(POOLS[dim], pool_counter, alt_used, answer_chars, seed + 113 + len(dim)):
                    trial = list(new)
                    trial[5] = cand
                    if seen_full[tuple(trial)] == 0:
                        new = trial
                        full_key = tuple(new)
                        break
                if seen_full[full_key] == 0:
                    break

        seen_full[tuple(new)] += 1

        if new != old:
            it["hints"] = new
            changed += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category": "节日", "changed_items": changed, "total": len(sub)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
