from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_fail_answers(details_path: Path) -> list[str]:
    details = json.loads(details_path.read_text(encoding="utf-8"))
    fail = [str(x.get("answer", "")).strip() for x in details if not bool(x.get("pass"))]
    out: list[str] = []
    seen: set[str] = set()
    for x in fail:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate human anchor fill template for anime failures")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--details", default="tmp/post_remove_daily_generic_protected_guess/anime_guessability_v1_details.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--out", default="tmp/anime_human_anchor_template_v1.csv")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    fail_answers = set(load_fail_answers(Path(args.details)))

    anime_rows = []
    seen_answers: set[str] = set()
    for it in data:
        if it.get("category") != "动漫":
            continue
        answer = str(it.get("answer", "")).strip()
        if not answer or answer not in fail_answers:
            continue
        if answer in seen_answers:
            continue
        seen_answers.add(answer)
        cur = [str(x).strip() for x in (it.get("hints") or [])[:7]]
        base = [str(x).strip() for x in mapping.get(answer, [])[:7]]
        anime_rows.append((answer, cur, base))

    anime_rows.sort(key=lambda x: x[0])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "answer",
        "current_hints",
        "base_map_hints",
        "strong_anchor_1",
        "strong_anchor_2",
        "strong_anchor_3",
        "strong_anchor_4",
        "strong_anchor_5",
        "forbidden_1",
        "forbidden_2",
        "forbidden_3",
        "notes",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for answer, cur, base in anime_rows:
            writer.writerow(
                {
                    "answer": answer,
                    "current_hints": " | ".join(cur),
                    "base_map_hints": " | ".join(base),
                    "strong_anchor_1": "",
                    "strong_anchor_2": "",
                    "strong_anchor_3": "",
                    "strong_anchor_4": "",
                    "strong_anchor_5": "",
                    "forbidden_1": "",
                    "forbidden_2": "",
                    "forbidden_3": "",
                    "notes": "",
                }
            )

    print(
        json.dumps(
            {
                "total_fail_answers": len(fail_answers),
                "written_rows": len(anime_rows),
                "output": str(out_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
