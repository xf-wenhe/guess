from __future__ import annotations

import argparse
import json
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply anime guess-master hint map v1")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))

    total = 0
    changed = 0
    missing: list[str] = []
    invalid: list[str] = []

    for item in data:
        if item.get("category") != "动漫":
            continue
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue
        total += 1

        if answer == "名侦探柯南":
            continue

        target = mapping.get(answer)
        if not target:
            missing.append(answer)
            continue

        hints = [str(x).strip() for x in target[:7]]
        if len(hints) != 7 or len(set(hints)) != 7:
            invalid.append(answer)
            continue
        if any(h in META_TERMS for h in hints):
            invalid.append(answer)
            continue
        if any(has_overlap(answer, h) for h in hints):
            invalid.append(answer)
            continue

        if (item.get("hints") or [])[:7] != hints:
            item["hints"] = hints
            changed += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "category": "动漫",
                "total": total,
                "mapped": len(mapping),
                "changed_items": changed,
                "missing_answers": sorted(set(missing)),
                "invalid_answers": sorted(set(invalid)),
                "apply": bool(args.apply),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
