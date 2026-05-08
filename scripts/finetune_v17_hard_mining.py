import csv
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

INPUT_CSV = Path('data/semantic_scoring_user_input_template.csv')
BASE_MODEL = 'models/bge-m3-finetuned-v16'
OUTPUT_MODEL = 'models/bge-m3-finetuned-v17'

BATCH_SIZE = 32
EPOCHS = 2
WARMUP_STEPS = 200
LEARNING_RATE = 1.5e-5


def load_rows(path: Path):
    rows = list(csv.DictReader(path.open('r', encoding='utf-8')))
    valid = []
    for r in rows:
        a = (r.get('answer') or '').strip()
        b = (r.get('user_input') or '').strip()
        s = (r.get('score_0_100') or '').strip()
        if not a or not b or not s:
            continue
        try:
            score = float(s)
        except ValueError:
            continue
        if 0 <= score <= 100:
            valid.append((a, b, score / 100.0))
    return valid


def build_weighted_examples(model: SentenceTransformer, rows):
    texts_a = [a for a, _, _ in rows]
    texts_b = [b for _, b, _ in rows]
    labels = [y for _, _, y in rows]

    emb_a = model.encode(texts_a, normalize_embeddings=True, batch_size=64)
    emb_b = model.encode(texts_b, normalize_embeddings=True, batch_size=64)

    examples = []
    hard_count = 0
    for a, b, y, va, vb in zip(texts_a, texts_b, labels, emb_a, emb_b):
        pred = float((va * vb).sum())
        err = abs(pred - y)

        repeat = 1
        if err >= 0.35:
            repeat = 5
            hard_count += 1
        elif err >= 0.25:
            repeat = 4
            hard_count += 1
        elif err >= 0.18:
            repeat = 3
        elif err >= 0.10:
            repeat = 2

        for _ in range(repeat):
            examples.append(InputExample(texts=[a, b], label=y))

    return examples, hard_count


def main():
    if not INPUT_CSV.exists():
        raise SystemExit(f'missing file: {INPUT_CSV}')

    rows = load_rows(INPUT_CSV)
    if len(rows) < 100:
        raise SystemExit('Not enough valid rows')

    model = SentenceTransformer(BASE_MODEL, device='cpu')
    train_examples, hard_count = build_weighted_examples(model, rows)

    print(f'base_rows={len(rows)} weighted_examples={len(train_examples)} hard_rows={hard_count}')

    train_loader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = losses.CosineSimilarityLoss(model=model)

    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=EPOCHS,
        warmup_steps=WARMUP_STEPS,
        optimizer_params={'lr': LEARNING_RATE},
        show_progress_bar=True,
    )

    model.save(OUTPUT_MODEL)
    print(f'saved={OUTPUT_MODEL}')


if __name__ == '__main__':
    main()
