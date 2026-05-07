from __future__ import annotations

import argparse
import json
from pathlib import Path

from hint_quality_v29_common import (
    dedupe_keep_order,
    is_meta_hint,
    normalize_hint,
    strip_template_suffix,
)

CATEGORY_CONFIG = {
    "美食": {
        "base": ["饮食主题", "食材处理", "烹饪方式"],
        "keywords": ["烤", "炸", "煮", "蒸", "炖", "辣", "甜", "香", "奶", "米", "面", "汤", "卷", "饼"],
        "fallback": ["口感层次", "风味识别", "常见吃法", "出餐场景"],
    },
    "动漫": {
        "base": ["虚构作品", "角色叙事", "世界设定"],
        "keywords": ["角色", "战斗", "冒险", "侦探", "校园", "热血", "连载", "番剧", "漫画", "主线", "反派", "羁绊"],
        "fallback": ["剧情推进", "关键冲突", "人物关系", "经典桥段"],
    },
}

LOW_INFO_WORDS = {
    "一个人",
    "传统",
    "童年",
    "古风",
    "深渊",
    "雨天",
    "目的地",
    "巨人",
    "天才",
    "洪水",
}


def clean_hint(text: str, answer: str) -> str:
    out = strip_template_suffix(normalize_hint(text))
    if not out or out == answer:
        return ""
    bad, _ = is_meta_hint(out)
    if bad:
        return ""
    if out in LOW_INFO_WORDS:
        return ""
    if len(out) < 2 or len(out) > 10:
        return ""
    return out


def pick_tail(category: str, answer: str, old_hints: list[str]) -> list[str]:
    cfg = CATEGORY_CONFIG[category]
    keywords = cfg["keywords"]

    scored: list[tuple[int, str]] = []
    for hint in old_hints:
        h = clean_hint(hint, answer)
        if not h:
            continue
        score = 0
        for kw in keywords:
            if kw in h:
                score += 2
        score += min(len(set(h).intersection(set(answer))), 2)
        if h.endswith("语境") or h.endswith("特征"):
            score -= 5
        scored.append((score, h))

    scored.sort(key=lambda x: (-x[0], x[1]))
    selected = dedupe_keep_order([h for _, h in scored])

    # Keep high-signal tails only.
    selected = selected[:4]
    for token in cfg["fallback"]:
        if token not in selected and token != answer:
            selected.append(token)
        if len(selected) >= 4:
            break
    return selected[:4]


def run_rewrite(input_path: Path, out_dir: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    changed = 0
    touched: dict[str, list[str]] = {"美食": [], "动漫": []}

    out_data = []
    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        new_item = dict(item)

        if category in CATEGORY_CONFIG and answer:
            base = CATEGORY_CONFIG[category]["base"]
            old_hints = [normalize_hint(h) for h in (item.get("hints") or []) if normalize_hint(h)]
            tail = pick_tail(category, answer, old_hints)
            new_hints = base + tail
            old_first7 = old_hints[:7]
            new_item["hints"] = new_hints
            if new_hints != old_first7:
                changed += 1
                touched[category].append(answer)

        out_data.append(new_item)

    output_text = json.dumps(out_data, ensure_ascii=False, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "puzzles.food_anime_rewrite.v29.json"
    report_path = out_dir / "hints_food_anime_rewrite_v29_report.json"

    snapshot_path.write_text(output_text, encoding="utf-8")
    if apply:
        input_path.write_text(output_text, encoding="utf-8")

    report = {
        "input": str(input_path),
        "snapshot": str(snapshot_path),
        "apply": apply,
        "changed_items": changed,
        "food_answers": sorted(set(touched["美食"])),
        "anime_answers": sorted(set(touched["动漫"])),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "report": report,
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite food+anime hints sample v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true", help="overwrite input file")
    args = parser.parse_args()

    result = run_rewrite(Path(args.input), Path(args.out_dir), apply=args.apply)
    report = result["report"]
    print(
        "changed_items={changed_items} food={food} anime={anime} apply={apply}".format(
            changed_items=report["changed_items"],
            food=len(report["food_answers"]),
            anime=len(report["anime_answers"]),
            apply=report["apply"],
        )
    )
    print(f"report={result['report_path']}")


if __name__ == "__main__":
    main()
