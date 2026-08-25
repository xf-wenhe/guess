from __future__ import annotations

import csv
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F
from datasets import Dataset, DatasetDict
from sentence_transformers import (
    InputExample,
    SentenceTransformer,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
)
from sentence_transformers.losses import CoSENTLoss, CosineSimilarityLoss, OnlineContrastiveLoss
from sentence_transformers.training_args import BatchSamplers, MultiDatasetBatchSamplers
from torch.utils.data import DataLoader


TRAIN_CSV = Path(os.getenv("SEM_TRAIN_CSV", "data/train_v28c_balanced.csv"))
BASE_MODEL = os.getenv("SEM_BASE_MODEL", "models/bge-m3-finetuned-v27-semreal-anchor")
OUTPUT_MODEL = os.getenv("SEM_OUTPUT_MODEL", "models/bge-m3-finetuned-v28c-phoenix")
TRAIN_STATS_JSON = os.getenv("SEM_TRAIN_STATS_JSON", "").strip()
REGRESSION_PAIRS_PATH = Path(os.getenv("SEM_REGRESSION_PAIRS_PATH", "data/regression_pairs_v23.json"))
EPOCHS = int(os.getenv("SEM_EPOCHS", "2"))
BATCH_SIZE = int(os.getenv("SEM_BATCH_SIZE", "8"))
LEARNING_RATE = float(os.getenv("SEM_LR", os.getenv("SEM_LEARNING_RATE", "8e-6")))
WARMUP_RATIO = float(os.getenv("SEM_WARMUP_RATIO", "0.1"))
MAX_TRAIN_ROWS = int(os.getenv("SEM_MAX_TRAIN_ROWS", "0"))
SEED = int(os.getenv("SEM_SEED", "20260515"))
SAMPLE_SEED = int(os.getenv("SEM_SAMPLE_SEED", str(SEED)))
DEVICE = os.getenv("SEM_DEVICE", "").strip().lower()
SCALE = float(os.getenv("SEM_COSENT_SCALE", "20.0"))
HARD_NEG_BOOST = float(os.getenv("SEM_HARD_NEG_BOOST", "2.0"))
MAX_REPEAT = int(os.getenv("SEM_MAX_REPEAT", "5"))
ANGLE_MODE = os.getenv("SEM_ANGLE_MODE", "cycle").strip().lower()
LOSS_MODE = os.getenv("SEM_LOSS_MODE", "mixed").strip().lower()
COSENT_EXCLUDE_TAGS_SPEC = os.getenv("SEM_COSENT_EXCLUDE_TAGS", "antonym_mid").strip()
# Keep midpoint antonyms in cosine regression; only CoSENT must exclude them.
COSINE_EXCLUDE_TAGS_SPEC = os.getenv("SEM_COSINE_EXCLUDE_TAGS", "").strip()
MIDPOINT_TAGS_SPEC = os.getenv("SEM_MIDPOINT_TAGS", "antonym_mid").strip()
MIDPOINT_REPEAT_BOOST = float(os.getenv("SEM_MIDPOINT_REPEAT_BOOST", "2.0"))
MIDPOINT_BAND_LOW = float(os.getenv("SEM_MIDPOINT_BAND_LOW", "0.45"))
MIDPOINT_BAND_HIGH = float(os.getenv("SEM_MIDPOINT_BAND_HIGH", "0.55"))
MIDPOINT_BAND_WEIGHT = float(os.getenv("SEM_MIDPOINT_BAND_WEIGHT", "4.0"))
MIDPOINT_CENTER_WEIGHT = float(os.getenv("SEM_MIDPOINT_CENTER_WEIGHT", "1.0"))
MIDPOINT_OBJECTIVE_REPEATS = int(os.getenv("SEM_MIDPOINT_OBJECTIVE_REPEATS", "2"))
BUCKET_BAND_WEIGHT = float(os.getenv("SEM_BUCKET_BAND_WEIGHT", "1.0"))
BUCKET_BAND_CENTER_WEIGHT = float(os.getenv("SEM_BUCKET_BAND_CENTER_WEIGHT", "1.0"))
BUCKET_BAND_TAGS_SPEC = os.getenv(
    "SEM_BUCKET_BAND_TAGS",
    "collocation_not_equivalent,function_word_low,function_word_vs_real_low,"
    "hard_negative_low,hard_negative_mid,cross_category_low,cross_category_negative,"
    "same_category_but_far,same_category_weak,same_category_mid,same_category_strong,"
    "abstract_confusion,nonsense_low",
).strip()
CONTRASTIVE_MARGIN = float(os.getenv("SEM_CONTRASTIVE_MARGIN", "0.5"))
CONTRASTIVE_POS_THRESHOLD = float(os.getenv("SEM_CONTRASTIVE_POS_THRESHOLD", "0.7"))
CONTRASTIVE_NEG_THRESHOLD = float(os.getenv("SEM_CONTRASTIVE_NEG_THRESHOLD", "0.3"))
CONTRASTIVE_SCOPE = os.getenv("SEM_CONTRASTIVE_SCOPE", "selective").strip().lower()
PIN_HIGH_VALUE_ROWS = os.getenv("SEM_PIN_HIGH_VALUE_ROWS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
PIN_WEIGHT_THRESHOLD = float(os.getenv("SEM_PIN_WEIGHT_THRESHOLD", "3.0"))
MIN_ANGLE_REPEAT_FOR_HIGH_VALUE = int(os.getenv("SEM_MIN_ANGLE_REPEAT_FOR_HIGH_VALUE", "0"))
MIN_TRAIN_EXAMPLES = int(os.getenv("SEM_MIN_TRAIN_EXAMPLES", "200"))
MIN_TAG_ROWS_SPEC = os.getenv("SEM_MIN_TAG_ROWS", "antonym_mid:45").strip()
MIN_TAG_BUCKET_ROWS_SPEC = os.getenv("SEM_MIN_TAG_BUCKET_ROWS", "").strip()
MIN_ANGLE_REPEAT_TAG_BUCKETS_SPEC = os.getenv("SEM_MIN_ANGLE_REPEAT_TAG_BUCKETS", "").strip()

ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]
REQUIRED_ANTONYM_MIN_ANGLE_REPEAT = int(
    os.getenv("SEM_REQUIRED_ANTONYM_MIN_ANGLE_REPEAT", str(len(ANGLES)))
)
PRIORITY_ANTONYM_MIN_ANGLE_REPEAT = int(
    os.getenv("SEM_PRIORITY_ANTONYM_MIN_ANGLE_REPEAT", str(len(ANGLES)))
)

HARD_NEG_TAGS = {
    "collocation_not_equivalent",
    "function_word_low",
    "function_word_vs_real_low",
    "hard_negative_low",
    "hard_negative_mid",
    "cross_category_low",
    "cross_category_negative",
    "same_category_but_far",
    "abstract_confusion",
    "nonsense_low",
}

TAG_REPEAT_BOOSTS = {
    "alias_synonym_high": 1.5,
    "antonym_mid": 2.0,
    "near_synonym_high": 1.5,
    "hint_like_high": 1.5,
    "same_category_mid": 1.5,
    "same_category_strong": 1.5,
    "related_mid": 1.25,
}

BUCKET_BAND_TAGS = {
    item.strip()
    for item in BUCKET_BAND_TAGS_SPEC.split(",")
    if item.strip()
}

CONTRASTIVE_POSITIVE_TAGS = {
    "alias_synonym_high",
    "near_synonym_high",
    "hint_like_high",
}


def parse_min_tag_rows(spec: str) -> dict[str, int]:
    quotas: dict[str, int] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        tag, raw_count = item.split(":", 1)
        tag = tag.strip()
        try:
            count = int(raw_count.strip())
        except ValueError:
            continue
        if tag and count > 0:
            quotas[tag] = count
    return quotas


def parse_min_tag_bucket_rows(spec: str) -> dict[tuple[str, str], int]:
    quotas: dict[tuple[str, str], int] = {}
    valid_buckets = {"0-19", "20-39", "40-59", "60-79", "80-100"}
    for item in spec.split(","):
        item = item.strip()
        if not item or ":" not in item or "@" not in item:
            continue
        tag_bucket, raw_count = item.split(":", 1)
        tag, bucket = tag_bucket.split("@", 1)
        tag = tag.strip()
        bucket = bucket.strip()
        if not tag or bucket not in valid_buckets:
            continue
        try:
            count = int(raw_count.strip())
        except ValueError:
            continue
        if count > 0:
            quotas[(tag, bucket)] = count
    return quotas


MIN_TAG_ROWS = parse_min_tag_rows(MIN_TAG_ROWS_SPEC)
MIN_TAG_BUCKET_ROWS = parse_min_tag_bucket_rows(MIN_TAG_BUCKET_ROWS_SPEC)
MIN_ANGLE_REPEAT_TAG_BUCKETS = parse_min_tag_bucket_rows(MIN_ANGLE_REPEAT_TAG_BUCKETS_SPEC)
COSENT_EXCLUDE_TAGS = {
    item.strip()
    for item in COSENT_EXCLUDE_TAGS_SPEC.split(",")
    if item.strip()
}
COSINE_EXCLUDE_TAGS = {
    item.strip()
    for item in COSINE_EXCLUDE_TAGS_SPEC.split(",")
    if item.strip()
}
MIDPOINT_TAGS = {
    item.strip()
    for item in MIDPOINT_TAGS_SPEC.split(",")
    if item.strip()
}


def validate_objective_scope() -> None:
    """Keep midpoint supervision in cosine regression as well as midpoint loss."""
    if MIDPOINT_OBJECTIVE_REPEATS < 1:
        raise SystemExit("SEM_MIDPOINT_OBJECTIVE_REPEATS must be at least 1")
    if "antonym_mid" in MIDPOINT_TAGS and "antonym_mid" not in COSENT_EXCLUDE_TAGS:
        raise SystemExit(
            "antonym_mid midpoint rows must remain excluded from the CoSENT objective"
        )
    overlap = sorted(MIDPOINT_TAGS & COSINE_EXCLUDE_TAGS)
    if overlap:
        raise SystemExit(
            "midpoint tags must remain in the cosine objective; "
            f"remove them from SEM_COSINE_EXCLUDE_TAGS: {','.join(overlap)}"
        )


def is_bucket_band_row(row: dict) -> bool:
    """Avoid applying a generic bucket boundary to dedicated midpoint rows."""
    return (
        row["tag"] in BUCKET_BAND_TAGS
        and row["tag"] not in COSINE_EXCLUDE_TAGS
        and row["tag"] not in MIDPOINT_TAGS
    )


def canonical_pair(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def load_regression_pair_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    keys: set[tuple[str, str]] = set()
    if not isinstance(payload, list):
        return keys
    for item in payload:
        if not isinstance(item, dict):
            continue
        pair = item.get("pair")
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        left = str(pair[0]).strip()
        right = str(pair[1]).strip()
        if left and right:
            keys.add(canonical_pair(left, right))
    return keys


REGRESSION_PAIR_KEYS = load_regression_pair_keys(REGRESSION_PAIRS_PATH)


def is_required_antonym_row(tag: str, reviewer: str) -> bool:
    return tag == "antonym_mid" and reviewer == "required_antonym_patch"


def is_priority_antonym_row(tag: str, reviewer: str) -> bool:
    return tag == "antonym_mid" and reviewer.startswith("nightly_patch")


def resolve_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def score_bin(score: float) -> str:
    value = int(round(score * 100))
    if value < 20:
        return "0-19"
    if value < 40:
        return "20-39"
    if value < 60:
        return "40-59"
    if value < 80:
        return "60-79"
    return "80-100"


def stratified_limit_rows(rows: list[dict], limit: int, seed: int) -> list[dict]:
    if limit <= 0 or len(rows) <= limit:
        return rows

    rng = random.Random(seed)
    pinned = []
    pool = []
    if PIN_HIGH_VALUE_ROWS:
        for row in rows:
            if is_high_value_row(row):
                pinned.append(row)
            else:
                pool.append(row)
    else:
        pool = list(rows)
    if len(pinned) >= limit:
        rng.shuffle(pinned)
        return pinned[:limit]

    selected = list(pinned)
    if MIN_TAG_BUCKET_ROWS:
        rows_by_tag_bucket: dict[tuple[str, str], list[dict]] = {}
        for row in pool:
            rows_by_tag_bucket.setdefault((row["tag"], score_bin(row["score"])), []).append(row)
        for bucket_rows in rows_by_tag_bucket.values():
            rng.shuffle(bucket_rows)
        for key, minimum in MIN_TAG_BUCKET_ROWS.items():
            if len(selected) >= limit:
                break
            current = sum(
                1
                for row in selected
                if row["tag"] == key[0] and score_bin(row["score"]) == key[1]
            )
            need = max(0, min(minimum - current, limit - len(selected)))
            if need <= 0:
                continue
            selected.extend(rows_by_tag_bucket.get(key, [])[:need])
            rows_by_tag_bucket[key] = rows_by_tag_bucket.get(key, [])[need:]
        pool = [row for bucket_rows in rows_by_tag_bucket.values() for row in bucket_rows]

    if MIN_TAG_ROWS:
        rows_by_tag: dict[str, list[dict]] = {}
        for row in pool:
            rows_by_tag.setdefault(row["tag"], []).append(row)
        for tag_rows in rows_by_tag.values():
            rng.shuffle(tag_rows)
        for tag, minimum in MIN_TAG_ROWS.items():
            if len(selected) >= limit:
                break
            current = sum(1 for row in selected if row["tag"] == tag)
            need = max(0, min(minimum - current, limit - len(selected)))
            if need <= 0:
                continue
            selected.extend(rows_by_tag.get(tag, [])[:need])
            rows_by_tag[tag] = rows_by_tag.get(tag, [])[need:]
        pool = [row for tag_rows in rows_by_tag.values() for row in tag_rows]

    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in pool:
        bucket_key = (row["tag"] or "unknown", score_bin(row["score"]))
        buckets.setdefault(bucket_key, []).append(row)
    for bucket_rows in buckets.values():
        rng.shuffle(bucket_rows)

    bucket_names = sorted(
        buckets,
        key=lambda key: (0 if key[0] in HARD_NEG_TAGS else 1, key[0], key[1]),
    )
    while len(selected) < limit and any(buckets.values()):
        for name in bucket_names:
            if buckets[name] and len(selected) < limit:
                selected.append(buckets[name].pop())

    rng.shuffle(selected)
    return selected


def is_high_value_row(row: dict) -> bool:
    return (
        row["sample_weight"] >= PIN_WEIGHT_THRESHOLD
        or row["reviewer"].startswith("nightly_patch")
        or canonical_pair(row["answer"], row["user_input"]) in REGRESSION_PAIR_KEYS
    )


def contrastive_label(row: dict) -> float | None:
    score = row["score"]
    tag = row["tag"]
    if CONTRASTIVE_SCOPE == "all":
        if score >= CONTRASTIVE_POS_THRESHOLD:
            return 1.0
        if score <= CONTRASTIVE_NEG_THRESHOLD:
            return 0.0
        return None
    if CONTRASTIVE_SCOPE != "selective":
        raise ValueError(f"unsupported SEM_CONTRASTIVE_SCOPE={CONTRASTIVE_SCOPE!r}")

    if tag in CONTRASTIVE_POSITIVE_TAGS and score >= CONTRASTIVE_POS_THRESHOLD:
        return 1.0
    if tag in HARD_NEG_TAGS and score <= CONTRASTIVE_NEG_THRESHOLD:
        return 0.0
    return None


class MidpointBandLoss(torch.nn.Module):
    def __init__(
        self,
        model: SentenceTransformer,
        band_low: float,
        band_high: float,
        band_weight: float,
        center_weight: float,
    ) -> None:
        super().__init__()
        self.model = model
        self.band_low = band_low
        self.band_high = band_high
        self.band_weight = band_weight
        self.center_weight = center_weight

    def forward(
        self,
        sentence_features: list[dict[str, torch.Tensor]],
        labels: torch.Tensor,
    ) -> torch.Tensor:
        embeddings = [self.model(features)["sentence_embedding"] for features in sentence_features]
        scores = F.cosine_similarity(embeddings[0], embeddings[1])
        labels = labels.view(-1).to(scores.device)
        center_loss = F.mse_loss(scores, labels)
        lower_violation = torch.relu(self.band_low - scores)
        upper_violation = torch.relu(scores - self.band_high)
        band_loss = (lower_violation.square() + upper_violation.square()).mean()
        return (self.center_weight * center_loss) + (self.band_weight * band_loss)


class BucketBandLoss(torch.nn.Module):
    """Penalize predictions that leave the target score bucket.

    The cosine center term reinforces the reviewed target inside the bucket. The
    auxiliary band term also resists cross-bucket moves, which is important for
    reviewed hard negatives and ambiguous same-category rows.
    """

    def __init__(
        self,
        model: SentenceTransformer,
        band_weight: float,
        center_weight: float = 1.0,
    ) -> None:
        super().__init__()
        self.model = model
        self.band_weight = band_weight
        self.center_weight = center_weight

    def forward(
        self,
        sentence_features: list[dict[str, torch.Tensor]],
        labels: torch.Tensor,
    ) -> torch.Tensor:
        embeddings = [self.model(features)["sentence_embedding"] for features in sentence_features]
        scores = F.cosine_similarity(embeddings[0], embeddings[1])
        if self.band_weight <= 0 and self.center_weight <= 0:
            return scores.sum() * 0.0

        labels = labels.view(-1).to(scores.device).clamp(0.0, 1.0)
        bucket_index = torch.floor(labels * 5.0).to(torch.long).clamp(0, 4)
        lower = bucket_index.to(scores.dtype) * 0.2
        upper = (bucket_index + 1).to(scores.dtype) * 0.2
        lower_violation = torch.relu(lower - scores)
        upper_violation = torch.relu(scores - upper)
        violation = lower_violation.square() + upper_violation.square()
        center_loss = F.mse_loss(scores, labels)
        return (self.center_weight * center_loss) + (self.band_weight * violation.mean())


def load_examples(
    path: Path,
    seed: int,
) -> tuple[
    list[InputExample],
    list[InputExample],
    list[InputExample],
    list[InputExample],
    list[InputExample],
    list[InputExample],
    dict,
]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            answer = (row.get("answer") or "").strip()
            user_input = (row.get("user_input") or "").strip()
            score_raw = (row.get("score_0_100") or "").strip()
            tag = (row.get("relation_tag") or "").strip()
            sample_weight_raw = (row.get("sample_weight") or "").strip()
            if not answer or not user_input or not score_raw:
                continue
            try:
                score = float(score_raw) / 100.0
            except ValueError:
                continue
            try:
                sample_weight = float(sample_weight_raw) if sample_weight_raw else 1.0
            except ValueError:
                sample_weight = 1.0
            sample_weight = max(0.0, min(10.0, sample_weight))
            reviewer = (row.get("reviewer") or "").strip()
            boost = HARD_NEG_BOOST if tag in HARD_NEG_TAGS else TAG_REPEAT_BOOSTS.get(tag, 1.0)
            repeat = max(1, min(MAX_REPEAT, int(round(sample_weight * boost))))
            if ANGLE_MODE != "none" and REQUIRED_ANTONYM_MIN_ANGLE_REPEAT > 0:
                if is_required_antonym_row(tag, reviewer):
                    repeat = max(repeat, min(len(ANGLES), REQUIRED_ANTONYM_MIN_ANGLE_REPEAT))
            if ANGLE_MODE != "none" and PRIORITY_ANTONYM_MIN_ANGLE_REPEAT > 0:
                if is_priority_antonym_row(tag, reviewer):
                    repeat = max(repeat, min(len(ANGLES), PRIORITY_ANTONYM_MIN_ANGLE_REPEAT))
            if ANGLE_MODE != "none" and MIN_ANGLE_REPEAT_FOR_HIGH_VALUE > 0:
                min_angle_repeat = min(len(ANGLES), MIN_ANGLE_REPEAT_FOR_HIGH_VALUE)
                if sample_weight >= PIN_WEIGHT_THRESHOLD or reviewer.startswith("nightly_patch") or tag in TAG_REPEAT_BOOSTS:
                    repeat = max(repeat, min_angle_repeat)
            if ANGLE_MODE != "none" and MIN_ANGLE_REPEAT_TAG_BUCKETS:
                bucket_min_repeat = MIN_ANGLE_REPEAT_TAG_BUCKETS.get((tag, score_bin(score)), 0)
                if bucket_min_repeat > 0:
                    repeat = max(repeat, min(len(ANGLES), bucket_min_repeat))
            rows.append(
                {
                    "answer": answer,
                    "user_input": user_input,
                    "score": score,
                    "tag": tag,
                    "reviewer": reviewer,
                    "sample_weight": sample_weight,
                    "repeat": repeat,
                }
            )

    rng = random.Random(seed)
    rng.shuffle(rows)
    source_rows_before_limit = len(rows)
    rows = stratified_limit_rows(rows, MAX_TRAIN_ROWS, seed)

    examples = []
    cosent_examples = []
    cosine_examples = []
    contrastive_examples = []
    midpoint_examples = []
    bucket_band_examples = []
    for row_idx, row in enumerate(rows):
        for _ in range(row["repeat"]):
            repeat_idx = len(examples)
            if ANGLE_MODE == "none":
                answer_text = row["answer"]
                input_text = row["user_input"]
            elif ANGLE_MODE == "all":
                angle = ANGLES[repeat_idx % len(ANGLES)]
                answer_text = f"{angle}{row['answer']}"
                input_text = f"{angle}{row['user_input']}"
            else:
                angle = ANGLES[(row_idx + repeat_idx) % len(ANGLES)]
                answer_text = f"{angle}{row['answer']}"
                input_text = f"{angle}{row['user_input']}"
            example = InputExample(
                texts=[answer_text, input_text],
                label=row["score"],
            )
            examples.append(example)
            if row["tag"] not in COSENT_EXCLUDE_TAGS:
                cosent_examples.append(example)
            if row["tag"] not in COSINE_EXCLUDE_TAGS:
                cosine_examples.append(example)
            if row["tag"] in MIDPOINT_TAGS:
                midpoint_repeat = max(1, int(round(MIDPOINT_REPEAT_BOOST)))
                midpoint_examples.extend(
                    InputExample(texts=list(example.texts), label=example.label)
                    for _ in range(midpoint_repeat)
                )
            if is_bucket_band_row(row):
                bucket_band_examples.append(
                    InputExample(texts=list(example.texts), label=example.label)
                )
            binary_label = contrastive_label(row)
            if binary_label is not None:
                contrastive_examples.append(
                    InputExample(
                        texts=[answer_text, input_text],
                        label=binary_label,
                    )
                )
    rng.shuffle(examples)
    rng.shuffle(cosent_examples)
    rng.shuffle(cosine_examples)
    rng.shuffle(contrastive_examples)
    rng.shuffle(midpoint_examples)
    rng.shuffle(bucket_band_examples)

    tag_counts = Counter(row["tag"] for row in rows)
    contrastive_tag_counts = Counter()
    contrastive_label_counts = Counter()
    for row in rows:
        binary_label = contrastive_label(row)
        if binary_label is not None:
            contrastive_tag_counts[row["tag"]] += row["repeat"]
            contrastive_label_counts[str(int(binary_label))] += row["repeat"]
    score_buckets = Counter((int(row["score"] * 100) // 10) * 10 for row in rows)
    bucket_band_rows = sum(
        1
        for row in rows
        if is_bucket_band_row(row)
    )
    hard_count = sum(1 for row in rows if row["tag"] in HARD_NEG_TAGS)
    protected_count = sum(1 for row in rows if row["tag"] in TAG_REPEAT_BOOSTS)
    antonym_mid_count = sum(1 for row in rows if row["tag"] == "antonym_mid")
    antonym_mid_repeats = sum(row["repeat"] for row in rows if row["tag"] == "antonym_mid")
    required_antonym_count = sum(1 for row in rows if is_required_antonym_row(row["tag"], row["reviewer"]))
    required_antonym_repeats = sum(
        row["repeat"] for row in rows if is_required_antonym_row(row["tag"], row["reviewer"])
    )
    priority_antonym_count = sum(1 for row in rows if is_priority_antonym_row(row["tag"], row["reviewer"]))
    priority_antonym_repeats = sum(
        row["repeat"] for row in rows if is_priority_antonym_row(row["tag"], row["reviewer"])
    )
    cosent_excluded_rows = sum(1 for row in rows if row["tag"] in COSENT_EXCLUDE_TAGS)
    cosent_excluded_examples = sum(row["repeat"] for row in rows if row["tag"] in COSENT_EXCLUDE_TAGS)
    cosine_excluded_rows = sum(1 for row in rows if row["tag"] in COSINE_EXCLUDE_TAGS)
    cosine_excluded_examples = sum(row["repeat"] for row in rows if row["tag"] in COSINE_EXCLUDE_TAGS)
    pinned_count = sum(1 for row in rows if is_high_value_row(row))
    regression_protected_count = sum(
        1
        for row in rows
        if canonical_pair(row["answer"], row["user_input"]) in REGRESSION_PAIR_KEYS
    )
    angle_covered_count = sum(1 for row in rows if row["repeat"] >= len(ANGLES))
    tag_bucket_angle_repeat_rows = {
        f"{tag}@{bucket}": sum(
            1
            for row in rows
            if row["tag"] == tag and score_bin(row["score"]) == bucket
        )
        for tag, bucket in sorted(MIN_ANGLE_REPEAT_TAG_BUCKETS)
    }
    tag_bucket_angle_repeat_examples = {
        f"{tag}@{bucket}": sum(
            row["repeat"]
            for row in rows
            if row["tag"] == tag and score_bin(row["score"]) == bucket
        )
        for tag, bucket in sorted(MIN_ANGLE_REPEAT_TAG_BUCKETS)
    }
    stats = {
        "source_rows_before_limit": source_rows_before_limit,
        "source_rows": len(rows),
        "train_examples_after_repeat": len(examples),
        "cosent_examples_after_repeat": len(cosent_examples),
        "cosent_exclude_tags": sorted(COSENT_EXCLUDE_TAGS),
        "cosent_excluded_rows": cosent_excluded_rows,
        "cosent_excluded_examples_after_repeat": cosent_excluded_examples,
        "cosine_examples_after_repeat": len(cosine_examples),
        "cosine_exclude_tags": sorted(COSINE_EXCLUDE_TAGS),
        "cosine_excluded_rows": cosine_excluded_rows,
        "cosine_excluded_examples_after_repeat": cosine_excluded_examples,
        "midpoint_tags": sorted(MIDPOINT_TAGS),
        "midpoint_repeat_boost": MIDPOINT_REPEAT_BOOST,
        "midpoint_band_low": MIDPOINT_BAND_LOW,
        "midpoint_band_high": MIDPOINT_BAND_HIGH,
        "midpoint_band_weight": MIDPOINT_BAND_WEIGHT,
        "midpoint_center_weight": MIDPOINT_CENTER_WEIGHT,
        "midpoint_objective_repeats": MIDPOINT_OBJECTIVE_REPEATS,
        "midpoint_examples_after_repeat": len(midpoint_examples),
        "bucket_band_tags": sorted(BUCKET_BAND_TAGS),
        "bucket_band_weight": BUCKET_BAND_WEIGHT,
        "bucket_band_center_weight": BUCKET_BAND_CENTER_WEIGHT,
        "bucket_band_rows": bucket_band_rows,
        "bucket_band_examples_after_repeat": len(bucket_band_examples),
        "contrastive_examples_after_repeat": len(contrastive_examples),
        "contrastive_scope": CONTRASTIVE_SCOPE,
        "min_tag_rows": MIN_TAG_ROWS,
        "min_tag_bucket_rows": {
            f"{tag}@{bucket}": count
            for (tag, bucket), count in sorted(MIN_TAG_BUCKET_ROWS.items())
        },
        "min_angle_repeat_tag_buckets": {
            f"{tag}@{bucket}": count
            for (tag, bucket), count in sorted(MIN_ANGLE_REPEAT_TAG_BUCKETS.items())
        },
        "contrastive_pos_threshold": CONTRASTIVE_POS_THRESHOLD,
        "contrastive_neg_threshold": CONTRASTIVE_NEG_THRESHOLD,
        "contrastive_label_counts": dict(contrastive_label_counts),
        "contrastive_tag_counts": dict(contrastive_tag_counts.most_common(30)),
        "hard_negative_rows": hard_count,
        "hard_negative_ratio": round(hard_count / max(len(rows), 1), 6),
        "antonym_mid_rows": antonym_mid_count,
        "antonym_mid_examples_after_repeat": antonym_mid_repeats,
        "required_antonym_rows": required_antonym_count,
        "required_antonym_examples_after_repeat": required_antonym_repeats,
        "priority_antonym_rows": priority_antonym_count,
        "priority_antonym_examples_after_repeat": priority_antonym_repeats,
        "protected_positive_rows": protected_count,
        "pinned_high_value_rows": pinned_count,
        "regression_protected_rows": regression_protected_count,
        "regression_pairs_path": str(REGRESSION_PAIRS_PATH),
        "full_angle_coverage_rows": angle_covered_count,
        "tag_bucket_angle_repeat_rows": tag_bucket_angle_repeat_rows,
        "tag_bucket_angle_repeat_examples_after_repeat": tag_bucket_angle_repeat_examples,
        "angle_mode": ANGLE_MODE,
        "tag_counts": dict(tag_counts.most_common(30)),
        "score_buckets": {str(k): v for k, v in sorted(score_buckets.items())},
    }
    return (
        examples,
        cosent_examples,
        cosine_examples,
        contrastive_examples,
        midpoint_examples,
        bucket_band_examples,
        stats,
    )


def fit_with_explicit_cpu(
    model: SentenceTransformer,
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    epochs: int,
    batch_size: int,
    warmup_steps: int,
    learning_rate: float,
) -> None:
    def identity(batch):
        return batch

    datasets: dict[str, Dataset] = {}
    losses: dict[str, torch.nn.Module] = {}
    for idx, (data_loader, loss_fn) in enumerate(train_objectives, start=1):
        data_loader.collate_fn = identity
        texts = []
        labels = []
        for batch in data_loader:
            batch_texts, batch_labels = zip(*[(example.texts, example.label) for example in batch])
            texts += batch_texts
            labels += batch_labels
        dataset = Dataset.from_dict({f"sentence_{text_idx}": text for text_idx, text in enumerate(zip(*texts))})
        dataset = dataset.add_column("label", labels)
        dataset_key = f"_dataset_{idx}"
        datasets[dataset_key] = dataset
        losses[dataset_key] = loss_fn

    args = SentenceTransformerTrainingArguments(
        output_dir=str(Path(OUTPUT_MODEL).with_name(Path(OUTPUT_MODEL).name + "_checkpoints")),
        batch_sampler=BatchSamplers.BATCH_SAMPLER,
        multi_dataset_batch_sampler=MultiDatasetBatchSamplers.ROUND_ROBIN,
        per_device_train_batch_size=batch_size,
        num_train_epochs=epochs,
        warmup_steps=warmup_steps,
        learning_rate=learning_rate,
        use_cpu=True,
        no_cuda=True,
        use_mps_device=False,
        eval_strategy="no",
        save_strategy="no",
        disable_tqdm=False,
    )
    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=DatasetDict(datasets),
        loss=losses,
    )
    trainer.train()


def round_robin_steps_per_epoch(
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
) -> int:
    """Match SentenceTransformers' ROUND_ROBIN batch sampler update count."""
    if not train_objectives:
        raise ValueError("at least one training objective is required")
    batches_per_objective = [len(data_loader) for data_loader, _ in train_objectives]
    if any(batch_count <= 0 for batch_count in batches_per_objective):
        raise ValueError("every training objective must contain at least one batch")
    return min(batches_per_objective) * len(train_objectives)


def seed_training(seed: int) -> None:
    """Keep model and loader randomness tied to the per-round training seed."""
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def main() -> None:
    validate_objective_scope()
    if not TRAIN_CSV.exists():
        raise SystemExit(f"missing: {TRAIN_CSV}")

    device = resolve_device()
    seed_training(SEED)
    (
        examples,
        cosent_examples,
        cosine_examples,
        contrastive_examples,
        midpoint_examples,
        bucket_band_examples,
        stats,
    ) = load_examples(TRAIN_CSV, SAMPLE_SEED)
    stats["sample_seed"] = SAMPLE_SEED
    if len(examples) < MIN_TRAIN_EXAMPLES:
        raise SystemExit(f"not enough training examples (<{MIN_TRAIN_EXAMPLES})")
    if LOSS_MODE in {"cosent", "mixed", "mixed_contrastive"} and not cosent_examples:
        raise SystemExit("CoSENT objective has no examples after SEM_COSENT_EXCLUDE_TAGS filtering")
    if LOSS_MODE in {"cosine", "mixed", "mixed_contrastive"} and not cosine_examples:
        raise SystemExit("Cosine objective has no examples after SEM_COSINE_EXCLUDE_TAGS filtering")

    print(f"base_model={BASE_MODEL}")
    print(f"output_model={OUTPUT_MODEL}")
    print(f"device={device}")
    print(f"epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}")
    print(f"warmup_ratio={WARMUP_RATIO} seed={SEED} sample_seed={SAMPLE_SEED} scale={SCALE}")
    print(f"hard_neg_boost={HARD_NEG_BOOST} max_repeat={MAX_REPEAT} angle_mode={ANGLE_MODE} loss_mode={LOSS_MODE}")
    print(f"cosent_exclude_tags={','.join(sorted(COSENT_EXCLUDE_TAGS)) or '-'}")
    print(f"cosine_exclude_tags={','.join(sorted(COSINE_EXCLUDE_TAGS)) or '-'}")
    print(
        f"midpoint_tags={','.join(sorted(MIDPOINT_TAGS)) or '-'} "
        f"midpoint_repeat_boost={MIDPOINT_REPEAT_BOOST} "
        f"midpoint_band=[{MIDPOINT_BAND_LOW:.2f},{MIDPOINT_BAND_HIGH:.2f}] "
        f"midpoint_band_weight={MIDPOINT_BAND_WEIGHT} "
        f"midpoint_center_weight={MIDPOINT_CENTER_WEIGHT} "
        f"midpoint_objective_repeats={MIDPOINT_OBJECTIVE_REPEATS}"
    )
    print(
        f"bucket_band_tags={','.join(sorted(BUCKET_BAND_TAGS)) or '-'} "
        f"bucket_band_weight={BUCKET_BAND_WEIGHT} "
        f"bucket_band_center_weight={BUCKET_BAND_CENTER_WEIGHT} "
        f"bucket_band_examples={len(bucket_band_examples)}"
    )
    print(f"required_antonym_min_angle_repeat={REQUIRED_ANTONYM_MIN_ANGLE_REPEAT}")
    print(f"priority_antonym_min_angle_repeat={PRIORITY_ANTONYM_MIN_ANGLE_REPEAT}")
    print(
        "contrastive_margin="
        f"{CONTRASTIVE_MARGIN} contrastive_pos_threshold={CONTRASTIVE_POS_THRESHOLD} "
        f"contrastive_neg_threshold={CONTRASTIVE_NEG_THRESHOLD} contrastive_scope={CONTRASTIVE_SCOPE}"
    )
    print(f"pin_high_value_rows={PIN_HIGH_VALUE_ROWS} pin_weight_threshold={PIN_WEIGHT_THRESHOLD}")
    print(f"min_angle_repeat_for_high_value={MIN_ANGLE_REPEAT_FOR_HIGH_VALUE}")
    print(
        "min_angle_repeat_tag_buckets="
        + json.dumps(stats.get("min_angle_repeat_tag_buckets", {}), ensure_ascii=False, sort_keys=True)
    )
    print("train_stats=" + json.dumps(stats, ensure_ascii=False))
    if TRAIN_STATS_JSON:
        stats_path = Path(TRAIN_STATS_JSON)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    model = SentenceTransformer(
        BASE_MODEL,
        device=device,
        local_files_only=True,
    )
    cosent_loader = DataLoader(
        cosent_examples,
        shuffle=True,
        batch_size=BATCH_SIZE,
        num_workers=0,
        pin_memory=False,
    )
    examples_loader = DataLoader(
        examples,
        shuffle=True,
        batch_size=BATCH_SIZE,
        num_workers=0,
        pin_memory=False,
    )
    midpoint_loader = DataLoader(
        midpoint_examples,
        shuffle=True,
        batch_size=BATCH_SIZE,
        num_workers=0,
        pin_memory=False,
    )
    bucket_band_loader = DataLoader(
        bucket_band_examples,
        shuffle=True,
        batch_size=BATCH_SIZE,
        num_workers=0,
        pin_memory=False,
    )
    if LOSS_MODE == "cosine":
        cosine_loader = DataLoader(
            list(cosine_examples),
            shuffle=True,
            batch_size=BATCH_SIZE,
            num_workers=0,
            pin_memory=False,
        )
        train_objectives = [(cosine_loader, CosineSimilarityLoss(model=model))]
    elif LOSS_MODE == "mixed":
        cosine_loader = DataLoader(
            list(cosine_examples),
            shuffle=True,
            batch_size=BATCH_SIZE,
            num_workers=0,
            pin_memory=False,
        )
        train_objectives = [
            (cosent_loader, CoSENTLoss(model=model, scale=SCALE)),
            (cosine_loader, CosineSimilarityLoss(model=model)),
        ]
        if midpoint_examples:
            for _ in range(MIDPOINT_OBJECTIVE_REPEATS):
                train_objectives.append(
                    (
                        midpoint_loader,
                        MidpointBandLoss(
                            model=model,
                            band_low=MIDPOINT_BAND_LOW,
                            band_high=MIDPOINT_BAND_HIGH,
                            band_weight=MIDPOINT_BAND_WEIGHT,
                            center_weight=MIDPOINT_CENTER_WEIGHT,
                        ),
                    )
                )
        if bucket_band_examples and BUCKET_BAND_WEIGHT > 0:
            train_objectives.append(
                (
                    bucket_band_loader,
                    BucketBandLoss(
                        model=model,
                        band_weight=BUCKET_BAND_WEIGHT,
                        center_weight=BUCKET_BAND_CENTER_WEIGHT,
                    ),
                )
            )
    elif LOSS_MODE == "mixed_contrastive":
        if not contrastive_examples:
            raise SystemExit("mixed_contrastive requires at least one positive or negative contrastive example")
        cosine_loader = DataLoader(
            list(cosine_examples),
            shuffle=True,
            batch_size=BATCH_SIZE,
            num_workers=0,
            pin_memory=False,
        )
        contrastive_loader = DataLoader(
            contrastive_examples,
            shuffle=True,
            batch_size=BATCH_SIZE,
            num_workers=0,
            pin_memory=False,
        )
        train_objectives = [
            (cosent_loader, CoSENTLoss(model=model, scale=SCALE)),
            (cosine_loader, CosineSimilarityLoss(model=model)),
            (contrastive_loader, OnlineContrastiveLoss(model=model, margin=CONTRASTIVE_MARGIN)),
        ]
        if midpoint_examples:
            for _ in range(MIDPOINT_OBJECTIVE_REPEATS):
                train_objectives.append(
                    (
                        midpoint_loader,
                        MidpointBandLoss(
                            model=model,
                            band_low=MIDPOINT_BAND_LOW,
                            band_high=MIDPOINT_BAND_HIGH,
                            band_weight=MIDPOINT_BAND_WEIGHT,
                            center_weight=MIDPOINT_CENTER_WEIGHT,
                        ),
                    )
                )
        if bucket_band_examples and BUCKET_BAND_WEIGHT > 0:
            train_objectives.append(
                (
                    bucket_band_loader,
                    BucketBandLoss(
                        model=model,
                        band_weight=BUCKET_BAND_WEIGHT,
                        center_weight=BUCKET_BAND_CENTER_WEIGHT,
                    ),
                )
            )
    else:
        train_objectives = [(cosent_loader, CoSENTLoss(model=model, scale=SCALE))]

    steps_per_epoch = round_robin_steps_per_epoch(train_objectives)
    total_steps = steps_per_epoch * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)
    print(
        f"objective_count={len(train_objectives)} "
        f"round_robin_steps_per_epoch={steps_per_epoch} "
        f"total_steps={total_steps} warmup_steps={warmup_steps}"
    )
    print(f"Starting supervised {LOSS_MODE} training...")

    started = time.time()
    if device == "cpu":
        fit_with_explicit_cpu(
            model=model,
            train_objectives=train_objectives,
            epochs=EPOCHS,
            batch_size=BATCH_SIZE,
            warmup_steps=warmup_steps,
            learning_rate=LEARNING_RATE,
        )
    else:
        model.fit(
            train_objectives=train_objectives,
            epochs=EPOCHS,
            warmup_steps=warmup_steps,
            optimizer_params={"lr": LEARNING_RATE},
            show_progress_bar=True,
        )
    elapsed = time.time() - started
    model.save(OUTPUT_MODEL)

    metrics = {
        "base_model": BASE_MODEL,
        "train_csv": str(TRAIN_CSV),
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "learning_rate": LEARNING_RATE,
        "warmup_ratio": WARMUP_RATIO,
        "warmup_steps": warmup_steps,
        "objective_count": len(train_objectives),
        "round_robin_steps_per_epoch": steps_per_epoch,
        "total_steps": total_steps,
        "scale": SCALE,
        "loss_mode": LOSS_MODE,
        "cosent_exclude_tags": sorted(COSENT_EXCLUDE_TAGS),
        "cosine_exclude_tags": sorted(COSINE_EXCLUDE_TAGS),
        "midpoint_tags": sorted(MIDPOINT_TAGS),
        "midpoint_repeat_boost": MIDPOINT_REPEAT_BOOST,
        "midpoint_band_low": MIDPOINT_BAND_LOW,
        "midpoint_band_high": MIDPOINT_BAND_HIGH,
        "midpoint_band_weight": MIDPOINT_BAND_WEIGHT,
        "midpoint_center_weight": MIDPOINT_CENTER_WEIGHT,
        "midpoint_objective_repeats": MIDPOINT_OBJECTIVE_REPEATS,
        "bucket_band_tags": sorted(BUCKET_BAND_TAGS),
        "bucket_band_weight": BUCKET_BAND_WEIGHT,
        "bucket_band_center_weight": BUCKET_BAND_CENTER_WEIGHT,
        "bucket_band_examples_after_repeat": len(bucket_band_examples),
        "contrastive_margin": CONTRASTIVE_MARGIN,
        "contrastive_scope": CONTRASTIVE_SCOPE,
        "hard_neg_boost": HARD_NEG_BOOST,
        "max_repeat": MAX_REPEAT,
        "angle_mode": ANGLE_MODE,
        "pin_high_value_rows": PIN_HIGH_VALUE_ROWS,
        "pin_weight_threshold": PIN_WEIGHT_THRESHOLD,
        "min_angle_repeat_for_high_value": MIN_ANGLE_REPEAT_FOR_HIGH_VALUE,
        "required_antonym_min_angle_repeat": REQUIRED_ANTONYM_MIN_ANGLE_REPEAT,
        "min_train_examples": MIN_TRAIN_EXAMPLES,
        "seed": SEED,
        "sample_seed": SAMPLE_SEED,
        "device": device,
        "elapsed_seconds": round(elapsed, 1),
        **stats,
    }
    metrics_path = Path(OUTPUT_MODEL + "_train_metrics.json")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Training completed in {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    print(f"Model saved to {OUTPUT_MODEL}")
    print(f"Metrics saved to {metrics_path}")


if __name__ == "__main__":
    main()
