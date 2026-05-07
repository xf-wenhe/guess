from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def range_for_score(score: float) -> str:
    center = int(round(score))
    left = max(0, center - 5)
    right = min(100, center + 5)
    return f"{left}-{right}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix expected_range based on score only")
    parser.add_argument("--input", default="data/semantic_scoring_user_input_template_with_relabels_ab_applied_v1.csv")
    parser.add_argument("--out", default="data/semantic_scoring_user_input_template_with_relabels_ab_applied_v1_rangefixed.csv")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out)

    with in_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
        if not rows:
            raise SystemExit("empty input")
        fieldnames = list(rows[0].keys())

    updated = 0
    invalid_score = 0
    for row in rows:
        raw = (row.get("score_0_100") or "").strip()
        try:
            score = float(raw)
        except ValueError:
            invalid_score += 1
            continue
        new_range = range_for_score(score)
        old_range = (row.get("expected_range") or "").strip()
        if old_range != new_range:
            row["expected_range"] = new_range
            updated += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        json.dumps(
            {
                "input": str(in_path),
                "out": str(out_path),
                "rows": len(rows),
                "updated_expected_range": updated,
                "invalid_score_rows": invalid_score,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
