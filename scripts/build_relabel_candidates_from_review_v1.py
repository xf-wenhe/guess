from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


BASE_FIELDS = [
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

OUT_FIELDS = BASE_FIELDS + [
    "qc_status",
    "qc_reason",
    "qc_calibrated_score",
    "qc_shared_chars",
    "relabel_bucket",
    "suggested_relation_tag",
    "suggested_expected_range",
    "suggested_score_0_100",
    "relabel_note",
]


def bucket_and_suggestion(cal_score: float) -> tuple[str, str, str, str]:
    if cal_score >= 80:
        return ("A_80_100", "near_synonym_high", "75-90", "82")
    if cal_score >= 65:
        return ("B_65_79", "related_mid", "60-75", "68")
    if cal_score >= 50:
        return ("C_50_64", "related_mid", "45-60", "55")
    if cal_score >= 35:
        return ("D_35_49", "related_low", "30-45", "40")
    return ("E_0_34", "hard_negative_low", "0-25", "15")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build relabel candidate set from reviewed hard negatives")
    parser.add_argument(
        "--reviewed",
        default="data/hard_negatives_from_guessability_v1_reviewed.csv",
        help="input reviewed csv",
    )
    parser.add_argument(
        "--out",
        default="data/hard_negatives_relabel_candidates_v1.csv",
        help="output relabel candidates csv",
    )
    parser.add_argument(
        "--out-buckets-dir",
        default="tmp/hard_negatives_relabel_buckets_v1",
        help="directory to write per-bucket files",
    )
    args = parser.parse_args()

    reviewed_path = Path(args.reviewed)
    if not reviewed_path.exists():
        raise SystemExit(f"missing reviewed csv: {reviewed_path}")

    rows: list[dict[str, str]] = []
    with reviewed_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("qc_status") or "").strip() != "reject":
                continue
            try:
                cal_score = float((row.get("qc_calibrated_score") or "").strip())
            except ValueError:
                continue

            bucket, tag, exp_range, suggested_score = bucket_and_suggestion(cal_score)
            enriched = {k: (row.get(k) or "").strip() for k in OUT_FIELDS if k in row}
            for field in OUT_FIELDS:
                if field not in enriched:
                    enriched[field] = ""

            enriched["relabel_bucket"] = bucket
            enriched["suggested_relation_tag"] = tag
            enriched["suggested_expected_range"] = exp_range
            enriched["suggested_score_0_100"] = suggested_score
            enriched["relabel_note"] = "人工确认：是否应从 hard_negative_low 上调"
            rows.append(enriched)

    # Stable ordering: hardest/highest score first for fastest value from manual labeling.
    rows.sort(key=lambda r: float(r.get("qc_calibrated_score") or 0.0), reverse=True)
    for i, row in enumerate(rows, start=1):
        row["id"] = str(i)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    bucket_dir = Path(args.out_buckets_dir)
    bucket_dir.mkdir(parents=True, exist_ok=True)
    bucket_rows: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        bucket_rows.setdefault(row["relabel_bucket"], []).append(row)

    for bucket, items in bucket_rows.items():
        bucket_path = bucket_dir / f"{bucket}.csv"
        with bucket_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
            writer.writeheader()
            writer.writerows(items)

    summary = {
        "reviewed": str(reviewed_path),
        "out": str(out_path),
        "rows": len(rows),
        "bucket_counts": {bucket: len(items) for bucket, items in sorted(bucket_rows.items())},
        "bucket_dir": str(bucket_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
