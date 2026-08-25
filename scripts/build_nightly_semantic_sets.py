from __future__ import annotations

import csv
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from build_v26_gold_and_unsup import build_unsup_pairs_from_puzzles, load_manual_gold


PUZZLES_JSON = Path(os.getenv("SEM_PUZZLES_JSON", "assets/puzzles.json"))
MANUAL_OVERRIDES = Path(os.getenv("SEM_MANUAL_OVERRIDES", "data/manual_similarity_overrides.json"))
BASE_TRAIN_CSV = Path(os.getenv("SEM_BASE_TRAIN_CSV", "data/train_v28c_balanced.csv"))
SCORED_CSV = Path(os.getenv("SEM_SCORED_CSV", "data/semantic_scoring_user_input_template.csv"))
SEED = int(os.getenv("SEM_SEED", "20260303"))

OUTPUT_TRAIN_CSV = Path(os.getenv("SEM_OUTPUT_TRAIN_CSV", ".nightly/data/gold/train_v28c_nightly.csv"))
OUTPUT_CALIB_CSV = Path(os.getenv("SEM_GOLD_CALIB_CSV", ".nightly/data/gold/gold_nightly_calib.csv"))
OUTPUT_EVAL_CSV = Path(os.getenv("SEM_GOLD_EVAL_CSV", ".nightly/data/gold/gold_nightly_eval.csv"))
OUTPUT_POOL_CSV = Path(os.getenv("SEM_GOLD_POOL_CSV", ".nightly/data/gold/gold_nightly_pool.csv"))
OUTPUT_UNSUP_JSONL = Path(os.getenv("SEM_UNSUP_PAIRS_JSONL", ".nightly/data/gold/unsupervised_pairs_v26.jsonl"))
OUTPUT_BUILD_STATS_JSON = os.getenv("SEM_BUILD_STATS_JSON", "").strip()

TARGET_GOLD_TOTAL = int(os.getenv("SEM_GOLD_TARGET_TOTAL", "1200"))
CALIB_RATIO = float(os.getenv("SEM_GOLD_CALIB_RATIO", "0.35"))
EVAL_RATIO = float(os.getenv("SEM_GOLD_EVAL_RATIO", "0.25"))
ANTONYM_CALIB_ANCHOR_TARGET = int(os.getenv("SEM_ANTONYM_CALIB_ANCHOR_TARGET", "9"))
ANTONYM_CALIB_ANCHOR_WEIGHT = float(os.getenv("SEM_ANTONYM_CALIB_ANCHOR_WEIGHT", "10.0"))
PRIORITY_ANTONYM_CALIB_ANCHOR_WEIGHT = float(
    os.getenv("SEM_PRIORITY_ANTONYM_CALIB_ANCHOR_WEIGHT", "13.0")
)
EVAL_TO_CALIB_ANCHOR_WEIGHT = float(
    os.getenv("SEM_EVAL_TO_CALIB_ANCHOR_WEIGHT", str(ANTONYM_CALIB_ANCHOR_WEIGHT))
)

DEFAULT_EXTRA_GOLD = [
    "data/semantic_error_review_template_v1.csv",
    "data/score_trace_review_candidates.csv",
    "data/nightly_worst_case_review_candidates.csv",
    "data/hard_negatives_relabel_applied_ab_v1.csv",
    "data/semantic_scoring_user_input_template_with_relabels_ab_applied_v1_rangefixed_weighted.csv",
]
DEFAULT_HOLDOUT = [
    "data/semantic_holdout_v1.csv",
]
DEFAULT_TRAIN_PATCH = [
    "data/semantic_train_patch_v1.csv",
]
EXTRA_GOLD_CSVS = [
    Path(p.strip())
    for p in os.getenv("SEM_EXTRA_GOLD_CSVS", ",".join(DEFAULT_EXTRA_GOLD)).split(",")
    if p.strip()
]
HOLDOUT_CSVS = [
    Path(p.strip())
    for p in os.getenv("SEM_HOLDOUT_CSVS", ",".join(DEFAULT_HOLDOUT)).split(",")
    if p.strip()
]
TRAIN_PATCH_CSVS = [
    Path(p.strip())
    for p in os.getenv("SEM_TRAIN_PATCH_CSVS", ",".join(DEFAULT_TRAIN_PATCH)).split(",")
    if p.strip()
]

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
    "sample_weight",
]

ANTONYM_TAGS = {
    "antonym_low",
    "antonym_mid",
    "antonym_or_conflict",
}
ANTONYM_SCORE = 50
ANTONYM_RANGE = "45-55"
ANTONYM_SAMPLE_WEIGHT = float(os.getenv("SEM_ANTONYM_SAMPLE_WEIGHT", "2.5"))
REQUIRED_ANTONYM_TRAIN_PATCH_ROWS = [
    ("高兴", "难过", "情感", "情感"),
    ("快乐", "悲伤", "情感", "情感"),
    ("欣喜", "郁闷", "情感", "情感"),
    ("胜利", "失败", "抽象", "抽象"),
    ("白天", "黑夜", "时间", "时间"),
    ("古代", "现代", "时间", "时间"),
    ("永恒", "瞬间", "抽象", "抽象"),
    ("智慧", "愚昧", "抽象", "抽象"),
]
PRIORITY_ANTONYM_CALIB_ANCHOR_PAIRS = [
    ("高兴", "难过"),
    ("高兴", "悲伤"),
    ("高兴", "伤心"),
    ("开心", "难过"),
    ("开心", "悲伤"),
    ("快乐", "难过"),
    ("胜利", "失败"),
    ("古代", "现代"),
    ("快乐", "悲伤"),
    ("白天", "黑夜"),
    ("欣喜", "郁闷"),
]
PRIORITY_ANTONYM_CALIB_ANCHOR_ORDER = {
    pair: idx for idx, pair in enumerate(PRIORITY_ANTONYM_CALIB_ANCHOR_PAIRS)
}
BOOSTED_PRIORITY_ANTONYM_CALIB_WEIGHT_PAIRS = {
    ("高兴", "悲伤"),
    ("高兴", "伤心"),
    ("开心", "难过"),
    ("开心", "悲伤"),
    ("快乐", "难过"),
    ("胜利", "失败"),
    ("古代", "现代"),
}
REQUIRED_HOLDOUT_FAMILY_PROXY_CALIB_PAIRS = {
    ("高兴", "伤心"),
    ("开心", "悲伤"),
    ("快乐", "难过"),
}
EVAL_TO_CALIB_TAGS = {
    tag.strip()
    for tag in os.getenv("SEM_EVAL_TO_CALIB_TAGS", "antonym_mid").split(",")
    if tag.strip()
}
EXCLUDED_REVIEWERS = {
    reviewer.strip().lower()
    for reviewer in os.getenv("SEM_EXCLUDED_REVIEWERS", "suggested_relabel_ab_v1").split(",")
    if reviewer.strip()
}


def score_bin(score: float) -> str:
    if score < 20:
        return "0-19"
    if score < 40:
        return "20-39"
    if score < 60:
        return "40-59"
    if score < 80:
        return "60-79"
    return "80-100"


def canonical_pair(answer: str, user_input: str) -> tuple[str, str]:
    return tuple(sorted((answer, user_input)))


def relation_for_score(score: int) -> str:
    if score >= 85:
        return "alias_synonym_high"
    if score >= 70:
        return "near_synonym_high"
    if score >= 50:
        return "related_mid"
    if score >= 30:
        return "related_low"
    return "hard_negative_low"


def range_for_score(score: int) -> str:
    left = max(0, score - 5)
    right = min(100, score + 5)
    return f"{left}-{right}"


def is_antonym_relation(relation_tag: str, reason: str) -> bool:
    tag = relation_tag.strip().lower()
    return tag in ANTONYM_TAGS or "反义" in reason


def required_antonym_train_patch_rows() -> list[dict]:
    rows = []
    for answer, user_input, answer_category, input_category in REQUIRED_ANTONYM_TRAIN_PATCH_ROWS:
        normalized = normalize_row(
            {
                "answer": answer,
                "user_input": user_input,
                "answer_category": answer_category,
                "input_category_guess": input_category,
                "relation_tag": "antonym_mid",
                "expected_range": ANTONYM_RANGE,
                "score_0_100": str(ANTONYM_SCORE),
                "reason": "required antonym regression patch; train as 50 percent semantic relatedness",
                "reviewer": "required_antonym_patch",
                "sample_weight": "4.0",
            },
            "required_antonym_patch",
        )
        if normalized is not None:
            rows.append(normalized)
    return rows


def normalize_row(row: dict, reviewer_fallback: str) -> Optional[dict]:
    answer = (row.get("answer") or "").strip()
    user_input = (row.get("user_input") or "").strip()
    score_raw = (
        row.get("score_0_100")
        or row.get("corrected_score")
        or row.get("qc_calibrated_score")
        or ""
    )
    if not answer or not user_input or score_raw == "":
        return None
    try:
        score = int(round(float(score_raw)))
    except ValueError:
        return None
    if not (0 <= score <= 100):
        return None

    relation_tag = (
        row.get("relation_tag")
        or row.get("error_type")
        or relation_for_score(score)
    ).strip()
    reason = (
        row.get("reason")
        or row.get("why_wrong")
        or row.get("rationale")
        or reviewer_fallback
    ).strip()
    reviewer = (row.get("reviewer") or reviewer_fallback).strip()
    sample_weight = (row.get("sample_weight") or "1.0").strip()
    try:
        sample_weight_f = max(0.0, min(10.0, float(sample_weight)))
    except ValueError:
        sample_weight_f = 1.0

    if is_antonym_relation(relation_tag, reason):
        relation_tag = "antonym_mid"
        score = ANTONYM_SCORE
        expected_range = ANTONYM_RANGE
        sample_weight_f = max(sample_weight_f, ANTONYM_SAMPLE_WEIGHT)
    else:
        expected_range = (row.get("expected_range") or range_for_score(score)).strip()

    return {
        "id": "",
        "answer": answer,
        "user_input": user_input,
        "answer_category": (row.get("answer_category") or "").strip(),
        "input_category_guess": (row.get("input_category_guess") or "").strip(),
        "relation_tag": relation_tag or relation_for_score(score),
        "expected_range": expected_range,
        "score_0_100": str(score),
        "reason": reason[:120],
        "reviewer": reviewer,
        "sample_weight": f"{sample_weight_f:.4f}",
    }


def read_csv_rows(
    path: Path,
    reviewer_fallback: str,
    load_stats: Counter | None = None,
) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = []
        for row in csv.DictReader(file):
            reviewer_text = (row.get("reviewer") or reviewer_fallback).strip().lower()
            if reviewer_text in EXCLUDED_REVIEWERS:
                if load_stats is not None:
                    load_stats["excluded_reviewer_rows"] += 1
                    load_stats[f"excluded_reviewer::{reviewer_text}"] += 1
                continue
            review_status = (row.get("review_status") or "").strip().lower()
            if review_status and review_status not in {"approved", "merged"}:
                continue
            normalized = normalize_row(row, reviewer_fallback)
            if normalized is not None:
                rows.append(normalized)
        return rows


def dedupe(rows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = (row["answer"], row["user_input"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    for idx, row in enumerate(out, start=1):
        row["id"] = str(idx)
    return out


def pair_keys(rows: list[dict], *, symmetric: bool = False) -> set[tuple[str, str]]:
    keys = set()
    for row in rows:
        if symmetric:
            keys.add(canonical_pair(row["answer"], row["user_input"]))
        else:
            keys.add((row["answer"], row["user_input"]))
    return keys


def exclude_pairs(
    rows: list[dict],
    excluded: set[tuple[str, str]],
    *,
    symmetric: bool = False,
) -> list[dict]:
    if not excluded:
        return list(rows)
    filtered = []
    for row in rows:
        key = (
            canonical_pair(row["answer"], row["user_input"])
            if symmetric
            else (row["answer"], row["user_input"])
        )
        if key in excluded:
            continue
        filtered.append(row)
    return filtered


def stratified_trim(rows: list[dict], limit: int, seed: int) -> list[dict]:
    if limit <= 0 or len(rows) <= limit:
        return list(rows)
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for row in rows:
        buckets[score_bin(float(row["score_0_100"]))].append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    out = []
    bucket_names = sorted(buckets)
    while len(out) < limit and any(buckets.values()):
        for name in bucket_names:
            if buckets[name] and len(out) < limit:
                out.append(buckets[name].pop())
    rng.shuffle(out)
    return out


def split_train_calib_eval(rows: list[dict], seed: int) -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(seed)
    train = []
    calib = []
    eval_rows = []
    buckets = defaultdict(list)
    for row in rows:
        buckets[score_bin(float(row["score_0_100"]))].append(row)
    for bucket_rows in buckets.values():
        pair_groups: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in bucket_rows:
            pair_groups[canonical_pair(row["answer"], row["user_input"])].append(row)
        grouped_rows = list(pair_groups.values())
        rng.shuffle(grouped_rows)
        n_rows = len(bucket_rows)
        n_groups = len(grouped_rows)
        if n_groups == 1:
            train.extend(grouped_rows[0])
            continue
        if n_groups == 2:
            train.extend(grouped_rows[0])
            calib.extend(grouped_rows[1])
            continue
        n_calib = max(1, int(round(n_rows * CALIB_RATIO)))
        n_eval = max(1, int(round(n_rows * EVAL_RATIO)))
        if n_calib + n_eval >= n_rows:
            overflow = n_calib + n_eval - (n_rows - 1)
            reduce_eval = min(overflow, max(0, n_eval - 1))
            n_eval -= reduce_eval
            overflow -= reduce_eval
            n_calib = max(1, n_calib - overflow)
        calib_count = 0
        eval_count = 0
        groups_remaining = n_groups
        for group in grouped_rows:
            group_size = len(group)
            groups_remaining -= 1
            if calib_count < n_calib and groups_remaining >= 2:
                calib.extend(group)
                calib_count += group_size
                continue
            if eval_count < n_eval and groups_remaining >= 1:
                eval_rows.extend(group)
                eval_count += group_size
                continue
            train.extend(group)
    rng.shuffle(train)
    rng.shuffle(calib)
    rng.shuffle(eval_rows)
    return dedupe(train), dedupe(calib), dedupe(eval_rows)


def reserve_antonym_calibration_rows(train_patch_rows: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    if ANTONYM_CALIB_ANCHOR_TARGET <= 0:
        return list(train_patch_rows), []

    eligible = [
        row for row in train_patch_rows
        if row["relation_tag"] == "antonym_mid" and row["reviewer"] != "required_antonym_patch"
    ]
    if not eligible:
        return list(train_patch_rows), []

    rng = random.Random(seed + 97)
    reviewer_priority = {
        # Prioritize the newer curated opposite-pair patch first so calibration
        # sees the same antonym families that are currently failing regression.
        "nightly_patch_v2": 0,
        "nightly_patch_v1": 1,
    }
    shuffled = list(eligible)
    rng.shuffle(shuffled)
    shuffled.sort(
        key=lambda row: (
            PRIORITY_ANTONYM_CALIB_ANCHOR_ORDER.get((row["answer"], row["user_input"]), 999),
            reviewer_priority.get(row["reviewer"], 9),
            row["answer"],
            row["user_input"],
        )
    )
    selected_keys = {
        (row["answer"], row["user_input"])
        for row in shuffled[:ANTONYM_CALIB_ANCHOR_TARGET]
    }
    reserved = []
    for row in train_patch_rows:
        key = (row["answer"], row["user_input"])
        if key in selected_keys:
            # Keep the curated patch row in training and add a boosted mirror
            # into calibration so raw supervision and post-hoc calibration both
            # see the same opposite-pair families.
            reserved.append(boost_calibration_anchor_row(row, ANTONYM_CALIB_ANCHOR_WEIGHT))
    return dedupe(train_patch_rows), dedupe(reserved)


def calibration_anchor_weight_for_row(
    row: dict,
    default_weight: float,
) -> tuple[float, str, str]:
    key = (row["answer"], row["user_input"])
    target_weight = default_weight
    priority_anchor = "0"
    priority_weight = "0"
    if key in PRIORITY_ANTONYM_CALIB_ANCHOR_ORDER:
        priority_anchor = "1"
    if key in BOOSTED_PRIORITY_ANTONYM_CALIB_WEIGHT_PAIRS:
        target_weight = max(target_weight, PRIORITY_ANTONYM_CALIB_ANCHOR_WEIGHT)
        priority_weight = "1"
    return target_weight, priority_anchor, priority_weight


def boost_calibration_anchor_row(row: dict, default_weight: float) -> dict:
    reserved_row = dict(row)
    try:
        current_weight = float(reserved_row.get("sample_weight") or "1.0")
    except ValueError:
        current_weight = 1.0
    target_weight, priority_anchor, priority_weight = calibration_anchor_weight_for_row(
        reserved_row,
        default_weight,
    )
    reserved_row["sample_weight"] = f"{max(current_weight, target_weight):.4f}"
    reserved_row["_priority_antonym_calib_anchor"] = priority_anchor
    reserved_row["_priority_antonym_calib_weight"] = priority_weight
    return reserved_row


def reserve_tagged_gold_rows_for_calibration(
    supervised_gold_rows: list[dict],
    tags: set[str],
) -> tuple[list[dict], list[dict]]:
    if not tags:
        return dedupe(supervised_gold_rows), []

    reserved = []
    remaining = []
    for row in supervised_gold_rows:
        if row.get("relation_tag") in tags:
            reserved.append(boost_calibration_anchor_row(row, EVAL_TO_CALIB_ANCHOR_WEIGHT))
        else:
            remaining.append(row)
    return dedupe(remaining), dedupe(reserved)


def required_holdout_family_proxy_calibration_rows(
    holdout_keys: set[tuple[str, str]],
) -> list[dict]:
    if canonical_pair("高兴", "难过") not in holdout_keys:
        return []

    rows = []
    for answer, user_input in sorted(REQUIRED_HOLDOUT_FAMILY_PROXY_CALIB_PAIRS):
        normalized = normalize_row(
            {
                "answer": answer,
                "user_input": user_input,
                "answer_category": "情感",
                "input_category_guess": "情感",
                "relation_tag": "antonym_mid",
                "expected_range": ANTONYM_RANGE,
                "score_0_100": str(ANTONYM_SCORE),
                "reason": "required holdout-family antonym calibration proxy",
                "reviewer": "required_antonym_proxy_calib",
                "sample_weight": "4.0",
            },
            "required_antonym_proxy_calib",
        )
        if normalized is not None:
            rows.append(boost_calibration_anchor_row(normalized, ANTONYM_CALIB_ANCHOR_WEIGHT))
    return dedupe(rows)


def reroute_eval_rows_to_calib(
    calib_rows: list[dict],
    eval_rows: list[dict],
    tags: set[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    if not tags:
        return dedupe(calib_rows), dedupe(eval_rows), []
    moved_rows = [
        boost_calibration_anchor_row(row, EVAL_TO_CALIB_ANCHOR_WEIGHT)
        for row in eval_rows
        if row.get("relation_tag") in tags
    ]
    kept_eval_rows = [row for row in eval_rows if row.get("relation_tag") not in tags]
    merged_calib_rows = dedupe([*calib_rows, *moved_rows])
    return merged_calib_rows, dedupe(kept_eval_rows), dedupe(moved_rows)


def is_allowed_train_calib_overlap(train_row: dict, calib_row: dict) -> bool:
    if train_row.get("relation_tag") != "antonym_mid" or calib_row.get("relation_tag") != "antonym_mid":
        return False
    train_reviewer = (train_row.get("reviewer") or "").strip()
    calib_reviewer = (calib_row.get("reviewer") or "").strip()
    if not train_reviewer.startswith("nightly_patch") or train_reviewer != calib_reviewer:
        return False
    try:
        train_weight = float(train_row.get("sample_weight") or "1.0")
        calib_weight = float(calib_row.get("sample_weight") or "1.0")
    except ValueError:
        return False
    return calib_weight > train_weight


def validate_dataset_partition(
    train_rows: list[dict],
    calib_rows: list[dict],
    eval_rows: list[dict],
    holdout_rows: list[dict] | None = None,
) -> dict:
    train_map = {(row["answer"], row["user_input"]): row for row in train_rows}
    calib_map = {(row["answer"], row["user_input"]): row for row in calib_rows}
    eval_map = {(row["answer"], row["user_input"]): row for row in eval_rows}
    holdout_keys = pair_keys(holdout_rows or [], symmetric=True)

    eval_antonym_rows = [
        row for row in eval_rows if row.get("relation_tag") == "antonym_mid"
    ]
    eval_holdout_antonym_rows = [
        row
        for row in eval_antonym_rows
        if canonical_pair(row["answer"], row["user_input"]) in holdout_keys
    ]
    unexpected_eval_antonym_rows = [
        (row["answer"], row["user_input"])
        for row in eval_antonym_rows
        if canonical_pair(row["answer"], row["user_input"]) not in holdout_keys
    ]

    train_eval_exact_overlap = sorted(set(train_map) & set(eval_map))
    train_eval_symmetric_overlap = sorted(
        pair_keys(train_rows, symmetric=True) & pair_keys(eval_rows, symmetric=True)
    )
    eval_calib_exact_overlap = sorted(set(eval_map) & set(calib_map))
    eval_calib_symmetric_overlap = sorted(
        pair_keys(eval_rows, symmetric=True) & pair_keys(calib_rows, symmetric=True)
    )
    train_calib_symmetric_overlap = sorted(
        pair_keys(train_rows, symmetric=True) & pair_keys(calib_rows, symmetric=True)
    )
    train_rows_by_pair: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    calib_rows_by_pair: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in train_rows:
        train_rows_by_pair[canonical_pair(row["answer"], row["user_input"])].append(row)
    for row in calib_rows:
        calib_rows_by_pair[canonical_pair(row["answer"], row["user_input"])].append(row)
    unexpected_train_calib_symmetric_overlap = [
        pair
        for pair in train_calib_symmetric_overlap
        if not all(
            is_allowed_train_calib_overlap(train_row, calib_row)
            for train_row in train_rows_by_pair[pair]
            for calib_row in calib_rows_by_pair[pair]
        )
    ]
    train_calib_exact_overlap = sorted(set(train_map) & set(calib_map))
    unexpected_train_calib_exact_overlap = [
        pair
        for pair in train_calib_exact_overlap
        if not is_allowed_train_calib_overlap(train_map[pair], calib_map[pair])
    ]

    if (
        train_eval_exact_overlap
        or train_eval_symmetric_overlap
        or eval_calib_exact_overlap
        or eval_calib_symmetric_overlap
        or unexpected_train_calib_symmetric_overlap
        or unexpected_train_calib_exact_overlap
        or unexpected_eval_antonym_rows
    ):
        details = {
            "train_eval_exact_overlap": train_eval_exact_overlap[:10],
            "train_eval_symmetric_overlap": train_eval_symmetric_overlap[:10],
            "eval_calib_exact_overlap": eval_calib_exact_overlap[:10],
            "eval_calib_symmetric_overlap": eval_calib_symmetric_overlap[:10],
            "train_calib_symmetric_overlap": train_calib_symmetric_overlap[:10],
            "unexpected_train_calib_symmetric_overlap": unexpected_train_calib_symmetric_overlap[:10],
            "unexpected_train_calib_exact_overlap": unexpected_train_calib_exact_overlap[:10],
            "unexpected_eval_antonym_mid_rows": unexpected_eval_antonym_rows[:10],
        }
        raise SystemExit(
            "nightly train/calib/eval partition overlap detected: "
            + json.dumps(details, ensure_ascii=False)
        )

    return {
        "train_eval_exact_overlap": len(train_eval_exact_overlap),
        "train_eval_symmetric_overlap": len(train_eval_symmetric_overlap),
        "eval_calib_exact_overlap": len(eval_calib_exact_overlap),
        "eval_calib_symmetric_overlap": len(eval_calib_symmetric_overlap),
        "train_calib_symmetric_overlap": len(train_calib_symmetric_overlap),
        "unexpected_train_calib_symmetric_overlap": len(unexpected_train_calib_symmetric_overlap),
        "train_calib_exact_overlap": len(train_calib_exact_overlap),
        "allowed_train_calib_exact_overlap": len(train_calib_exact_overlap)
        - len(unexpected_train_calib_exact_overlap),
        "unexpected_train_calib_exact_overlap": len(unexpected_train_calib_exact_overlap),
        "eval_antonym_rows": len(eval_antonym_rows),
        "eval_holdout_antonym_rows": len(eval_holdout_antonym_rows),
        "eval_non_holdout_antonym_rows": len(unexpected_eval_antonym_rows),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    if not MANUAL_OVERRIDES.exists():
        raise SystemExit(f"missing file: {MANUAL_OVERRIDES}")
    if not PUZZLES_JSON.exists():
        raise SystemExit(f"missing file: {PUZZLES_JSON}")
    if not BASE_TRAIN_CSV.exists():
        raise SystemExit(f"missing file: {BASE_TRAIN_CSV}")

    manual_rows = [
        {**row, "sample_weight": "2.0000"}
        for row in load_manual_gold(MANUAL_OVERRIDES)
    ]
    for row in manual_rows:
        row.setdefault("sample_weight", "2.0000")

    load_stats: Counter[str] = Counter()
    supervised_gold_rows = []
    supervised_gold_rows.extend(normalize_row(row, "manual_gold") for row in manual_rows)
    supervised_gold_rows.extend(read_csv_rows(SCORED_CSV, "scored_user_input", load_stats))
    for path in EXTRA_GOLD_CSVS:
        supervised_gold_rows.extend(read_csv_rows(path, path.stem, load_stats))
    supervised_gold_rows = dedupe([row for row in supervised_gold_rows if row is not None])
    supervised_gold_rows = stratified_trim(supervised_gold_rows, TARGET_GOLD_TOTAL, SEED)

    holdout_rows = []
    for path in HOLDOUT_CSVS:
        holdout_rows.extend(read_csv_rows(path, path.stem, load_stats))
    holdout_rows = dedupe(holdout_rows)
    holdout_keys = pair_keys(holdout_rows, symmetric=True)
    supervised_gold_rows = dedupe(exclude_pairs(supervised_gold_rows, holdout_keys, symmetric=True))

    base_train_rows = read_csv_rows(BASE_TRAIN_CSV, "base_train", load_stats)
    train_patch_rows = []
    for path in TRAIN_PATCH_CSVS:
        train_patch_rows.extend(read_csv_rows(path, path.stem, load_stats))
    train_patch_rows.extend(required_antonym_train_patch_rows())
    train_patch_rows = dedupe(exclude_pairs(train_patch_rows, holdout_keys, symmetric=True))
    train_patch_rows, antonym_calib_anchor_rows = reserve_antonym_calibration_rows(train_patch_rows, SEED)
    required_proxy_antonym_calib_rows = required_holdout_family_proxy_calibration_rows(holdout_keys)
    curated_base_overlap_keys = pair_keys(
        [*supervised_gold_rows, *holdout_rows, *train_patch_rows],
        symmetric=True,
    )
    base_train_rows = dedupe(exclude_pairs(base_train_rows, curated_base_overlap_keys, symmetric=True))
    patch_override_keys = pair_keys([
        *train_patch_rows,
        *antonym_calib_anchor_rows,
        *required_proxy_antonym_calib_rows,
    ], symmetric=True)
    supervised_gold_rows = dedupe(exclude_pairs(supervised_gold_rows, patch_override_keys, symmetric=True))
    supervised_gold_rows, tagged_gold_calib_rows = reserve_tagged_gold_rows_for_calibration(
        supervised_gold_rows,
        EVAL_TO_CALIB_TAGS,
    )
    train_gold_rows, calib_rows, eval_candidate_rows = split_train_calib_eval([dict(row) for row in supervised_gold_rows], SEED)
    calib_rows, eval_candidate_rows, moved_eval_rows = reroute_eval_rows_to_calib(
        calib_rows,
        eval_candidate_rows,
        EVAL_TO_CALIB_TAGS,
    )
    calib_rows = dedupe([
        *calib_rows,
        *antonym_calib_anchor_rows,
        *required_proxy_antonym_calib_rows,
        *tagged_gold_calib_rows,
    ])
    eval_rows = dedupe([*holdout_rows, *eval_candidate_rows])
    train_excluded = pair_keys([*holdout_rows, *calib_rows, *eval_candidate_rows], symmetric=True)
    non_patch_train_rows = exclude_pairs(
        [*base_train_rows, *train_gold_rows],
        train_excluded,
        symmetric=True,
    )
    train_rows = dedupe([*train_patch_rows, *non_patch_train_rows])
    gold_pool_rows = dedupe([*supervised_gold_rows, *tagged_gold_calib_rows, *holdout_rows])
    partition_stats = validate_dataset_partition(train_rows, calib_rows, eval_rows, holdout_rows)

    unsup_pairs = build_unsup_pairs_from_puzzles(PUZZLES_JSON)

    write_csv(OUTPUT_TRAIN_CSV, train_rows)
    write_csv(OUTPUT_POOL_CSV, gold_pool_rows)
    write_csv(OUTPUT_CALIB_CSV, calib_rows)
    write_csv(OUTPUT_EVAL_CSV, eval_rows)
    write_jsonl(OUTPUT_UNSUP_JSONL, unsup_pairs)

    tag_counts = Counter(row["relation_tag"] for row in train_rows)
    bucket_counts = Counter(score_bin(float(row["score_0_100"])) for row in gold_pool_rows)
    build_stats = {
        "train_rows": len(train_rows),
        "gold_pool": len(gold_pool_rows),
        "train_gold": len(train_gold_rows),
        "train_patch": len(train_patch_rows),
        "antonym_calib_anchor_rows": len(antonym_calib_anchor_rows),
        "required_proxy_antonym_calib_rows": len(required_proxy_antonym_calib_rows),
        "priority_antonym_calib_anchor_rows": sum(
            1 for row in antonym_calib_anchor_rows if row.get("_priority_antonym_calib_anchor") == "1"
        ),
        "priority_antonym_calib_weight_rows": sum(
            1 for row in antonym_calib_anchor_rows if row.get("_priority_antonym_calib_weight") == "1"
        ),
        "antonym_calib_anchor_weight": ANTONYM_CALIB_ANCHOR_WEIGHT,
        "priority_antonym_calib_anchor_weight": PRIORITY_ANTONYM_CALIB_ANCHOR_WEIGHT,
        "gold_to_calib_tags": sorted(EVAL_TO_CALIB_TAGS),
        "gold_to_calib_rows": len(tagged_gold_calib_rows),
        "gold_to_calib_weight": EVAL_TO_CALIB_ANCHOR_WEIGHT,
        "eval_to_calib_tags": sorted(EVAL_TO_CALIB_TAGS),
        "eval_to_calib_rows": len(moved_eval_rows),
        "calib_antonym_rows": sum(1 for row in calib_rows if row["relation_tag"] == "antonym_mid"),
        "calib": len(calib_rows),
        "eval": len(eval_rows),
        "fixed_holdout": len(holdout_rows),
        "unsup_pairs": len(unsup_pairs),
        "excluded_reviewer_rows": load_stats["excluded_reviewer_rows"],
        "excluded_reviewer_counts": {
            key.split("::", 1)[1]: value
            for key, value in sorted(load_stats.items())
            if key.startswith("excluded_reviewer::")
        },
        "gold_buckets": dict(sorted(bucket_counts.items())),
        "top_train_tags": dict(tag_counts.most_common(20)),
        "output_train_csv": str(OUTPUT_TRAIN_CSV),
        "output_pool_csv": str(OUTPUT_POOL_CSV),
        "output_calib_csv": str(OUTPUT_CALIB_CSV),
        "output_eval_csv": str(OUTPUT_EVAL_CSV),
        "output_unsup_jsonl": str(OUTPUT_UNSUP_JSONL),
        **partition_stats,
    }
    if OUTPUT_BUILD_STATS_JSON:
        stats_path = Path(OUTPUT_BUILD_STATS_JSON)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(build_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"train_rows={len(train_rows)}")
    print(
        f"gold_pool={len(gold_pool_rows)} "
        f"train_gold={len(train_gold_rows)} train_patch={len(train_patch_rows)} "
        f"antonym_calib_anchor_rows={len(antonym_calib_anchor_rows)} calib={len(calib_rows)} "
        f"eval={len(eval_rows)} fixed_holdout={len(holdout_rows)}"
    )
    print(f"unsup_pairs={len(unsup_pairs)}")
    print("gold_buckets=" + json.dumps(dict(sorted(bucket_counts.items())), ensure_ascii=False))
    print("top_train_tags=" + json.dumps(dict(tag_counts.most_common(12)), ensure_ascii=False))
    print(
        f"written={OUTPUT_TRAIN_CSV} {OUTPUT_POOL_CSV} "
        f"{OUTPUT_CALIB_CSV} {OUTPUT_EVAL_CSV} {OUTPUT_UNSUP_JSONL}"
    )


if __name__ == "__main__":
    main()
