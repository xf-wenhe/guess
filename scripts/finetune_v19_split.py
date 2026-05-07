import csv
import os
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

TRAIN_CSV = Path(os.getenv('SEM_TRAIN_CSV', 'data/splits/semantic_train.csv'))
BASE_MODEL = os.getenv('SEM_BASE_MODEL', 'models/bge-m3-finetuned-v18')
OUTPUT_MODEL = os.getenv('SEM_OUTPUT_MODEL', 'models/bge-m3-finetuned-v19')

BATCH_SIZE = 32
EPOCHS = 2
WARMUP_STEPS = 120
LEARNING_RATE = 1.0e-5

BATCH_SIZE = int(os.getenv('SEM_BATCH_SIZE', str(BATCH_SIZE)))
EPOCHS = int(os.getenv('SEM_EPOCHS', str(EPOCHS)))
WARMUP_STEPS = int(os.getenv('SEM_WARMUP_STEPS', str(WARMUP_STEPS)))
LEARNING_RATE = float(os.getenv('SEM_LEARNING_RATE', str(LEARNING_RATE)))


def load_examples(path: Path):
    rows = list(csv.DictReader(path.open('r', encoding='utf-8')))
    examples = []

    for r in rows:
        answer = (r.get('answer') or '').strip()
        user_input = (r.get('user_input') or '').strip()
        score_raw = (r.get('score_0_100') or '').strip()

        if not answer or not user_input or not score_raw:
            continue

        try:
            score = float(score_raw)
        except ValueError:
            continue
        if not (0 <= score <= 100):
            continue

        label = score / 100.0

        repeat = 1
        if 20 <= score < 60:
            repeat = 3
        elif score < 20 or score >= 80:
            repeat = 2

        for _ in range(repeat):
            examples.append(InputExample(texts=[answer, user_input], label=label))

    return examples


def main():
    if not TRAIN_CSV.exists():
        raise SystemExit(f'missing file: {TRAIN_CSV}, run split_semantic_dataset.py first')

    examples = load_examples(TRAIN_CSV)
    print(f'train_examples={len(examples)}')
    print(
        f'base_model={BASE_MODEL} output_model={OUTPUT_MODEL} '
        f'batch_size={BATCH_SIZE} epochs={EPOCHS} warmup_steps={WARMUP_STEPS} lr={LEARNING_RATE}'
    )
    if len(examples) < 200:
        raise SystemExit('not enough examples from train split')

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
