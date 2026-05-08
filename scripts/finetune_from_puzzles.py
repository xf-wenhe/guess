#!/usr/bin/env python3
"""
Finetune embedding model using puzzles.json answers and hints.
Targets:
- Unrelated pairs <= 0.10
- Slightly related pairs ~ 0.20 - 0.30
- Multi-angle semantics
- No length-based features
- Do not overwrite existing model
"""
import json
import random
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

RNG_SEED = 42
BASE_MODEL = "models/bge-m3-finetuned-v14"
OUTPUT_MODEL = "models/bge-m3-finetuned-v15"
PUZZLES_PATH = "assets/puzzles.json"
BATCH_SIZE = 32
EPOCHS = 3
WARMUP_STEPS = 200
LEARNING_RATE = 2e-5

HINT_PERCENTS = [30, 40, 50, 60, 70, 80, 90]
ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]

SLIGHTLY_RELATED_LABEL = 0.62
UNRELATED_LABEL = 0.05

MANUAL_ANCHORS = [
    ("啊啊", "夸父", 0.02),
    ("你是猪", "夸父", 0.02),
    ("夸父", "逐日", 0.85),
    ("夸父", "神话", 0.65),
    ("龙王", "应龙", 0.62),
]


def load_puzzles(path: str):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def build_pairs(puzzles):
    random.seed(RNG_SEED)
    answers = [p["answer"] for p in puzzles]
    by_category = {}
    for p in puzzles:
        by_category.setdefault(p.get("category", ""), []).append(p)

    pairs = []

    # Manual anchors for known edge cases
    pairs.extend(MANUAL_ANCHORS)

    # Positive pairs from hints with target labels based on percent order
    for p in puzzles:
        answer = p["answer"]
        hints = p.get("hints", [])
        for hint, percent in zip(hints, HINT_PERCENTS):
            label = percent / 100.0
            pairs.append((answer, hint, label))

    # Same category: target 0.60-0.80
    for p in puzzles:
        category = p.get("category", "")
        pool = [x for x in by_category.get(category, []) if x["answer"] != p["answer"]]
        if not pool:
            continue
        sampled = random.sample(pool, k=min(4, len(pool)))
        for other in sampled:
            pairs.append((p["answer"], other["answer"], SLIGHTLY_RELATED_LABEL))

    # Unrelated: different category
    for p in puzzles:
        pool = [x for x in puzzles if x.get("category") != p.get("category")]
        if not pool:
            continue
        sampled = random.sample(pool, k=min(2, len(pool)))
        for other in sampled:
            pairs.append((p["answer"], other["answer"], UNRELATED_LABEL))

    # Unrelated: gibberish or sentence-like inputs vs answers (sampled)
    for answer in answers:
        if random.random() < 0.4:
            pairs.append(("啊啊", answer, UNRELATED_LABEL))
        if random.random() < 0.4:
            pairs.append(("你是猪", answer, UNRELATED_LABEL))

    # Multi-angle expansions
    expanded = []
    for a, b, label in pairs:
        expanded.append((a, b, label))
        for angle in ANGLES:
            expanded.append((f"{angle}{a}", f"{angle}{b}", label))

    random.shuffle(expanded)
    return expanded


def main():
    puzzles = load_puzzles(PUZZLES_PATH)
    pairs = build_pairs(puzzles)
    print(f"Total pairs: {len(pairs)}")

    train_examples = [InputExample(texts=[a, b], label=label) for a, b, label in pairs]

    model = SentenceTransformer(BASE_MODEL, device="cpu")
    train_loader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = losses.CosineSimilarityLoss(model=model)

    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=EPOCHS,
        warmup_steps=WARMUP_STEPS,
        optimizer_params={"lr": LEARNING_RATE},
        show_progress_bar=True,
    )

    model.save(OUTPUT_MODEL)
    print(f"Saved to {OUTPUT_MODEL}")


if __name__ == "__main__":
    main()
