from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def clean_token(x: str) -> str:
    return str(x).strip()


def split_hint_blob(blob: str) -> list[str]:
    parts = [clean_token(x) for x in str(blob).split("|")]
    return [x for x in parts if x]


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge human anchor template into anime guess master map")
    parser.add_argument("--template", default="tmp/anime_human_anchor_template_v1.csv")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--apply-map", action="store_true")
    parser.add_argument("--apply-puzzles", action="store_true")
    parser.add_argument("--out-map", default="tmp/anime_guess_master_map_v1.human_patch.json")
    parser.add_argument("--out-report", default="tmp/anime_human_anchor_merge_v1_report.json")
    args = parser.parse_args()

    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    rows = list(csv.DictReader(Path(args.template).open("r", encoding="utf-8")))

    touched: list[str] = []
    skipped: list[str] = []
    forbidden_map: dict[str, list[str]] = {}

    new_mapping = dict(mapping)
    for row in rows:
        answer = clean_token(row.get("answer", ""))
        if not answer:
            continue

        anchors = [
            clean_token(row.get("strong_anchor_1", "")),
            clean_token(row.get("strong_anchor_2", "")),
            clean_token(row.get("strong_anchor_3", "")),
            clean_token(row.get("strong_anchor_4", "")),
            clean_token(row.get("strong_anchor_5", "")),
        ]
        anchors = [x for x in anchors if x]

        forbid = [
            clean_token(row.get("forbidden_1", "")),
            clean_token(row.get("forbidden_2", "")),
            clean_token(row.get("forbidden_3", "")),
        ]
        forbid = [x for x in forbid if x]
        forbidden_map[answer] = forbid

        if len(anchors) < 3:
            skipped.append(answer)
            continue

        base = [clean_token(x) for x in new_mapping.get(answer, [])[:7]]
        if not base:
            base = split_hint_blob(row.get("current_hints", ""))[:7]
        if not base:
            skipped.append(answer)
            continue

        merged = []
        for x in [*anchors, *base]:
            if x and x not in merged and x not in forbid:
                merged.append(x)
            if len(merged) >= 7:
                break

        if len(merged) < 7:
            skipped.append(answer)
            continue

        new_mapping[answer] = merged[:7]
        touched.append(answer)

    out_map = Path(args.out_map)
    out_map.parent.mkdir(parents=True, exist_ok=True)
    out_map.write_text(json.dumps(new_mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.apply_map:
        Path(args.map).write_text(json.dumps(new_mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    puzzles_changed = 0
    if args.apply_puzzles:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        for it in data:
            if it.get("category") != "动漫":
                continue
            ans = clean_token(it.get("answer", ""))
            target = new_mapping.get(ans)
            if not target:
                continue
            cur = [clean_token(x) for x in (it.get("hints") or [])[:7]]
            if cur != target[:7]:
                it["hints"] = target[:7]
                puzzles_changed += 1
        Path(args.input).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "template": args.template,
        "total_rows": len(rows),
        "touched_answers": sorted(set(touched)),
        "touched_count": len(set(touched)),
        "skipped_answers": sorted(set(skipped)),
        "skipped_count": len(set(skipped)),
        "puzzles_changed": puzzles_changed,
        "out_map": str(out_map),
        "applied_map": bool(args.apply_map),
        "applied_puzzles": bool(args.apply_puzzles),
    }

    out_report = Path(args.out_report)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
