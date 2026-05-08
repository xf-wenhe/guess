from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_buckets(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply suggested relabel values for selected buckets")
    parser.add_argument("--input", default="data/hard_negatives_relabel_candidates_v1.csv")
    parser.add_argument("--out", default="data/hard_negatives_relabel_candidates_ab_applied_v1.csv")
    parser.add_argument("--buckets", default="A_80_100,B_65_79")
    parser.add_argument("--reviewer", default="suggested_relabel_ab_v1")
    args = parser.parse_args()

    input_path = Path(args.input)
    rows = read_rows(input_path)
    if not rows:
        raise SystemExit("no rows found")

    fieldnames = list(rows[0].keys())
    target_buckets = parse_buckets(args.buckets)

    updated = 0
    for row in rows:
        bucket = (row.get("relabel_bucket") or "").strip()
        if bucket not in target_buckets:
            continue
        row["relation_tag"] = (row.get("suggested_relation_tag") or row.get("relation_tag") or "").strip()
        row["expected_range"] = (row.get("suggested_expected_range") or row.get("expected_range") or "").strip()
        row["score_0_100"] = (row.get("suggested_score_0_100") or row.get("score_0_100") or "").strip()
        row["reviewer"] = args.reviewer
        note = (row.get("relabel_note") or "").strip()
        prefix = f"AUTO_APPLIED:{bucket}"
        row["relabel_note"] = prefix if not note else f"{prefix}; {note}"
        updated += 1

    out_path = Path(args.out)
    write_rows(out_path, fieldnames, rows)

    print(
        json.dumps(
            {
                "input": str(input_path),
                "out": str(out_path),
                "target_buckets": sorted(target_buckets),
                "updated_rows": updated,
                "total_rows": len(rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
