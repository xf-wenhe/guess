from __future__ import annotations

import csv
import json
import math
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
from torch.utils.data import DataLoader, RandomSampler


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
# SentenceTransformer.fit does not expose the Trainer seed; its current
# SentenceTransformerTrainingArguments default is 42.
LEGACY_MODEL_FIT_SEED = 42
DEVICE = os.getenv("SEM_DEVICE", "").strip().lower()
SCALE = float(os.getenv("SEM_COSENT_SCALE", "20.0"))
HARD_NEG_BOOST = float(os.getenv("SEM_HARD_NEG_BOOST", "2.0"))
MAX_REPEAT = int(os.getenv("SEM_MAX_REPEAT", "5"))
ANGLE_MODE = os.getenv("SEM_ANGLE_MODE", "cycle").strip().lower()
LOSS_MODE = os.getenv("SEM_LOSS_MODE", "mixed").strip().lower()
COSENT_EXCLUDE_TAGS_SPEC = os.getenv("SEM_COSENT_EXCLUDE_TAGS", "antonym_mid").strip()
# Keep midpoint antonyms in cosine regression; only CoSENT must exclude them.
COSINE_EXCLUDE_TAGS_SPEC = os.getenv("SEM_COSINE_EXCLUDE_TAGS", "").strip()
# Some hard negatives are useful for evaluator-aligned bucket repair but are
# too noisy to share the global ranking/regression objectives.
BUCKET_ONLY_TAGS_SPEC = os.getenv("SEM_BUCKET_ONLY_TAGS", "same_category_but_far").strip()
MIDPOINT_TAGS_SPEC = os.getenv("SEM_MIDPOINT_TAGS", "antonym_mid").strip()
MIDPOINT_REPEAT_BOOST = float(os.getenv("SEM_MIDPOINT_REPEAT_BOOST", "2.0"))
# Keep raw midpoint supervision centered on the fixed strict 45-55 gate; the
# calibration stage must improve it without relying on a narrowed train band.
MIDPOINT_BAND_LOW_SPEC = os.getenv("SEM_MIDPOINT_BAND_LOW", "0.45").strip()
MIDPOINT_BAND_HIGH_SPEC = os.getenv("SEM_MIDPOINT_BAND_HIGH", "0.55").strip()
if MIDPOINT_BAND_LOW_SPEC == "0.47" or MIDPOINT_BAND_HIGH_SPEC == "0.53":
    # Direct invocations can inherit the pre-fix launchd values, so keep the
    # trainer safe even when nightly_train_v26.sh is bypassed.
    MIDPOINT_BAND_LOW = 0.45
    MIDPOINT_BAND_HIGH = 0.55
else:
    MIDPOINT_BAND_LOW = float(MIDPOINT_BAND_LOW_SPEC)
    MIDPOINT_BAND_HIGH = float(MIDPOINT_BAND_HIGH_SPEC)
MIDPOINT_BAND_WEIGHT = float(os.getenv("SEM_MIDPOINT_BAND_WEIGHT", "4.0"))
MIDPOINT_CENTER_WEIGHT = float(os.getenv("SEM_MIDPOINT_CENTER_WEIGHT", "1.0"))
MIDPOINT_OBJECTIVE_REPEATS = int(os.getenv("SEM_MIDPOINT_OBJECTIVE_REPEATS", "2"))
BUCKET_BAND_WEIGHT = float(os.getenv("SEM_BUCKET_BAND_WEIGHT", "1.0"))
BUCKET_BAND_CENTER_WEIGHT = float(os.getenv("SEM_BUCKET_BAND_CENTER_WEIGHT", "1.0"))
# Keep bucket emphasis opt-in without changing the round-robin schedule by default.
BUCKET_BAND_HARD_NEG_REPEAT = max(
    1, int(os.getenv("SEM_BUCKET_BAND_HARD_NEG_REPEAT", "2"))
)
BUCKET_BAND_BASE_GUARD = os.getenv("SEM_BUCKET_BAND_BASE_GUARD", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
BUCKET_BAND_BASE_GUARD_WEIGHT = float(os.getenv("SEM_BUCKET_BAND_BASE_GUARD_WEIGHT", "1.0"))
BUCKET_BAND_BASE_GUARD_MARGIN = min(
    0.09,
    max(0.0, float(os.getenv("SEM_BUCKET_BAND_BASE_GUARD_MARGIN", "0.02"))),
)
BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT = max(
    0.0,
    float(os.getenv("SEM_BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT", "0.25")),
)
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
DEFAULT_MIN_ANGLE_REPEAT_TAG_BUCKETS = (
    "same_category_but_far@20-39:5,same_category_mid@20-39:5,"
    "same_category_mid@40-59:5,same_category_mid@60-79:5"
)
MIN_ANGLE_REPEAT_TAG_BUCKETS_SPEC = os.getenv(
    "SEM_MIN_ANGLE_REPEAT_TAG_BUCKETS",
    DEFAULT_MIN_ANGLE_REPEAT_TAG_BUCKETS,
).strip()

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
PROXY_ANTONYM_MIN_ANGLE_REPEAT = int(
    os.getenv("SEM_PROXY_ANTONYM_MIN_ANGLE_REPEAT", str(len(ANGLES)))
)
PROXY_ANTONYM_TRAIN_REVIEWER = "required_antonym_proxy_train"

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
BUCKET_ONLY_TAGS = {
    item.strip()
    for item in BUCKET_ONLY_TAGS_SPEC.split(",")
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
    missing_bucket_tags = sorted(BUCKET_ONLY_TAGS - BUCKET_BAND_TAGS)
    if missing_bucket_tags:
        raise SystemExit(
            "bucket-only tags must remain in the bucket-band objective; "
            f"add them to SEM_BUCKET_BAND_TAGS: {','.join(missing_bucket_tags)}"
        )
    midpoint_bucket_only = sorted(BUCKET_ONLY_TAGS & MIDPOINT_TAGS)
    if midpoint_bucket_only:
        raise SystemExit(
            "bucket-only tags cannot also be midpoint tags: "
            f"{','.join(midpoint_bucket_only)}"
        )


def is_bucket_band_row(row: dict) -> bool:
    """Keep bucket-only rows in the evaluator-aligned bucket objective."""
    if row["tag"] not in BUCKET_BAND_TAGS or row["tag"] in MIDPOINT_TAGS:
        return False
    if row["tag"] in BUCKET_ONLY_TAGS:
        return True
    return row["tag"] not in COSINE_EXCLUDE_TAGS


def bucket_band_repeat_for_row(row: dict) -> int:
    """Spend extra bucket-boundary updates on the already-selected hard negatives."""
    if row["tag"] in HARD_NEG_TAGS:
        return BUCKET_BAND_HARD_NEG_REPEAT
    return 1


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


def is_proxy_antonym_row(tag: str, reviewer: str) -> bool:
    return tag == "antonym_mid" and reviewer == PROXY_ANTONYM_TRAIN_REVIEWER


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
    if tag in BUCKET_ONLY_TAGS:
        return None
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
        base_guard_weight: float = 1.0,
        base_guard_margin: float = 0.02,
        base_guard_anchor_weight: float = BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
    ) -> None:
        super().__init__()
        self.model = model
        self.band_low = band_low
        self.band_high = band_high
        self.band_weight = band_weight
        self.center_weight = center_weight
        self.base_guard_weight = base_guard_weight
        self.base_guard_margin = min(0.09, max(0.0, base_guard_margin))
        self.base_guard_anchor_weight = max(0.0, base_guard_anchor_weight)

    def forward(
        self,
        sentence_features: list[dict[str, torch.Tensor]],
        labels: torch.Tensor,
    ) -> torch.Tensor:
        embeddings = [self.model(features)["sentence_embedding"] for features in sentence_features]
        scores = F.cosine_similarity(embeddings[0], embeddings[1])
        target_labels, base_scores = _unpack_guard_labels(labels, scores)
        valid = torch.isfinite(target_labels)
        if base_scores is not None:
            valid &= torch.isfinite(base_scores)
        if not torch.any(valid):
            return scores.sum() * 0.0
        scores = scores[valid]
        labels = target_labels[valid].to(scores.device).clamp(0.0, 1.0)
        if base_scores is not None:
            base_scores = base_scores[valid]
        center_loss = F.mse_loss(scores, labels)
        lower_violation = torch.relu(self.band_low - scores)
        upper_violation = torch.relu(scores - self.band_high)
        band_loss = (lower_violation.square() + upper_violation.square()).mean()
        base_guard_loss = (
            _base_bucket_guard_penalty(
                scores,
                labels,
                base_scores,
                self.base_guard_margin,
                self.base_guard_anchor_weight,
            )
            if self.base_guard_weight > 0
            else scores.sum() * 0.0
        )
        return (
            (self.center_weight * center_loss)
            + (self.band_weight * band_loss)
            + (self.base_guard_weight * base_guard_loss)
        )


def _unpack_guard_labels(
    labels: torch.Tensor,
    scores: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor | None]:
    labels = labels.to(scores.device)
    if labels.ndim == 1:
        return labels.view(-1), None
    if labels.ndim == 2 and labels.shape[1] == 1:
        return labels[:, 0].view(-1), None
    if labels.ndim == 2 and labels.shape[1] >= 2:
        # Guarded objectives carry [target_score, frozen_base_score].
        return labels[:, 0].view(-1), labels[:, 1].view(-1)
    raise ValueError("guarded labels must be scalar or [target, base_score]")


def _base_bucket_guard_penalty(
    scores: torch.Tensor,
    target_labels: torch.Tensor,
    base_scores: torch.Tensor | None,
    margin: float,
    anchor_weight: float = 0.0,
) -> torch.Tensor:
    if base_scores is None:
        return scores.sum() * 0.0

    target_labels = target_labels.clamp(0.0, 1.0)
    base_scores = base_scores.clamp(0.0, 1.0)
    target_bucket = torch.floor(target_labels * 5.0).to(torch.long).clamp(0, 4)
    base_bucket = torch.floor(base_scores * 5.0).to(torch.long).clamp(0, 4)
    protected = base_bucket == target_bucket

    # A correct base bucket gets an interior margin instead of an exact-score
    # anchor, so pointwise learning can still improve within the bucket.
    lower = target_bucket.to(scores.dtype) * 0.2
    upper = (target_bucket + 1).to(scores.dtype) * 0.2
    correct_lower = lower + margin
    correct_upper = upper - margin
    correct_violation = torch.relu(correct_lower - scores).square()
    correct_violation += torch.relu(scores - correct_upper).square()
    correct_violation += max(0.0, anchor_weight) * (scores - base_scores).square()

    # A wrong base bucket may move toward the target, but not farther away.
    lower_drift = torch.relu(base_scores - margin - scores).square()
    upper_drift = torch.relu(scores - base_scores - margin).square()
    directional_violation = torch.where(base_bucket < target_bucket, lower_drift, upper_drift)
    return torch.where(protected, correct_violation, directional_violation).mean()


class BucketBandLoss(torch.nn.Module):
    """Penalize predictions that leave the target score bucket.

    The auxiliary band term resists cross-bucket moves, which is important for
    reviewed hard negatives and ambiguous same-category rows. The center term
    only corrects samples that are already outside their target bucket, so this
    objective does not move a base-model score across a boundary just to reach
    the exact reviewed label. When a frozen base score is supplied, a small
    interior guard protects rows whose base bucket was already correct, while
    a directional guard prevents an already-wrong base score from drifting
    farther away from the target bucket.
    """

    def __init__(
        self,
        model: SentenceTransformer,
        band_weight: float,
        center_weight: float = 1.0,
        base_guard_weight: float = 1.0,
        base_guard_margin: float = 0.02,
        base_guard_anchor_weight: float = BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
    ) -> None:
        super().__init__()
        self.model = model
        self.band_weight = band_weight
        self.center_weight = center_weight
        self.base_guard_weight = base_guard_weight
        self.base_guard_margin = min(0.09, max(0.0, base_guard_margin))
        self.base_guard_anchor_weight = max(0.0, base_guard_anchor_weight)

    def forward(
        self,
        sentence_features: list[dict[str, torch.Tensor]],
        labels: torch.Tensor,
    ) -> torch.Tensor:
        embeddings = [self.model(features)["sentence_embedding"] for features in sentence_features]
        scores = F.cosine_similarity(embeddings[0], embeddings[1])
        if self.band_weight <= 0 and self.center_weight <= 0 and self.base_guard_weight <= 0:
            return scores.sum() * 0.0

        target_labels, base_scores = _unpack_guard_labels(labels, scores)
        # Round-robin padding keeps the midpoint objective from being
        # truncated. Short bucket batches use NaN labels as inert padding so
        # that this schedule change does not silently amplify bucket updates.
        valid = torch.isfinite(target_labels)
        if base_scores is not None:
            valid &= torch.isfinite(base_scores)
        if not torch.any(valid):
            return scores.sum() * 0.0
        scores = scores[valid]
        labels = target_labels[valid].clamp(0.0, 1.0)
        if base_scores is not None:
            base_scores = base_scores[valid]
        bucket_index = torch.floor(labels * 5.0).to(torch.long).clamp(0, 4)
        lower = bucket_index.to(scores.dtype) * 0.2
        upper = (bucket_index + 1).to(scores.dtype) * 0.2
        lower_violation = torch.relu(lower - scores)
        upper_violation = torch.relu(scores - upper)
        violation = lower_violation.square() + upper_violation.square()
        # Treat buckets as a no-degrade region. Ordinary cosine supervision
        # still learns exact labels; this auxiliary objective only repairs
        # predictions that would otherwise be counted in the wrong bucket.
        outside_bucket = (scores < lower) | (scores >= upper)
        if torch.any(outside_bucket):
            center_loss = F.mse_loss(scores[outside_bucket], labels[outside_bucket])
        else:
            center_loss = scores.sum() * 0.0
        base_guard_loss = (
            _base_bucket_guard_penalty(
                scores,
                labels,
                base_scores,
                self.base_guard_margin,
                self.base_guard_anchor_weight,
            )
            if self.base_guard_weight > 0
            else scores.sum() * 0.0
        )
        return (
            (self.center_weight * center_loss)
            + (self.band_weight * violation.mean())
            + (self.base_guard_weight * base_guard_loss)
        )


class BaseGuardedCosineLoss(CosineSimilarityLoss):
    """Keep cosine regression from worsening a frozen base bucket."""

    def __init__(
        self,
        model: SentenceTransformer,
        base_guard_weight: float = 1.0,
        base_guard_margin: float = 0.02,
        base_guard_anchor_weight: float = BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
    ) -> None:
        super().__init__(model)
        self.base_guard_weight = base_guard_weight
        self.base_guard_margin = min(0.09, max(0.0, base_guard_margin))
        self.base_guard_anchor_weight = max(0.0, base_guard_anchor_weight)

    def forward(
        self,
        sentence_features: list[dict[str, torch.Tensor]],
        labels: torch.Tensor,
    ) -> torch.Tensor:
        embeddings = [self.model(features)["sentence_embedding"] for features in sentence_features]
        scores = F.cosine_similarity(embeddings[0], embeddings[1])
        target_labels, base_scores = _unpack_guard_labels(labels, scores)
        valid = torch.isfinite(target_labels)
        if base_scores is not None:
            valid &= torch.isfinite(base_scores)
        if not torch.any(valid):
            return scores.sum() * 0.0
        scores = scores[valid]
        target_labels = target_labels[valid].float()
        if base_scores is not None:
            base_scores = base_scores[valid]
        center_loss = F.mse_loss(scores, target_labels)
        guard_loss = (
            _base_bucket_guard_penalty(
                scores,
                target_labels,
                base_scores,
                self.base_guard_margin,
                self.base_guard_anchor_weight,
            )
            if self.base_guard_weight > 0
            else scores.sum() * 0.0
        )
        return center_loss + (self.base_guard_weight * guard_loss)


class BaseGuardedCoSENTLoss(CoSENTLoss):
    """Keep CoSENT ranking from worsening a frozen base bucket."""

    def __init__(
        self,
        model: SentenceTransformer,
        scale: float = 20.0,
        base_guard_weight: float = 1.0,
        base_guard_margin: float = 0.02,
        base_guard_anchor_weight: float = BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
    ) -> None:
        super().__init__(model=model, scale=scale)
        self.base_guard_weight = base_guard_weight
        self.base_guard_margin = min(0.09, max(0.0, base_guard_margin))
        self.base_guard_anchor_weight = max(0.0, base_guard_anchor_weight)

    def forward(
        self,
        sentence_features: list[dict[str, torch.Tensor]],
        labels: torch.Tensor,
    ) -> torch.Tensor:
        embeddings = [self.model(features)["sentence_embedding"] for features in sentence_features]
        scores = self.similarity_fct(embeddings[0], embeddings[1]).view(-1)
        target_labels, base_scores = _unpack_guard_labels(labels, scores)
        valid = torch.isfinite(target_labels)
        if base_scores is not None:
            valid &= torch.isfinite(base_scores)
        if not torch.any(valid):
            return scores.sum() * 0.0

        scores = scores[valid]
        target_labels = target_labels[valid].float()
        if base_scores is not None:
            base_scores = base_scores[valid]

        pairwise_scores = scores * self.scale
        pairwise_scores = pairwise_scores[:, None] - pairwise_scores[None, :]
        relevant = (target_labels[:, None] < target_labels[None, :]).float()
        pairwise_scores = pairwise_scores - (1 - relevant) * 1e12
        pairwise_scores = torch.cat((pairwise_scores.new_zeros(1), pairwise_scores.reshape(-1)), dim=0)
        ranking_loss = torch.logsumexp(pairwise_scores, dim=0)
        guard_loss = (
            _base_bucket_guard_penalty(
                scores,
                target_labels,
                base_scores,
                self.base_guard_margin,
                self.base_guard_anchor_weight,
            )
            if self.base_guard_weight > 0
            else scores.sum() * 0.0
        )
        return ranking_loss + (self.base_guard_weight * guard_loss)


GUARDED_LOSS_TYPES = (
    MidpointBandLoss,
    BucketBandLoss,
    BaseGuardedCosineLoss,
    BaseGuardedCoSENTLoss,
)


def attach_base_bucket_scores(
    model: SentenceTransformer,
    examples: list[InputExample],
    batch_size: int,
    *,
    vector_cache: dict[str, torch.Tensor] | None = None,
    stats_prefix: str = "bucket_band",
) -> tuple[list[InputExample], dict[str, object]]:
    """Attach frozen base scores using the evaluator's multi-angle score.

    Training examples contain one angle-prefixed pair, while evaluation uses a
    trimmed mean across all production angles. The guard must classify the
    frozen base bucket with that same aggregate score; otherwise a row can be
    marked as base-wrong during training even though its evaluated bucket is
    already correct.
    """
    stats_key = f"{stats_prefix}_base_guard"
    if not examples:
        return examples, {
            f"{stats_key}_examples": 0,
            f"{stats_key}_protected_examples": 0,
            f"{stats_key}_multi_angle_examples": 0,
            f"{stats_key}_fallback_examples": 0,
        }
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    unique_texts = sorted({text for example in examples for text in example.texts})
    base_texts = set()
    has_angle_prefix = False
    for text in unique_texts:
        for angle in ANGLES:
            if text.startswith(angle):
                has_angle_prefix = True
                base_texts.add(text[len(angle):])
                break
        else:
            base_texts.add(text)
    vectors = vector_cache if vector_cache is not None else {}
    was_training = bool(model.training)
    try:
        requested_texts = set(unique_texts)
        if has_angle_prefix:
            requested_texts.update(
                f"{angle}{text}"
                for text in base_texts
                for angle in ANGLES
            )
        missing_texts = sorted(text for text in requested_texts if text not in vectors)
        if missing_texts:
            encoded = model.encode(
                missing_texts,
                batch_size=batch_size,
                convert_to_tensor=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            vectors.update({text: vector for text, vector in zip(missing_texts, encoded)})
        enriched = []
        protected_examples = 0
        multi_angle_examples = 0
        fallback_examples = 0
        for example in examples:
            target = float(example.label)
            text_bases = []
            for text in example.texts[:2]:
                for angle in ANGLES:
                    if text.startswith(angle):
                        text_bases.append(text[len(angle):])
                        break
                else:
                    text_bases.append(text)
            angle_scores = []
            if has_angle_prefix and len(text_bases) == 2 and all(
                f"{angle}{text_bases[0]}" in vectors
                and f"{angle}{text_bases[1]}" in vectors
                for angle in ANGLES
            ):
                for angle in ANGLES:
                    left = torch.as_tensor(vectors[f"{angle}{text_bases[0]}"])
                    right = torch.as_tensor(vectors[f"{angle}{text_bases[1]}"])
                    angle_scores.append(float(torch.dot(left, right).detach().cpu().item()))
                angle_scores.sort()
                base_score = sum(angle_scores[1:-1]) / 3.0
                multi_angle_examples += 1
            else:
                left = torch.as_tensor(vectors[example.texts[0]])
                right = torch.as_tensor(vectors[example.texts[1]])
                base_score = float(torch.dot(left, right).detach().cpu().item())
                fallback_examples += 1
            if not math.isfinite(base_score):
                base_score = 0.0
            base_score = max(0.0, min(1.0, base_score))
            target_bucket = max(0, min(4, int(math.floor(target * 5.0))))
            base_bucket = max(0, min(4, int(math.floor(base_score * 5.0))))
            if target_bucket == base_bucket:
                protected_examples += 1
            enriched.append(
                InputExample(
                    texts=list(example.texts),
                    label=[target, base_score],
                )
            )
    finally:
        model.train(was_training)

    return enriched, {
        f"{stats_key}_examples": len(enriched),
        f"{stats_key}_protected_examples": protected_examples,
        f"{stats_key}_multi_angle_examples": multi_angle_examples,
        f"{stats_key}_fallback_examples": fallback_examples,
    }


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
            if ANGLE_MODE != "none" and PROXY_ANTONYM_MIN_ANGLE_REPEAT > 0:
                if is_proxy_antonym_row(tag, reviewer):
                    repeat = max(repeat, min(len(ANGLES), PROXY_ANTONYM_MIN_ANGLE_REPEAT))
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
            is_bucket_only = row["tag"] in BUCKET_ONLY_TAGS
            if row["tag"] not in COSENT_EXCLUDE_TAGS and not is_bucket_only:
                cosent_examples.append(example)
            if row["tag"] not in COSINE_EXCLUDE_TAGS and not is_bucket_only:
                cosine_examples.append(example)
            if row["tag"] in MIDPOINT_TAGS:
                midpoint_repeat = max(1, int(round(MIDPOINT_REPEAT_BOOST)))
                midpoint_examples.extend(
                    InputExample(texts=list(example.texts), label=example.label)
                    for _ in range(midpoint_repeat)
                )
            if is_bucket_band_row(row):
                bucket_band_examples.extend(
                    InputExample(texts=list(example.texts), label=example.label)
                    for _ in range(bucket_band_repeat_for_row(row))
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
    bucket_band_hard_negative_rows = sum(
        1
        for row in rows
        if is_bucket_band_row(row) and row["tag"] in HARD_NEG_TAGS
    )
    bucket_band_hard_negative_examples_before_repeat = sum(
        row["repeat"]
        for row in rows
        if is_bucket_band_row(row) and row["tag"] in HARD_NEG_TAGS
    )
    bucket_band_hard_negative_examples_after_repeat = sum(
        row["repeat"] * bucket_band_repeat_for_row(row)
        for row in rows
        if is_bucket_band_row(row) and row["tag"] in HARD_NEG_TAGS
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
    proxy_antonym_count = sum(1 for row in rows if is_proxy_antonym_row(row["tag"], row["reviewer"]))
    proxy_antonym_repeats = sum(
        row["repeat"] for row in rows if is_proxy_antonym_row(row["tag"], row["reviewer"])
    )
    cosent_excluded_rows = sum(1 for row in rows if row["tag"] in COSENT_EXCLUDE_TAGS)
    cosent_excluded_examples = sum(row["repeat"] for row in rows if row["tag"] in COSENT_EXCLUDE_TAGS)
    cosine_excluded_rows = sum(1 for row in rows if row["tag"] in COSINE_EXCLUDE_TAGS)
    cosine_excluded_examples = sum(row["repeat"] for row in rows if row["tag"] in COSINE_EXCLUDE_TAGS)
    bucket_only_rows = sum(1 for row in rows if row["tag"] in BUCKET_ONLY_TAGS)
    bucket_only_examples = sum(row["repeat"] for row in rows if row["tag"] in BUCKET_ONLY_TAGS)
    cosent_bucket_only_excluded_rows = bucket_only_rows
    cosent_bucket_only_excluded_examples = bucket_only_examples
    cosine_bucket_only_excluded_rows = bucket_only_rows
    cosine_bucket_only_excluded_examples = bucket_only_examples
    contrastive_bucket_only_excluded_rows = bucket_only_rows
    contrastive_bucket_only_excluded_examples = bucket_only_examples
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
        "bucket_only_tags": sorted(BUCKET_ONLY_TAGS),
        "bucket_only_rows": bucket_only_rows,
        "bucket_only_examples_after_repeat": bucket_only_examples,
        "cosent_bucket_only_excluded_rows": cosent_bucket_only_excluded_rows,
        "cosent_bucket_only_excluded_examples_after_repeat": cosent_bucket_only_excluded_examples,
        "cosine_bucket_only_excluded_rows": cosine_bucket_only_excluded_rows,
        "cosine_bucket_only_excluded_examples_after_repeat": cosine_bucket_only_excluded_examples,
        "contrastive_bucket_only_excluded_rows": contrastive_bucket_only_excluded_rows,
        "contrastive_bucket_only_excluded_examples_after_repeat": contrastive_bucket_only_excluded_examples,
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
        "bucket_band_hard_negative_repeat": BUCKET_BAND_HARD_NEG_REPEAT,
        "bucket_band_rows": bucket_band_rows,
        "bucket_band_hard_negative_rows": bucket_band_hard_negative_rows,
        "bucket_band_hard_negative_examples_before_repeat": bucket_band_hard_negative_examples_before_repeat,
        "bucket_band_hard_negative_examples_after_repeat": bucket_band_hard_negative_examples_after_repeat,
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
        "proxy_antonym_min_angle_repeat": PROXY_ANTONYM_MIN_ANGLE_REPEAT,
        "proxy_antonym_rows": proxy_antonym_count,
        "proxy_antonym_examples_after_repeat": proxy_antonym_repeats,
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


def materialize_padded_objectives(
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    batch_size: int,
    protected_min_batches: int = 0,
    sampling_seed: int | None = None,
) -> list[tuple[list[InputExample], torch.nn.Module]]:
    """Freeze each objective after padding it to the protected batch budget.

    When a sample seed is supplied, materialize random data loaders with a
    dedicated generator. This keeps the effective truncated prefix stable
    across model seeds while leaving optimizer/model randomness independent.
    """
    def identity(batch):
        return batch

    target_batches = round_robin_batch_budget(train_objectives, protected_min_batches)
    target_examples = target_batches * batch_size
    padded_objectives = []
    for objective_idx, (data_loader, loss_fn) in enumerate(train_objectives):
        data_loader.collate_fn = identity
        materialization_loader = data_loader
        if sampling_seed is not None and isinstance(getattr(data_loader, "sampler", None), RandomSampler):
            generator = torch.Generator()
            generator.manual_seed(int(sampling_seed) + objective_idx)
            materialization_loader = DataLoader(
                data_loader.dataset,
                batch_size=data_loader.batch_size,
                sampler=RandomSampler(data_loader.dataset, generator=generator),
                num_workers=data_loader.num_workers,
                pin_memory=data_loader.pin_memory,
                drop_last=data_loader.drop_last,
                collate_fn=identity,
            )
        raw_examples = []
        for batch in materialization_loader:
            raw_examples.extend(batch)
        texts = [tuple(example.texts) for example in raw_examples]
        labels = [example.label for example in raw_examples]
        pad_label = float("nan") if isinstance(loss_fn, GUARDED_LOSS_TYPES) else None
        if isinstance(loss_fn, GUARDED_LOSS_TYPES) and any(
            isinstance(label, (list, tuple)) and len(label) >= 2 for label in labels
        ):
            pad_label = [float("nan"), float("nan")]
        texts, labels = pad_examples_to_batch_budget(
            texts,
            labels,
            target_examples,
            pad_label=pad_label,
        )
        padded_objectives.append(
            (
                [InputExample(texts=list(text), label=label) for text, label in zip(texts, labels)],
                loss_fn,
            )
        )
    return padded_objectives


def fit_with_explicit_trainer(
    model: SentenceTransformer,
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    epochs: int,
    batch_size: int,
    warmup_steps: int,
    learning_rate: float,
    device: str,
    protected_min_batches: int = 0,
) -> None:
    padded_objectives = materialize_padded_objectives(
        train_objectives,
        batch_size=batch_size,
        protected_min_batches=protected_min_batches,
        sampling_seed=SAMPLE_SEED,
    )
    datasets: dict[str, Dataset] = {}
    losses: dict[str, torch.nn.Module] = {}
    for idx, (objective_examples, loss_fn) in enumerate(padded_objectives, start=1):
        texts = [example.texts for example in objective_examples]
        labels = [example.label for example in objective_examples]
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
        seed=SEED,
        use_cpu=device == "cpu",
        no_cuda=device == "cpu",
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


def fit_with_sentence_transformer_fit(
    model: SentenceTransformer,
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    epochs: int,
    batch_size: int,
    warmup_steps: int,
    learning_rate: float,
    protected_min_batches: int = 0,
) -> None:
    """Run the current SentenceTransformer.fit round-robin schedule.

    The installed SentenceTransformer.fit implementation uses the new Trainer
    path, where steps_per_epoch is the total number of optimizer updates. The
    padded round-robin datasets already provide one objective batch per cycle,
    so the total is the per-objective budget multiplied by objective_count.
    """
    padded_objectives = materialize_padded_objectives(
        train_objectives,
        batch_size=batch_size,
        protected_min_batches=protected_min_batches,
        sampling_seed=SAMPLE_SEED,
    )
    padded_loaders = [
        (
            DataLoader(
                objective_examples,
                # The source loader was already shuffled while it was
                # materialized; avoid adding a second pre-Trainer shuffle.
                shuffle=False,
                batch_size=batch_size,
                num_workers=0,
                pin_memory=False,
            ),
            loss_fn,
        )
        for objective_examples, loss_fn in padded_objectives
    ]
    # RoundRobinBatchSampler consumes one batch from each objective per cycle;
    # SentenceTransformer.fit expects the resulting total update count.
    steps_per_epoch = round_robin_steps_per_epoch(
        train_objectives,
        protected_min_batches=protected_min_batches,
    )
    model.fit(
        train_objectives=padded_loaders,
        epochs=epochs,
        steps_per_epoch=steps_per_epoch if epochs == 1 else None,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": learning_rate},
        show_progress_bar=True,
    )


def fit_with_legacy_model_fit(
    model: SentenceTransformer,
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    epochs: int,
    batch_size: int,
    warmup_steps: int,
    learning_rate: float,
    protected_min_batches: int = 0,
) -> None:
    """Compatibility entry point for callers using the former function name."""
    fit_with_sentence_transformer_fit(
        model=model,
        train_objectives=train_objectives,
        epochs=epochs,
        batch_size=batch_size,
        warmup_steps=warmup_steps,
        learning_rate=learning_rate,
        protected_min_batches=protected_min_batches,
    )


def round_robin_steps_per_epoch(
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    protected_min_batches: int = 0,
) -> int:
    """Match ROUND_ROBIN updates while protecting the midpoint objective."""
    return round_robin_batch_budget(train_objectives, protected_min_batches) * len(train_objectives)


def round_robin_batch_budget(
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    protected_min_batches: int = 0,
) -> int:
    """Return the shortest objective length, never below a protected objective."""
    if not train_objectives:
        raise ValueError("at least one training objective is required")
    if protected_min_batches < 0:
        raise ValueError("protected_min_batches must be non-negative")
    batches_per_objective = [len(data_loader) for data_loader, _ in train_objectives]
    if any(batch_count <= 0 for batch_count in batches_per_objective):
        raise ValueError("every training objective must contain at least one batch")
    return max(min(batches_per_objective), protected_min_batches)


def pad_examples_to_batch_budget(
    texts: list[tuple[str, ...]],
    labels: list[float | list[float]],
    target_examples: int,
    pad_label: float | list[float] | None = None,
) -> tuple[list[tuple[str, ...]], list[float | list[float]]]:
    """Pad short objectives, optionally marking synthetic labels as inert."""
    if len(texts) != len(labels):
        raise ValueError("texts and labels must have the same length")
    if target_examples <= len(texts):
        return texts, labels
    if not texts:
        raise ValueError("cannot pad an empty objective")

    extra = target_examples - len(texts)
    full_repeats, remainder = divmod(extra, len(texts))
    padded_labels = (
        [pad_label] * extra
        if pad_label is not None
        else labels * full_repeats + labels[:remainder]
    )
    return (
        texts + texts * full_repeats + texts[:remainder],
        labels + padded_labels,
    )


def round_robin_schedule_stats(
    train_objectives: list[tuple[DataLoader, torch.nn.Module]],
    batch_size: int,
    protected_min_batches: int = 0,
) -> dict[str, int]:
    """Describe the effective schedule after short objectives are padded."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    target_batches = round_robin_batch_budget(train_objectives, protected_min_batches)
    padded_examples = 0
    noop_padded_examples = 0
    for data_loader, loss_fn in train_objectives:
        dataset = getattr(data_loader, "dataset", None)
        try:
            example_count = len(dataset) if dataset is not None else len(data_loader) * batch_size
        except TypeError:
            example_count = len(data_loader) * batch_size
        objective_padding = max(0, target_batches * batch_size - example_count)
        padded_examples += objective_padding
        if isinstance(loss_fn, GUARDED_LOSS_TYPES):
            noop_padded_examples += objective_padding
    return {
        "original_min_batches": min(len(data_loader) for data_loader, _ in train_objectives),
        "target_batches_per_objective": target_batches,
        "protected_min_batches": protected_min_batches,
        "padded_examples": padded_examples,
        "noop_padded_examples": noop_padded_examples,
        "steps_per_epoch": target_batches * len(train_objectives),
    }


def seed_training(seed: int) -> None:
    """Keep model and loader randomness tied to the per-round training seed."""
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def write_train_stats(stats: dict) -> None:
    if not TRAIN_STATS_JSON:
        return
    stats_path = Path(TRAIN_STATS_JSON)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    stats["device"] = device
    trainer_backend = "SentenceTransformerTrainer" if device == "cpu" else "SentenceTransformer.fit"
    trainer_seed = SEED if device == "cpu" else LEGACY_MODEL_FIT_SEED
    stats["trainer_backend"] = trainer_backend
    stats["trainer_seed"] = trainer_seed
    stats["seed"] = SEED
    stats["epochs"] = EPOCHS
    stats["batch_size"] = BATCH_SIZE
    stats["learning_rate"] = LEARNING_RATE
    if len(examples) < MIN_TRAIN_EXAMPLES:
        raise SystemExit(f"not enough training examples (<{MIN_TRAIN_EXAMPLES})")
    if LOSS_MODE in {"cosent", "mixed", "mixed_contrastive"} and not cosent_examples:
        raise SystemExit("CoSENT objective has no examples after SEM_COSENT_EXCLUDE_TAGS filtering")
    if LOSS_MODE in {"cosine", "mixed", "mixed_contrastive"} and not cosine_examples:
        raise SystemExit("Cosine objective has no examples after SEM_COSINE_EXCLUDE_TAGS filtering")

    print(f"base_model={BASE_MODEL}")
    print(f"output_model={OUTPUT_MODEL}")
    print(f"device={device}")
    print(f"trainer_backend={trainer_backend} trainer_seed={trainer_seed}")
    print(f"epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}")
    print(f"warmup_ratio={WARMUP_RATIO} seed={SEED} sample_seed={SAMPLE_SEED} scale={SCALE}")
    print(f"hard_neg_boost={HARD_NEG_BOOST} max_repeat={MAX_REPEAT} angle_mode={ANGLE_MODE} loss_mode={LOSS_MODE}")
    print(f"cosent_exclude_tags={','.join(sorted(COSENT_EXCLUDE_TAGS)) or '-'}")
    print(f"cosine_exclude_tags={','.join(sorted(COSINE_EXCLUDE_TAGS)) or '-'}")
    print(f"bucket_only_tags={','.join(sorted(BUCKET_ONLY_TAGS)) or '-'}")
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
        f"bucket_band_hard_negative_repeat={BUCKET_BAND_HARD_NEG_REPEAT} "
        f"bucket_band_examples={len(bucket_band_examples)}"
    )
    print(f"required_antonym_min_angle_repeat={REQUIRED_ANTONYM_MIN_ANGLE_REPEAT}")
    print(f"priority_antonym_min_angle_repeat={PRIORITY_ANTONYM_MIN_ANGLE_REPEAT}")
    print(f"proxy_antonym_min_angle_repeat={PROXY_ANTONYM_MIN_ANGLE_REPEAT}")
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

    model = SentenceTransformer(
        BASE_MODEL,
        device=device,
        local_files_only=True,
    )
    bucket_guard_stats = {
        "bucket_band_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "bucket_band_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "bucket_band_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "bucket_band_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "bucket_band_base_guard_examples": 0,
        "bucket_band_base_guard_protected_examples": 0,
    }
    cosine_guard_stats = {
        "cosine_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "cosine_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "cosine_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "cosine_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "cosine_base_guard_examples": 0,
        "cosine_base_guard_protected_examples": 0,
    }
    cosent_guard_stats = {
        "cosent_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "cosent_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "cosent_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "cosent_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "cosent_base_guard_examples": 0,
        "cosent_base_guard_protected_examples": 0,
    }
    midpoint_guard_stats = {
        "midpoint_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "midpoint_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "midpoint_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "midpoint_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "midpoint_base_guard_examples": 0,
        "midpoint_base_guard_protected_examples": 0,
    }
    base_vector_cache: dict[str, torch.Tensor] = {}
    if BUCKET_BAND_BASE_GUARD and cosent_examples:
        cosent_examples, attached_stats = attach_base_bucket_scores(
            model,
            cosent_examples,
            BATCH_SIZE,
            vector_cache=base_vector_cache,
            stats_prefix="cosent",
        )
        cosent_guard_stats.update(attached_stats)
    if BUCKET_BAND_BASE_GUARD and midpoint_examples:
        midpoint_examples, attached_stats = attach_base_bucket_scores(
            model,
            midpoint_examples,
            BATCH_SIZE,
            vector_cache=base_vector_cache,
            stats_prefix="midpoint",
        )
        midpoint_guard_stats.update(attached_stats)
    if BUCKET_BAND_BASE_GUARD and bucket_band_examples:
        bucket_band_examples, attached_stats = attach_base_bucket_scores(
            model,
            bucket_band_examples,
            BATCH_SIZE,
            vector_cache=base_vector_cache,
        )
        bucket_guard_stats.update(attached_stats)
    if BUCKET_BAND_BASE_GUARD and cosine_examples:
        cosine_examples, attached_stats = attach_base_bucket_scores(
            model,
            cosine_examples,
            BATCH_SIZE,
            vector_cache=base_vector_cache,
            stats_prefix="cosine",
        )
        cosine_guard_stats.update(attached_stats)
    stats.update(bucket_guard_stats)
    stats.update(cosine_guard_stats)
    stats.update(cosent_guard_stats)
    stats.update(midpoint_guard_stats)
    print(
        f"cosent_base_guard={BUCKET_BAND_BASE_GUARD} "
        f"weight={BUCKET_BAND_BASE_GUARD_WEIGHT} "
        f"margin={BUCKET_BAND_BASE_GUARD_MARGIN} "
        f"anchor_weight={BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT} "
        f"protected_examples={cosent_guard_stats['cosent_base_guard_protected_examples']}"
    )
    print(
        f"midpoint_base_guard={BUCKET_BAND_BASE_GUARD} "
        f"weight={BUCKET_BAND_BASE_GUARD_WEIGHT} "
        f"margin={BUCKET_BAND_BASE_GUARD_MARGIN} "
        f"anchor_weight={BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT} "
        f"protected_examples={midpoint_guard_stats['midpoint_base_guard_protected_examples']}"
    )
    print(
        f"bucket_band_base_guard={BUCKET_BAND_BASE_GUARD} "
        f"weight={BUCKET_BAND_BASE_GUARD_WEIGHT} "
        f"margin={BUCKET_BAND_BASE_GUARD_MARGIN} "
        f"anchor_weight={BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT} "
        f"protected_examples={bucket_guard_stats['bucket_band_base_guard_protected_examples']}"
    )
    print(
        f"cosine_base_guard={BUCKET_BAND_BASE_GUARD} "
        f"weight={BUCKET_BAND_BASE_GUARD_WEIGHT} "
        f"margin={BUCKET_BAND_BASE_GUARD_MARGIN} "
        f"anchor_weight={BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT} "
        f"protected_examples={cosine_guard_stats['cosine_base_guard_protected_examples']}"
    )
    print("train_stats=" + json.dumps(stats, ensure_ascii=False))
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
        train_objectives = [
            (
                cosine_loader,
                BaseGuardedCosineLoss(
                    model=model,
                    base_guard_weight=(
                        BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                    ),
                    base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                ),
            )
        ]
    elif LOSS_MODE == "mixed":
        cosine_loader = DataLoader(
            list(cosine_examples),
            shuffle=True,
            batch_size=BATCH_SIZE,
            num_workers=0,
            pin_memory=False,
        )
        train_objectives = [
            (
                cosent_loader,
                BaseGuardedCoSENTLoss(
                    model=model,
                    scale=SCALE,
                    base_guard_weight=(
                        BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                    ),
                    base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                ),
            ),
            (
                cosine_loader,
                BaseGuardedCosineLoss(
                    model=model,
                    base_guard_weight=(
                        BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                    ),
                    base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                ),
            ),
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
                            base_guard_weight=(
                                BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                            ),
                            base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
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
                        base_guard_weight=(
                            BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                        ),
                        base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
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
            (
                cosent_loader,
                BaseGuardedCoSENTLoss(
                    model=model,
                    scale=SCALE,
                    base_guard_weight=(
                        BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                    ),
                    base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                ),
            ),
            (
                cosine_loader,
                BaseGuardedCosineLoss(
                    model=model,
                    base_guard_weight=(
                        BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                    ),
                    base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                ),
            ),
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
                            base_guard_weight=(
                                BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                            ),
                            base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
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
                        base_guard_weight=(
                            BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                        ),
                        base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                    ),
                )
            )
    else:
        train_objectives = [
            (
                cosent_loader,
                BaseGuardedCoSENTLoss(
                    model=model,
                    scale=SCALE,
                    base_guard_weight=(
                        BUCKET_BAND_BASE_GUARD_WEIGHT if BUCKET_BAND_BASE_GUARD else 0.0
                    ),
                    base_guard_margin=BUCKET_BAND_BASE_GUARD_MARGIN,
                ),
            )
        ]

    protected_min_batches = (
        len(midpoint_loader)
        if any(isinstance(loss_fn, MidpointBandLoss) for _, loss_fn in train_objectives)
        else 0
    )
    schedule_stats = round_robin_schedule_stats(
        train_objectives,
        batch_size=BATCH_SIZE,
        protected_min_batches=protected_min_batches,
    )
    steps_per_epoch = schedule_stats["steps_per_epoch"]
    total_steps = steps_per_epoch * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)
    fit_steps_per_epoch = (
        steps_per_epoch
        if trainer_backend == "SentenceTransformer.fit" and EPOCHS == 1
        else None
    )
    fit_warmup_steps = warmup_steps if trainer_backend == "SentenceTransformer.fit" else None
    print(
        f"objective_count={len(train_objectives)} "
        f"round_robin_steps_per_epoch={steps_per_epoch} "
        f"round_robin_target_batches_per_objective={schedule_stats['target_batches_per_objective']} "
        f"round_robin_padded_examples={schedule_stats['padded_examples']} "
        f"round_robin_noop_padded_examples={schedule_stats['noop_padded_examples']} "
        f"fit_steps_per_epoch={fit_steps_per_epoch} "
        f"fit_warmup_steps={fit_warmup_steps} "
        f"total_steps={total_steps} warmup_steps={warmup_steps}"
    )
    stats["objective_count"] = len(train_objectives)
    stats["round_robin_steps_per_epoch"] = steps_per_epoch
    stats["round_robin_original_min_batches"] = schedule_stats["original_min_batches"]
    stats["round_robin_target_batches_per_objective"] = schedule_stats["target_batches_per_objective"]
    stats["round_robin_protected_min_batches"] = schedule_stats["protected_min_batches"]
    stats["round_robin_padded_examples"] = schedule_stats["padded_examples"]
    stats["round_robin_noop_padded_examples"] = schedule_stats["noop_padded_examples"]
    stats["fit_steps_per_epoch"] = fit_steps_per_epoch
    stats["fit_warmup_steps"] = fit_warmup_steps
    stats["total_steps"] = total_steps
    stats["warmup_steps"] = warmup_steps
    write_train_stats(stats)
    print(f"Starting supervised {LOSS_MODE} training...")

    started = time.time()
    if device == "cpu":
        fit_with_explicit_trainer(
            model=model,
            train_objectives=train_objectives,
            epochs=EPOCHS,
            batch_size=BATCH_SIZE,
            warmup_steps=warmup_steps,
            learning_rate=LEARNING_RATE,
            device=device,
            protected_min_batches=protected_min_batches,
        )
    else:
        fit_with_sentence_transformer_fit(
            model=model,
            train_objectives=train_objectives,
            epochs=EPOCHS,
            batch_size=BATCH_SIZE,
            warmup_steps=fit_warmup_steps,
            learning_rate=LEARNING_RATE,
            protected_min_batches=protected_min_batches,
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
        "round_robin_original_min_batches": schedule_stats["original_min_batches"],
        "round_robin_target_batches_per_objective": schedule_stats["target_batches_per_objective"],
        "round_robin_protected_min_batches": schedule_stats["protected_min_batches"],
        "round_robin_padded_examples": schedule_stats["padded_examples"],
        "round_robin_noop_padded_examples": schedule_stats["noop_padded_examples"],
        "fit_steps_per_epoch": fit_steps_per_epoch,
        "fit_warmup_steps": fit_warmup_steps,
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
        "bucket_band_hard_negative_repeat": BUCKET_BAND_HARD_NEG_REPEAT,
        "bucket_band_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "bucket_band_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "bucket_band_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "bucket_band_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "bucket_band_base_guard_examples": stats["bucket_band_base_guard_examples"],
        "bucket_band_base_guard_protected_examples": stats[
            "bucket_band_base_guard_protected_examples"
        ],
        "cosine_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "cosine_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "cosine_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "cosine_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "cosine_base_guard_examples": stats["cosine_base_guard_examples"],
        "cosine_base_guard_protected_examples": stats[
            "cosine_base_guard_protected_examples"
        ],
        "cosent_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "cosent_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "cosent_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "cosent_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "cosent_base_guard_examples": stats["cosent_base_guard_examples"],
        "cosent_base_guard_protected_examples": stats[
            "cosent_base_guard_protected_examples"
        ],
        "midpoint_base_guard_enabled": BUCKET_BAND_BASE_GUARD,
        "midpoint_base_guard_weight": BUCKET_BAND_BASE_GUARD_WEIGHT,
        "midpoint_base_guard_margin": BUCKET_BAND_BASE_GUARD_MARGIN,
        "midpoint_base_guard_anchor_weight": BUCKET_BAND_BASE_GUARD_ANCHOR_WEIGHT,
        "midpoint_base_guard_examples": stats["midpoint_base_guard_examples"],
        "midpoint_base_guard_protected_examples": stats[
            "midpoint_base_guard_protected_examples"
        ],
        "bucket_band_hard_negative_rows": stats["bucket_band_hard_negative_rows"],
        "bucket_band_hard_negative_examples_before_repeat": stats[
            "bucket_band_hard_negative_examples_before_repeat"
        ],
        "bucket_band_hard_negative_examples_after_repeat": stats[
            "bucket_band_hard_negative_examples_after_repeat"
        ],
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
        "priority_antonym_min_angle_repeat": PRIORITY_ANTONYM_MIN_ANGLE_REPEAT,
        "proxy_antonym_min_angle_repeat": PROXY_ANTONYM_MIN_ANGLE_REPEAT,
        "min_train_examples": MIN_TRAIN_EXAMPLES,
        "seed": SEED,
        "sample_seed": SAMPLE_SEED,
        "device": device,
        "trainer_backend": trainer_backend,
        "trainer_seed": trainer_seed,
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
