from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDNAMES = [
    "id",
    "answer",
    "user_input",
    "answer_category",
    "input_category_guess",
    "relation_tag",
    "expected_range",
    "score_0_100",
    "reason",
    "reviewer",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def to_training_row(row: dict[str, str]) -> dict[str, str]:
    return {field: (row.get(field) or "").strip() for field in FIELDNAMES}


def pair_key(row: dict[str, str]) -> tuple[str, str]:
    return ((row.get("answer") or "").strip(), (row.get("user_input") or "").strip())


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge relabel candidates into training csv with pair-level override")
    parser.add_argument("--base", default="data/semantic_scoring_user_input_template.csv")
    parser.add_argument("--relabel", default="data/hard_negatives_relabel_candidates_v1.csv")
    parser.add_argument("--out", default="data/semantic_scoring_user_input_template_with_relabels_v1.csv")
    parser.add_argument("--out-relabel-only", default="data/hard_negatives_relabel_applied_v1.csv")
    args = parser.parse_args()

    base_path = Path(args.base)
    relabel_path = Path(args.relabel)

    base_rows = [to_training_row(row) for row in read_rows(base_path)]
    relabel_rows = [to_training_row(row) for row in read_rows(relabel_path)]

    base_map: dict[tuple[str, str], dict[str, str]] = {}
    for row in base_rows:
        key = pair_key(row)
        if not key[0] or not key[1]:
            continue
        base_map[key] = row

    relabel_map: dict[tuple[str, str], dict[str, str]] = {}
    for row in relabel_rows:
        key = pair_key(row)
        if not key[0] or not key[1]:
            continue
        relabel_map[key] = row

    replaced = 0
    added = 0
    for key, row in relabel_map.items():
        if key in base_map:
            replaced += 1
        else:
            added += 1
        base_map[key] = row

    merged = list(base_map.values())
    merged.sort(key=lambda r: (r["answer"], r["user_input"]))
    for idx, row in enumerate(merged, start=1):
        row["id"] = str(idx)

    relabel_only = list(relabel_map.values())
    relabel_only.sort(key=lambda r: (r["answer"], r["user_input"]))
    for idx, row in enumerate(relabel_only, start=1):
        row["id"] = str(idx)

    out_path = Path(args.out)
    out_relabel_only_path = Path(args.out_relabel_only)
    write_rows(out_path, merged)
    write_rows(out_relabel_only_path, relabel_only)

    summary = {
        "base_rows": len(base_rows),
        "relabel_rows": len(relabel_rows),
        "relabel_unique_pairs": len(relabel_map),
        "replaced_pairs": replaced,
        "added_pairs": added,
        "merged_rows": len(merged),
        "out": str(out_path),
        "out_relabel_only": str(out_relabel_only_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
