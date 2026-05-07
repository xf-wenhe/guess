import csv
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

INPUT_CSV = Path('data/semantic_scoring_user_input_template.csv')
BASE_MODEL = 'models/bge-m3-finetuned-v17'
OUTPUT_MODEL = 'models/bge-m3-finetuned-v18'

BATCH_SIZE = 32
EPOCHS = 2
WARMUP_STEPS = 200
LEARNING_RATE = 1.2e-5


def load_examples(path: Path):
    rows = list(csv.DictReader(path.open('r', encoding='utf-8')))
    examples = []
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
        if not (0 <= score <= 100):
            continue

        label = score / 100.0
        repeat = 1
        if score >= 85 or score <= 10:
            repeat = 3
        elif score >= 70 or score <= 20:
            repeat = 2

        for _ in range(repeat):
            examples.append(InputExample(texts=[a, b], label=label))

    return examples


def main():
    if not INPUT_CSV.exists():
        raise SystemExit(f'missing file: {INPUT_CSV}')

    examples = load_examples(INPUT_CSV)
    print(f'train_examples={len(examples)}')
    if len(examples) < 200:
        raise SystemExit('not enough examples')

    model = SentenceTransformer(BASE_MODEL, device='cpu')
    train_loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = losses.CoSENTLoss(model=model)

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
