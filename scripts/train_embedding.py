import argparse
import json
import random
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer
from sentence_transformers import losses
from torch.utils.data import DataLoader


def load_pairs(path: Path, max_samples: int | None = None) -> list[InputExample]:
    examples: list[InputExample] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            text1 = (obj.get("text1") or "").strip()
            text2 = (obj.get("text2") or "").strip()
            if not text1 or not text2:
                continue
            label = float(obj.get("label", 1.0))
            examples.append(InputExample(texts=[text1, text2], label=label))
            if max_samples and len(examples) >= max_samples:
                break
    return examples


def load_puzzle_examples(
    path: Path,
    max_samples: int | None = None,
    negatives_per_answer: int = 6,
    add_symmetric: bool = True,
) -> list[InputExample]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    puzzles: list[dict] = []
    for item in data:
        answer = (item.get("answer") or "").strip()
        hints = [h.strip() for h in item.get("hints", []) if str(h).strip()]
        category = (item.get("category") or "").strip()
        pos = (item.get("pos") or "").strip()
        if not answer or not hints:
            continue
        puzzles.append(
            {"answer": answer, "hints": hints, "category": category, "pos": pos}
        )

    if not puzzles:
        return []

    answers = [p["answer"] for p in puzzles]
    all_hints = [h for p in puzzles for h in p["hints"]]
    rng = random.Random(42)

    examples: list[InputExample] = []
    for puzzle in puzzles:
        answer = puzzle["answer"]
        positives = set(puzzle["hints"])
        if puzzle["category"]:
            positives.add(f"范围：{puzzle['category']}")
        if puzzle["pos"]:
            positives.add(f"词性：{puzzle['pos']}")
        positives.add(f"词义：{answer}")
        combined = (
            f"词义：{answer}，"
            f"范围：{puzzle['category'] or '其他'}，"
            f"词性：{puzzle['pos'] or '名词'}，"
            f"{','.join(puzzle['hints'])}"
        )
        positives.add(combined)

        for text2 in positives:
            examples.append(InputExample(texts=[answer, text2], label=1.0))
            if add_symmetric:
                examples.append(InputExample(texts=[text2, answer], label=1.0))

        negative_candidates = [
            a for a in answers if a != answer
        ] + [h for h in all_hints if h not in positives]
        rng.shuffle(negative_candidates)
        for text2 in negative_candidates[:negatives_per_answer]:
            examples.append(InputExample(texts=[answer, text2], label=0.0))
            if add_symmetric:
                examples.append(InputExample(texts=[text2, answer], label=0.0))

        if max_samples and len(examples) >= max_samples:
            break

    if max_samples:
        return examples[:max_samples]
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune embedding model")
    parser.add_argument(
        "--data",
        type=str,
        default="assets/puzzles.json",
        help="Path to puzzles.json or jsonl training pairs",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="BAAI/bge-small-zh-v1.5",
        help="Base model name or local path",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/bge-small-zh-finetuned",
        help="Output directory for fine-tuned model",
    )
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--negatives-per-answer", type=int, default=6)
    parser.add_argument("--no-symmetric", action="store_true")
    parser.add_argument("--preview", type=int, default=0)
    parser.add_argument("--preview-random", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Training data not found: {data_path}")

    if data_path.suffix.lower() == ".json":
        examples = load_puzzle_examples(
            data_path,
            max_samples=args.max_samples or None,
            negatives_per_answer=args.negatives_per_answer,
            add_symmetric=not args.no_symmetric,
        )
    else:
        examples = load_pairs(
            data_path,
            max_samples=args.max_samples or None,
        )
    if not examples:
        raise ValueError("No training examples found.")

    if args.summary:
        pos = sum(1 for e in examples if e.label >= 0.5)
        neg = len(examples) - pos
        print(
            f"Loaded {len(examples)} examples (pos={pos}, neg={neg})."
        )

    if args.preview > 0:
        if args.preview_random:
            sample = random.sample(
                examples, k=min(args.preview, len(examples))
            )
        else:
            sample = examples[: args.preview]
        print("Preview samples:")
        for idx, ex in enumerate(sample, start=1):
            print(f"{idx}. label={ex.label} | {ex.texts[0]} <> {ex.texts[1]}")
        return

    model = SentenceTransformer(args.base_model)
    train_loader = DataLoader(examples, shuffle=True, batch_size=args.batch_size)
    train_loss = losses.CosineSimilarityLoss(model)

    warmup_steps = max(1, int(len(train_loader) * 0.1))
    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=args.epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": args.lr},
        show_progress_bar=True,
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(output_dir))
    print(f"Saved fine-tuned model to {output_dir}")


if __name__ == "__main__":
    main()
