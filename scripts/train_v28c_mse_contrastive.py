import csv
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

import torch
from sentence_transformers import InputExample, SentenceTransformer
from sentence_transformers.losses import CoSENTLoss
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

HARD_NEG_TAGS = {
    "antonym_low",
    "function_word_low",
    "function_word_vs_real_low",
    "hard_negative_low",
    "hard_negative_mid",
    "cross_category_low",
    "cross_category_negative",
    "nonsense_low",
}


def resolve_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_examples(path: Path, seed: int) -> tuple[list[InputExample], dict]:
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
            boost = HARD_NEG_BOOST if tag in HARD_NEG_TAGS else 1.0
            repeat = max(1, min(MAX_REPEAT, int(round(sample_weight * boost))))
            rows.append(
                {
                    "answer": answer,
                    "user_input": user_input,
                    "score": score,
                    "tag": tag,
                    "repeat": repeat,
                }
            )

    rng = random.Random(seed)
    rng.shuffle(rows)
    if MAX_TRAIN_ROWS > 0 and len(rows) > MAX_TRAIN_ROWS:
        rows = rows[:MAX_TRAIN_ROWS]

    examples = []
    for row in rows:
        for _ in range(row["repeat"]):
            examples.append(
                InputExample(
                    texts=[row["answer"], row["user_input"]],
                    label=row["score"],
                )
            )
    rng.shuffle(examples)

    tag_counts = Counter(row["tag"] for row in rows)
    score_buckets = Counter((int(row["score"] * 100) // 10) * 10 for row in rows)
    hard_count = sum(1 for row in rows if row["tag"] in HARD_NEG_TAGS)
    stats = {
        "source_rows": len(rows),
        "train_examples_after_repeat": len(examples),
        "hard_negative_rows": hard_count,
        "hard_negative_ratio": round(hard_count / max(len(rows), 1), 6),
        "tag_counts": dict(tag_counts.most_common(30)),
        "score_buckets": {str(k): v for k, v in sorted(score_buckets.items())},
    }
    return examples, stats


def main() -> None:
    if not TRAIN_CSV.exists():
        raise SystemExit(f"missing: {TRAIN_CSV}")

    device = resolve_device()
    examples, stats = load_examples(TRAIN_CSV, SEED)
    if len(examples) < 200:
        raise SystemExit("not enough training examples (<200)")

    print(f"base_model={BASE_MODEL}")
    print(f"output_model={OUTPUT_MODEL}")
    print(f"device={device}")
    print(f"epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}")
    print(f"warmup_ratio={WARMUP_RATIO} seed={SEED} scale={SCALE}")
    print(f"hard_neg_boost={HARD_NEG_BOOST} max_repeat={MAX_REPEAT}")
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
    train_loss = CoSENTLoss(model=model, scale=SCALE)

    total_steps = len(train_loader) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)
    print(f"total_steps={total_steps} warmup_steps={warmup_steps}")
    print("Starting supervised CoSENT training...")

    started = time.time()
    model.fit(
        train_objectives=[(train_loader, train_loss)],
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
        "hard_neg_boost": HARD_NEG_BOOST,
        "max_repeat": MAX_REPEAT,
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
