from __future__ import annotations

import csv
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

import torch
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
EPOCHS = int(os.getenv("SEM_EPOCHS", "2"))
BATCH_SIZE = int(os.getenv("SEM_BATCH_SIZE", "8"))
LEARNING_RATE = float(os.getenv("SEM_LR", os.getenv("SEM_LEARNING_RATE", "8e-6")))
WARMUP_RATIO = float(os.getenv("SEM_WARMUP_RATIO", "0.1"))
MAX_TRAIN_ROWS = int(os.getenv("SEM_MAX_TRAIN_ROWS", "0"))
SEED = int(os.getenv("SEM_SEED", "20260515"))
DEVICE = os.getenv("SEM_DEVICE", "").strip().lower()
SCALE = float(os.getenv("SEM_COSENT_SCALE", "20.0"))
HARD_NEG_BOOST = float(os.getenv("SEM_HARD_NEG_BOOST", "2.0"))
MAX_REPEAT = int(os.getenv("SEM_MAX_REPEAT", "5"))
ANGLE_MODE = os.getenv("SEM_ANGLE_MODE", "cycle").strip().lower()
LOSS_MODE = os.getenv("SEM_LOSS_MODE", "mixed").strip().lower()
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

ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]

HARD_NEG_TAGS = {
    "collocation_not_equivalent",
    "function_word_low",
    "function_word_vs_real_low",
    "hard_negative_low",
    "hard_negative_mid",
    "cross_category_low",
    "cross_category_negative",
    "same_category_but_far",
    "nonsense_low",
}

TAG_REPEAT_BOOSTS = {
    "alias_synonym_high": 1.5,
    "near_synonym_high": 1.5,
    "hint_like_high": 1.5,
    "same_category_mid": 1.5,
    "same_category_strong": 1.5,
    "related_mid": 1.25,
}

CONTRASTIVE_POSITIVE_TAGS = {
    "alias_synonym_high",
    "near_synonym_high",
    "hint_like_high",
}


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
            if row["sample_weight"] >= PIN_WEIGHT_THRESHOLD or row["reviewer"].startswith("nightly_patch"):
                pinned.append(row)
            else:
                pool.append(row)
    else:
        pool = list(rows)
    if len(pinned) >= limit:
        rng.shuffle(pinned)
        return pinned[:limit]

    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in pool:
        bucket_key = (row["tag"] or "unknown", score_bin(row["score"]))
        buckets.setdefault(bucket_key, []).append(row)
    for bucket_rows in buckets.values():
        rng.shuffle(bucket_rows)

    selected = list(pinned)
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
    return row["sample_weight"] >= PIN_WEIGHT_THRESHOLD or row["reviewer"].startswith("nightly_patch")


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


def load_examples(path: Path, seed: int) -> tuple[list[InputExample], list[InputExample], dict]:
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
            if ANGLE_MODE != "none" and MIN_ANGLE_REPEAT_FOR_HIGH_VALUE > 0:
                min_angle_repeat = min(len(ANGLES), MIN_ANGLE_REPEAT_FOR_HIGH_VALUE)
                if sample_weight >= PIN_WEIGHT_THRESHOLD or reviewer.startswith("nightly_patch") or tag in TAG_REPEAT_BOOSTS:
                    repeat = max(repeat, min_angle_repeat)
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
    contrastive_examples = []
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
            examples.append(
                InputExample(
                    texts=[answer_text, input_text],
                    label=row["score"],
                )
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
    rng.shuffle(contrastive_examples)

    tag_counts = Counter(row["tag"] for row in rows)
    contrastive_tag_counts = Counter()
    contrastive_label_counts = Counter()
    for row in rows:
        binary_label = contrastive_label(row)
        if binary_label is not None:
            contrastive_tag_counts[row["tag"]] += row["repeat"]
            contrastive_label_counts[str(int(binary_label))] += row["repeat"]
    score_buckets = Counter((int(row["score"] * 100) // 10) * 10 for row in rows)
    hard_count = sum(1 for row in rows if row["tag"] in HARD_NEG_TAGS)
    protected_count = sum(1 for row in rows if row["tag"] in TAG_REPEAT_BOOSTS)
    pinned_count = sum(1 for row in rows if is_high_value_row(row))
    angle_covered_count = sum(1 for row in rows if row["repeat"] >= len(ANGLES))
    stats = {
        "source_rows_before_limit": source_rows_before_limit,
        "source_rows": len(rows),
        "train_examples_after_repeat": len(examples),
        "contrastive_examples_after_repeat": len(contrastive_examples),
        "contrastive_scope": CONTRASTIVE_SCOPE,
        "contrastive_pos_threshold": CONTRASTIVE_POS_THRESHOLD,
        "contrastive_neg_threshold": CONTRASTIVE_NEG_THRESHOLD,
        "contrastive_label_counts": dict(contrastive_label_counts),
        "contrastive_tag_counts": dict(contrastive_tag_counts.most_common(30)),
        "hard_negative_rows": hard_count,
        "hard_negative_ratio": round(hard_count / max(len(rows), 1), 6),
        "protected_positive_rows": protected_count,
        "pinned_high_value_rows": pinned_count,
        "full_angle_coverage_rows": angle_covered_count,
        "angle_mode": ANGLE_MODE,
        "tag_counts": dict(tag_counts.most_common(30)),
        "score_buckets": {str(k): v for k, v in sorted(score_buckets.items())},
    }
    return examples, contrastive_examples, stats


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


def main() -> None:
    if not TRAIN_CSV.exists():
        raise SystemExit(f"missing: {TRAIN_CSV}")

    device = resolve_device()
    examples, contrastive_examples, stats = load_examples(TRAIN_CSV, SEED)
    if len(examples) < MIN_TRAIN_EXAMPLES:
        raise SystemExit(f"not enough training examples (<{MIN_TRAIN_EXAMPLES})")

    print(f"base_model={BASE_MODEL}")
    print(f"output_model={OUTPUT_MODEL}")
    print(f"device={device}")
    print(f"epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}")
    print(f"warmup_ratio={WARMUP_RATIO} seed={SEED} scale={SCALE}")
    print(f"hard_neg_boost={HARD_NEG_BOOST} max_repeat={MAX_REPEAT} angle_mode={ANGLE_MODE} loss_mode={LOSS_MODE}")
    print(
        "contrastive_margin="
        f"{CONTRASTIVE_MARGIN} contrastive_pos_threshold={CONTRASTIVE_POS_THRESHOLD} "
        f"contrastive_neg_threshold={CONTRASTIVE_NEG_THRESHOLD} contrastive_scope={CONTRASTIVE_SCOPE}"
    )
    print(f"pin_high_value_rows={PIN_HIGH_VALUE_ROWS} pin_weight_threshold={PIN_WEIGHT_THRESHOLD}")
    print(f"min_angle_repeat_for_high_value={MIN_ANGLE_REPEAT_FOR_HIGH_VALUE}")
    print("train_stats=" + json.dumps(stats, ensure_ascii=False))

    model = SentenceTransformer(
        BASE_MODEL,
        device=device,
        local_files_only=True,
    )
    train_loader = DataLoader(
        examples,
        shuffle=True,
        batch_size=BATCH_SIZE,
        num_workers=0,
        pin_memory=False,
    )
    if LOSS_MODE == "cosine":
        train_objectives = [(train_loader, CosineSimilarityLoss(model=model))]
    elif LOSS_MODE == "mixed":
        cosine_loader = DataLoader(
            list(examples),
            shuffle=True,
            batch_size=BATCH_SIZE,
            num_workers=0,
            pin_memory=False,
        )
        train_objectives = [
            (train_loader, CoSENTLoss(model=model, scale=SCALE)),
            (cosine_loader, CosineSimilarityLoss(model=model)),
        ]
    elif LOSS_MODE == "mixed_contrastive":
        if not contrastive_examples:
            raise SystemExit("mixed_contrastive requires at least one positive or negative contrastive example")
        cosine_loader = DataLoader(
            list(examples),
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
            (train_loader, CoSENTLoss(model=model, scale=SCALE)),
            (cosine_loader, CosineSimilarityLoss(model=model)),
            (contrastive_loader, OnlineContrastiveLoss(model=model, margin=CONTRASTIVE_MARGIN)),
        ]
    else:
        train_objectives = [(train_loader, CoSENTLoss(model=model, scale=SCALE))]

    total_steps = sum(len(loader) for loader, _ in train_objectives) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)
    print(f"total_steps={total_steps} warmup_steps={warmup_steps}")
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
        "total_steps": total_steps,
        "scale": SCALE,
        "loss_mode": LOSS_MODE,
        "contrastive_margin": CONTRASTIVE_MARGIN,
        "contrastive_scope": CONTRASTIVE_SCOPE,
        "hard_neg_boost": HARD_NEG_BOOST,
        "max_repeat": MAX_REPEAT,
        "angle_mode": ANGLE_MODE,
        "pin_high_value_rows": PIN_HIGH_VALUE_ROWS,
        "pin_weight_threshold": PIN_WEIGHT_THRESHOLD,
        "min_angle_repeat_for_high_value": MIN_ANGLE_REPEAT_FOR_HIGH_VALUE,
        "min_train_examples": MIN_TRAIN_EXAMPLES,
        "seed": SEED,
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
