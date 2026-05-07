from __future__ import annotations

import json
from pathlib import Path

MAP_PATH = Path("data/food_hint_style_map_v2.json")


def load_food_map() -> dict[str, list[str]]:
    raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return {str(key): [str(v) for v in value[:7]] for key, value in raw.items()}


def main() -> None:
    p = Path("assets/puzzles.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    food_map = load_food_map()

    changed = 0
    total = 0
    missing_answers: list[str] = []
    for it in data:
        if it.get("category") != "美食":
            continue
        total += 1
        answer = str(it.get("answer", "")).strip()
        target = food_map.get(answer)
        if not target:
            missing_answers.append(answer)
            continue
        if (it.get("hints") or [])[:7] != target:
            it["hints"] = target[:]
            changed += 1

    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "category": "美食",
                "total": total,
                "mapped_items": len(food_map),
                "changed_items": changed,
                "missing_answers": missing_answers,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
