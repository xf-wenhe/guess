from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
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


RANGE_RE = re.compile(r"^\s*(\d{1,3})\s*-\s*(\d{1,3})\s*$")


@dataclass
class CheckedRow:
    row: dict[str, str]
    pair_key: tuple[str, str]
    label_key: tuple[str, str, str]
    source_tier: str
    sample_weight: float
    reasons: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight noise guard for training CSV")
    parser.add_argument(
        "--input",
        default="data/semantic_scoring_user_input_template_with_relabels_ab_applied_v1.csv",
    )
    parser.add_argument(
        "--out-clean",
        default="data/semantic_scoring_user_input_template_with_relabels_ab_applied_v1_clean.csv",
    )
    parser.add_argument(
        "--out-weighted",
        default="data/semantic_scoring_user_input_template_with_relabels_ab_applied_v1_weighted.csv",
    )
    parser.add_argument(
        "--out-quarantine",
        default="tmp/training_noise_guard_v1_quarantine.csv",
    )
    parser.add_argument(
        "--out-report",
        default="tmp/training_noise_guard_v1_report.json",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def parse_score(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        score = float(text)
    except ValueError:
        return None
    return score


def parse_expected_range(raw: str) -> tuple[float, float] | None:
    match = RANGE_RE.match((raw or "").strip())
    if not match:
        return None
    left = float(match.group(1))
    right = float(match.group(2))
    if left > right:
        return None
    if left < 0 or right > 100:
        return None
    return left, right


def infer_source_tier_and_weight(reviewer: str) -> tuple[str, float]:
    text = (reviewer or "").strip().lower()
    if not text:
        return "unknown", 0.50
    if "xuanheng" in text or "manual" in text or "human" in text:
        return "human", 1.00
    if "suggested_relabel_ab_v1" in text:
        return "auto_relabel", 0.80
    if "hard_negative_miner_v1" in text:
        return "auto_miner", 0.55
    return "auto_other", 0.60


def build_checked_rows(rows: list[dict[str, str]]) -> list[CheckedRow]:
    checked: list[CheckedRow] = []
    for src_row in rows:
        row = {field: (src_row.get(field) or "").strip() for field in BASE_FIELDS}
        pair_key = (row["answer"], row["user_input"])
        label_key = (row["relation_tag"], row["expected_range"], row["score_0_100"])
        tier, weight = infer_source_tier_and_weight(row["reviewer"])
        reasons: list[str] = []

        if not row["answer"] or not row["user_input"]:
            reasons.append("missing_pair_text")
        if not row["relation_tag"]:
            reasons.append("missing_relation_tag")

        score = parse_score(row["score_0_100"])
        if score is None:
            reasons.append("invalid_score")
        elif score < 0 or score > 100:
            reasons.append("score_out_of_bounds")

        parsed_range = parse_expected_range(row["expected_range"])
        if parsed_range is None:
            reasons.append("invalid_expected_range")
        elif score is not None:
            left, right = parsed_range
            if score < left or score > right:
                reasons.append("score_outside_expected_range")

        if row["answer"] and row["user_input"] and row["answer"] == row["user_input"]:
            if score is None or score < 95:
                reasons.append("self_pair_low_score")

        checked.append(
            CheckedRow(
                row=row,
                pair_key=pair_key,
                label_key=label_key,
                source_tier=tier,
                sample_weight=weight,
                reasons=reasons,
            )
        )
    return checked


def pick_better_row(left: CheckedRow, right: CheckedRow) -> CheckedRow:
    if left.sample_weight != right.sample_weight:
        return left if left.sample_weight > right.sample_weight else right
    left_score = parse_score(left.row["score_0_100"]) or -1
    right_score = parse_score(right.row["score_0_100"]) or -1
    if left_score != right_score:
        return left if left_score > right_score else right
    return left


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    raw_rows = read_rows(input_path)
    checked = build_checked_rows(raw_rows)

    by_pair: dict[tuple[str, str], list[CheckedRow]] = {}
    for item in checked:
        by_pair.setdefault(item.pair_key, []).append(item)

    conflict_pairs = 0
    for pair_rows in by_pair.values():
        label_set = {item.label_key for item in pair_rows}
        if len(label_set) > 1:
            conflict_pairs += 1
            for item in pair_rows:
                item.reasons.append("pair_label_conflict")

    deduped: dict[tuple[str, str], CheckedRow] = {}
    for pair_key, pair_rows in by_pair.items():
        best = pair_rows[0]
        for item in pair_rows[1:]:
            best = pick_better_row(best, item)
        deduped[pair_key] = best

    quarantine_rows: list[dict[str, str]] = []
    clean_rows: list[dict[str, str]] = []
    weighted_rows: list[dict[str, str]] = []
    reason_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}

    for pair_key in sorted(deduped.keys()):
        item = deduped[pair_key]
        tier_counts[item.source_tier] = tier_counts.get(item.source_tier, 0) + 1

        unique_reasons = sorted(set(item.reasons))
        for reason in unique_reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        if unique_reasons:
            quarantine_row = dict(item.row)
            quarantine_row["noise_reasons"] = ";".join(unique_reasons)
            quarantine_rows.append(quarantine_row)
            continue

        clean_rows.append(dict(item.row))
        weighted_row = dict(item.row)
        weighted_row["source_tier"] = item.source_tier
        weighted_row["sample_weight"] = f"{item.sample_weight:.2f}"
        weighted_row["noise_reasons"] = ""
        weighted_rows.append(weighted_row)

    for idx, row in enumerate(clean_rows, start=1):
        row["id"] = str(idx)
    for idx, row in enumerate(weighted_rows, start=1):
        row["id"] = str(idx)
    for idx, row in enumerate(quarantine_rows, start=1):
        row["id"] = str(idx)

    clean_path = Path(args.out_clean)
    weighted_path = Path(args.out_weighted)
    quarantine_path = Path(args.out_quarantine)
    report_path = Path(args.out_report)

    write_csv(clean_path, BASE_FIELDS, clean_rows)
    write_csv(weighted_path, BASE_FIELDS + ["source_tier", "sample_weight", "noise_reasons"], weighted_rows)
    write_csv(quarantine_path, BASE_FIELDS + ["noise_reasons"], quarantine_rows)

    report = {
        "input_rows": len(raw_rows),
        "deduped_pairs": len(deduped),
        "clean_rows": len(clean_rows),
        "quarantine_rows": len(quarantine_rows),
        "conflict_pairs": conflict_pairs,
        "reason_counts": reason_counts,
        "source_tier_counts": tier_counts,
        "input": str(input_path),
        "out_clean": str(clean_path),
        "out_weighted": str(weighted_path),
        "out_quarantine": str(quarantine_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
