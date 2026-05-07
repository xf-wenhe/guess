import json
import os
import random
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader
import torch

UNSUP_JSONL = Path(os.getenv('SEM_UNSUP_PAIRS_JSONL', 'data/unsupervised_pairs_v26.jsonl'))
BASE_MODEL = os.getenv('SEM_BASE_MODEL', 'models/bge-m3-finetuned-v25-hintdistill')
OUTPUT_MODEL = os.getenv('SEM_OUTPUT_MODEL', 'models/bge-m3-finetuned-v26-unsup')

MAX_PAIRS = int(os.getenv('SEM_MAX_PAIRS', '20000'))
BATCH_SIZE = int(os.getenv('SEM_BATCH_SIZE', '16'))
EPOCHS = int(os.getenv('SEM_EPOCHS', '1'))
WARMUP_STEPS = int(os.getenv('SEM_WARMUP_STEPS', '100'))
LEARNING_RATE = float(os.getenv('SEM_LEARNING_RATE', '1e-5'))
SEED = int(os.getenv('SEM_SEED', '20260303'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()


def resolve_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def load_pairs(path: Path):
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            a = str(item.get('text_a', '')).strip()
            b = str(item.get('text_b', '')).strip()
            if a and b:
                rows.append((a, b))
    return rows


def main():
    if not UNSUP_JSONL.exists():
        raise SystemExit(f'missing file: {UNSUP_JSONL}')

    pairs = load_pairs(UNSUP_JSONL)
    if len(pairs) < 200:
        raise SystemExit('not enough unsupervised pairs (<200)')

    random.Random(SEED).shuffle(pairs)
    pairs = pairs[:MAX_PAIRS]

    examples = [InputExample(texts=[a, b]) for a, b in pairs]

    print(
        f'unsup_examples={len(examples)} base_model={BASE_MODEL} output_model={OUTPUT_MODEL} '
        f'batch_size={BATCH_SIZE} epochs={EPOCHS} warmup_steps={WARMUP_STEPS} lr={LEARNING_RATE} '
        f'device={resolve_device()}'
    )

    model = SentenceTransformer(
        BASE_MODEL,
        device=resolve_device(),
        local_files_only=True,
    )
    train_loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = losses.MultipleNegativesRankingLoss(model)

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