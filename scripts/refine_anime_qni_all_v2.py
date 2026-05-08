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

PLACEHOLDER_TERMS = {
    "系列作品",
    "番剧作品",
    "虚构故事",
    "长篇连载",
    "观众熟知",
    "角色互动",
    "连载作品",
    "人物关系",
    "核心锚点",
    "地域舞台",
}

# Keep Conan unchanged as required by the user.
PROTECTED_ANSWERS = {"名侦探柯南"}

# User-confirmed high-precision versions.
OVERRIDES = {
    "樱桃小丸子": ["日本", "昭和", "家庭日常", "班级生活", "清水市", "三年四班", "友藏爷爷"],
    "蜡笔小新": ["日本", "昭和", "家庭日常", "班级生活", "春日部", "双叶幼稚园", "野原一家"],
}

FALLBACK = [
    "日本",
    "动画作品",
    "角色群像",
    "剧情推进",
    "世界设定",
    "核心道具",
    "关键锚点",
]


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def is_valid(category: str, answer: str, hint: str, used: set[str]) -> bool:
    if not hint or hint in used:
        return False
    if hint in META_TERMS:
        return False
    if has_overlap(answer, hint):
        return False
    if detect_cross_domain(category, hint):
        return False
    return True


def normalize7(hints: list[str]) -> list[str]:
    hs = [str(x).strip() for x in hints[:7]]
    if len(hs) < 7:
        hs.extend([""] * (7 - len(hs)))
    return hs[:7]


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine all anime hints to QNI-style (exclude Conan)")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))
    anime_map = json.loads(Path(args.map).read_text(encoding="utf-8"))

    total_anime = 0
    changed_items = 0
    missing_map: list[str] = []
    placeholder_cleaned = 0

    for item in data:
        if item.get("category") != "动漫":
            continue
        total_anime += 1

        answer = str(item.get("answer", "")).strip()
        if not answer or answer in PROTECTED_ANSWERS:
            continue

        current = normalize7(item.get("hints") or [])
        used: set[str] = set()

        if answer in OVERRIDES:
            base = normalize7(OVERRIDES[answer])
        else:
            mapped = anime_map.get(answer)
            if not mapped:
                missing_map.append(answer)
                base = current[:]
            else:
                base = normalize7(mapped)

        new_hints = base[:]

        # Pass 1: enforce validity and uniqueness.
        for i, h in enumerate(new_hints):
            if is_valid("动漫", answer, h, used):
                used.add(h)
                continue

            replaced = None
            candidates = [str(x).strip() for x in anime_map.get(answer, [])] + FALLBACK
            for cand in candidates:
                if is_valid("动漫", answer, cand, used):
                    replaced = cand
                    break

            if replaced is None:
                replaced = "剧情线索"
                if not is_valid("动漫", answer, replaced, used):
                    replaced = "情节推进"

            if h in PLACEHOLDER_TERMS:
                placeholder_cleaned += 1
            new_hints[i] = replaced
            used.add(replaced)

        # Pass 2: placeholder cleanup for any leftovers.
        for i, h in enumerate(new_hints):
            if h not in PLACEHOLDER_TERMS:
                continue
            replacement = None
            for cand in [str(x).strip() for x in anime_map.get(answer, [])] + FALLBACK:
                if is_valid("动漫", answer, cand, set(new_hints) - {h}):
                    replacement = cand
                    break
            if replacement:
                new_hints[i] = replacement
                placeholder_cleaned += 1

        if current != new_hints:
            item["hints"] = new_hints
            changed_items += 1

    if args.apply:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "category": "动漫",
        "total_anime": total_anime,
        "changed_items": changed_items,
        "missing_map": sorted(set(missing_map)),
        "placeholder_cleaned": placeholder_cleaned,
        "apply": bool(args.apply),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
