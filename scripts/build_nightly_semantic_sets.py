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
    ("胜利", "失败", "抽象", "抽象"),
    ("白天", "黑夜", "时间", "时间"),
    ("古代", "现代", "时间", "时间"),
]


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


def read_csv_rows(path: Path, reviewer_fallback: str) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = []
        for row in csv.DictReader(file):
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


def pair_keys(rows: list[dict]) -> set[tuple[str, str]]:
    return {(row["answer"], row["user_input"]) for row in rows}


def exclude_pairs(rows: list[dict], excluded: set[tuple[str, str]]) -> list[dict]:
    if not excluded:
        return list(rows)
    return [row for row in rows if (row["answer"], row["user_input"]) not in excluded]


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
        rng.shuffle(bucket_rows)
        n = len(bucket_rows)
        if n == 1:
            train.extend(bucket_rows)
            continue
        if n == 2:
            train.extend(bucket_rows[:1])
            calib.extend(bucket_rows[1:])
            continue
        n_calib = max(1, int(round(n * CALIB_RATIO)))
        n_eval = max(1, int(round(n * EVAL_RATIO)))
        if n_calib + n_eval >= n:
            overflow = n_calib + n_eval - (n - 1)
            reduce_eval = min(overflow, max(0, n_eval - 1))
            n_eval -= reduce_eval
            overflow -= reduce_eval
            n_calib = max(1, n_calib - overflow)
        calib.extend(bucket_rows[:n_calib])
        eval_rows.extend(bucket_rows[n_calib:n_calib + n_eval])
        train.extend(bucket_rows[n_calib + n_eval:])
    rng.shuffle(train)
    rng.shuffle(calib)
    rng.shuffle(eval_rows)
    return dedupe(train), dedupe(calib), dedupe(eval_rows)


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

    supervised_gold_rows = []
    supervised_gold_rows.extend(normalize_row(row, "manual_gold") for row in manual_rows)
    supervised_gold_rows.extend(read_csv_rows(SCORED_CSV, "scored_user_input"))
    for path in EXTRA_GOLD_CSVS:
        supervised_gold_rows.extend(read_csv_rows(path, path.stem))
    supervised_gold_rows = dedupe([row for row in supervised_gold_rows if row is not None])
    supervised_gold_rows = stratified_trim(supervised_gold_rows, TARGET_GOLD_TOTAL, SEED)

    holdout_rows = []
    for path in HOLDOUT_CSVS:
        holdout_rows.extend(read_csv_rows(path, path.stem))
    holdout_rows = dedupe(holdout_rows)
    holdout_keys = pair_keys(holdout_rows)
    supervised_gold_rows = dedupe(exclude_pairs(supervised_gold_rows, holdout_keys))

    base_train_rows = read_csv_rows(BASE_TRAIN_CSV, "base_train")
    train_patch_rows = []
    for path in TRAIN_PATCH_CSVS:
        train_patch_rows.extend(read_csv_rows(path, path.stem))
    train_patch_rows.extend(required_antonym_train_patch_rows())
    train_patch_rows = dedupe(exclude_pairs(train_patch_rows, holdout_keys))
    supervised_gold_rows = dedupe(exclude_pairs(supervised_gold_rows, pair_keys(train_patch_rows)))
    train_gold_rows, calib_rows, eval_candidate_rows = split_train_calib_eval([dict(row) for row in supervised_gold_rows], SEED)
    eval_rows = dedupe([*holdout_rows, *eval_candidate_rows])
    train_excluded = pair_keys([*holdout_rows, *calib_rows, *eval_candidate_rows])
    train_rows = dedupe(exclude_pairs([*train_patch_rows, *base_train_rows, *train_gold_rows], train_excluded))

    unsup_pairs = build_unsup_pairs_from_puzzles(PUZZLES_JSON)

    write_csv(OUTPUT_TRAIN_CSV, train_rows)
    write_csv(OUTPUT_POOL_CSV, dedupe([*supervised_gold_rows, *holdout_rows]))
    write_csv(OUTPUT_CALIB_CSV, calib_rows)
    write_csv(OUTPUT_EVAL_CSV, eval_rows)
    write_jsonl(OUTPUT_UNSUP_JSONL, unsup_pairs)

    tag_counts = Counter(row["relation_tag"] for row in train_rows)
    bucket_counts = Counter(score_bin(float(row["score_0_100"])) for row in [*supervised_gold_rows, *holdout_rows])
    build_stats = {
        "train_rows": len(train_rows),
        "gold_pool": len(supervised_gold_rows) + len(holdout_rows),
        "train_gold": len(train_gold_rows),
        "train_patch": len(train_patch_rows),
        "calib": len(calib_rows),
        "eval": len(eval_rows),
        "fixed_holdout": len(holdout_rows),
        "unsup_pairs": len(unsup_pairs),
        "gold_buckets": dict(sorted(bucket_counts.items())),
        "top_train_tags": dict(tag_counts.most_common(20)),
        "output_train_csv": str(OUTPUT_TRAIN_CSV),
        "output_pool_csv": str(OUTPUT_POOL_CSV),
        "output_calib_csv": str(OUTPUT_CALIB_CSV),
        "output_eval_csv": str(OUTPUT_EVAL_CSV),
        "output_unsup_jsonl": str(OUTPUT_UNSUP_JSONL),
    }
    if OUTPUT_BUILD_STATS_JSON:
        stats_path = Path(OUTPUT_BUILD_STATS_JSON)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(build_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"train_rows={len(train_rows)}")
    print(
        f"gold_pool={len(supervised_gold_rows) + len(holdout_rows)} "
        f"train_gold={len(train_gold_rows)} train_patch={len(train_patch_rows)} calib={len(calib_rows)} "
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
