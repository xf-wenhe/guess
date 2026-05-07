import csv
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

INPUT_CSV = Path("data/semantic_scoring_user_input_template.csv")
BASE_MODEL = "models/bge-m3-finetuned-v15"
OUTPUT_MODEL = "models/bge-m3-finetuned-v16"
BATCH_SIZE = 32
EPOCHS = 2
WARMUP_STEPS = 200
LEARNING_RATE = 2e-5


def load_examples(path: Path):
    rows = list(csv.DictReader(path.open("r", encoding="utf-8")))
    examples = []
    missing = 0
    invalid = 0

    for r in rows:
        answer = (r.get("answer") or "").strip()
        user_input = (r.get("user_input") or "").strip()
        score_raw = (r.get("score_0_100") or "").strip()

        if not answer or not user_input:
            missing += 1
            continue
        if not score_raw:
            missing += 1
            continue
        try:
            score = float(score_raw)
        except ValueError:
            invalid += 1
            continue
        if score < 0 or score > 100:
            invalid += 1
            continue

        label = score / 100.0
        examples.append(InputExample(texts=[answer, user_input], label=label))

    return rows, examples, missing, invalid


def main():
    if not INPUT_CSV.exists():
        raise SystemExit(f"missing file: {INPUT_CSV}")

    rows, examples, missing, invalid = load_examples(INPUT_CSV)

    print(f"total_rows={len(rows)}")
    print(f"train_examples={len(examples)}")
    print(f"missing_rows={missing}")
    print(f"invalid_rows={invalid}")

    if len(examples) < 100:
        raise SystemExit("Not enough valid labeled rows (<100).")

    model = SentenceTransformer(BASE_MODEL, device="cpu")
    train_loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = losses.CosineSimilarityLoss(model=model)

    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=EPOCHS,
        warmup_steps=WARMUP_STEPS,
        optimizer_params={"lr": LEARNING_RATE},
        show_progress_bar=True,
    )

    model.save(OUTPUT_MODEL)
    print(f"saved={OUTPUT_MODEL}")


if __name__ == "__main__":
    main()
