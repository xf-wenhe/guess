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


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def is_mostly_chinese(text: str) -> bool:
    if not text:
        return False
    for ch in text:
        if not ('\u4e00' <= ch <= '\u9fff'):
            return False
    return True


def build_dynamic_name_like(anime_map: dict, seed_names: set[str]) -> set[str]:
    generic_markers = [
        "组织", "世界", "兵团", "学院", "学园", "计划", "高专", "之墙", "王", "队", "团", "界", "城",
        "法", "术", "气功", "机动", "武魂", "魂环", "剑", "刀", "球", "赛", "圈", "改编", "国漫", "武侠",
        "番剧", "动画", "系列", "故事", "角色", "成长", "冲突", "设定", "网文", "电竞", "远航", "草帽",
        "忍者", "九尾", "巫女", "战国", "四魂玉", "铁碎牙", "日轮", "柱级",
    ]

    out = set(seed_names)
    for hints in anime_map.values():
        for raw in hints:
            t = str(raw).strip()
            if not t:
                continue
            if t in out:
                continue
            if not is_mostly_chinese(t):
                continue
            if len(t) < 2 or len(t) > 4:
                continue
            if any(m in t for m in generic_markers):
                continue
            out.add(t)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Limit anime name-like tokens to <=1 per item v41")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--rules", default="data/anime_ladder_rules_v40.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    anime_map = json.loads(Path(args.map).read_text(encoding="utf-8"))

    seed_name_like = {str(x).strip() for x in rules.get("name_like_tokens", []) if str(x).strip()}
    generic_pool = [
        *[str(x).strip() for x in rules.get("generic_low", []) if str(x).strip()],
        *[str(x).strip() for x in rules.get("generic_mid", []) if str(x).strip()],
        "番剧作品",
        "虚构故事",
        "系列作品",
        "冲突升级",
        "成长变化",
    ]

    name_like = build_dynamic_name_like(anime_map, seed_name_like)

    changed = 0
    moved_name_to_late_slots = 0
    touched_items = 0
    for item in data:
        if item.get("category") != "动漫":
            continue

        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue

        # Keep Conan anchor unchanged.
        if answer == "名侦探柯南":
            continue

        hints = [str(h).strip() for h in (item.get("hints") or [])[:7]]
        if len(hints) != 7:
            continue

        keep_name_budget = 1
        used = set(hints)
        new_hints = hints[:]
        local_changed = False

        # Build replacement candidates: prefer answer-specific non-name clues.
        answer_specific = [str(x).strip() for x in anime_map.get(answer, []) if str(x).strip()]
        answer_specific = [x for x in answer_specific if x not in name_like]
        candidates = answer_specific + generic_pool

        # Count/replace name-like hints from left to right, keep at most one.
        name_seen = 0
        for i, h in enumerate(hints):
            is_name = h in name_like
            if not is_name:
                continue
            if name_seen < keep_name_budget:
                name_seen += 1
                continue

            replacement = None
            for cand in candidates:
                if cand in used:
                    continue
                if cand in META_TERMS:
                    continue
                if cand in name_like:
                    continue
                if has_overlap(answer, cand):
                    continue
                if detect_cross_domain("动漫", cand):
                    continue
                replacement = cand
                break

            if replacement is None:
                # Safe fallback non-name token.
                replacement = "角色互动"
                if replacement in used or has_overlap(answer, replacement):
                    replacement = "情节推进"

            used.discard(h)
            used.add(replacement)
            new_hints[i] = replacement
            changed += 1
            local_changed = True

        # Final pass: clean accidental meta/cross-domain/overlap in replaced slots.
        for i, h in enumerate(new_hints):
            if h in META_TERMS or has_overlap(answer, h) or detect_cross_domain("动漫", h):
                for cand in candidates:
                    if cand in used:
                        continue
                    if cand in META_TERMS or cand in name_like:
                        continue
                    if has_overlap(answer, cand):
                        continue
                    if detect_cross_domain("动漫", cand):
                        continue
                    used.discard(new_hints[i])
                    used.add(cand)
                    new_hints[i] = cand
                    local_changed = True
                    break

        # Postpone the remaining name token to slots 5-7 when possible.
        name_positions = [i for i, h in enumerate(new_hints) if h in name_like]
        if len(name_positions) == 1 and name_positions[0] < 4:
            src = name_positions[0]
            dst = None
            for j in [4, 5, 6]:
                if new_hints[j] not in name_like:
                    dst = j
                    break
            if dst is not None:
                new_hints[src], new_hints[dst] = new_hints[dst], new_hints[src]
                local_changed = True
                moved_name_to_late_slots += 1

        if local_changed and new_hints != hints:
            item["hints"] = new_hints
            touched_items += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "category": "动漫",
        "touched_items": touched_items,
        "replaced_name_tokens": changed,
        "moved_name_to_late_slots": moved_name_to_late_slots,
        "apply": bool(args.apply),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
