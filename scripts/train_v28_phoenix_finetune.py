import csv
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer, InputExample
from sentence_transformers.losses import CoSENTLoss
from torch.utils.data import DataLoader

TRAIN_CSV = Path(os.getenv('SEM_TRAIN_CSV', 'data/train_v28_phoenix.csv'))
BASE_MODEL = os.getenv('SEM_BASE_MODEL', 'models/bge-m3-finetuned-v27-semreal-anchor')
OUTPUT_MODEL = os.getenv('SEM_OUTPUT_MODEL', 'models/bge-m3-finetuned-v28-phoenix')
EPOCHS = int(os.getenv('SEM_EPOCHS', '3'))
BATCH_SIZE = int(os.getenv('SEM_BATCH_SIZE', '16'))
LEARNING_RATE = float(os.getenv('SEM_LR', '2e-5'))
WARMUP_RATIO = float(os.getenv('SEM_WARMUP_RATIO', '0.1'))
MAX_TRAIN_ROWS = int(os.getenv('SEM_MAX_TRAIN_ROWS', '0'))
SEED = int(os.getenv('SEM_SEED', '20260515'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()
SCALE = float(os.getenv('SEM_COSSENT_SCALE', '20.0'))


def resolve_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def load_train_data(path: Path):
    rows = []
    with path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            a = (row.get('answer') or '').strip()
            b = (row.get('user_input') or '').strip()
            s = (row.get('score_0_100') or '').strip()
            if not a or not b or not s:
                continue
            try:
                score = float(s) / 100.0
            except ValueError:
                continue
            rows.append(InputExample(texts=[a, b], label=score))
    return rows


def main():
    if not TRAIN_CSV.exists():
        raise SystemExit(f'missing: {TRAIN_CSV}')

    device = resolve_device()
    print(f'base_model={BASE_MODEL}')
    print(f'output_model={OUTPUT_MODEL}')
    print(f'device={device}')
    print(f'epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}')
    print(f'warmup_ratio={WARMUP_RATIO} seed={SEED} scale={SCALE}')

    rows = load_train_data(TRAIN_CSV)
    print(f'train_rows={len(rows)}')

    if MAX_TRAIN_ROWS > 0 and len(rows) > MAX_TRAIN_ROWS:
        random.Random(SEED).shuffle(rows)
        rows = rows[:MAX_TRAIN_ROWS]
        print(f'trimmed to {MAX_TRAIN_ROWS}')

    random.Random(SEED).shuffle(rows)

    model = SentenceTransformer(
        BASE_MODEL,
        device=device,
        local_files_only=True,
    )

    train_loader = DataLoader(rows, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = CoSENTLoss(model=model, scale=SCALE)

    total_steps = len(train_loader) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)

    print(f'total_steps={total_steps} warmup_steps={warmup_steps}')
    print(f'Starting training...')

    started = time.time()
    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=EPOCHS,
        warmup_steps=warmup_steps,
        optimizer_params={'lr': LEARNING_RATE},
        show_progress_bar=True,
    )
    elapsed = time.time() - started
    print(f'Training completed in {elapsed:.1f}s ({elapsed/60:.1f}min)')

    model.save(OUTPUT_MODEL)
    print(f'Model saved to {OUTPUT_MODEL}')

    metrics = {
        'base_model': BASE_MODEL,
        'train_csv': str(TRAIN_CSV),
        'train_rows': len(rows),
        'epochs': EPOCHS,
        'batch_size': BATCH_SIZE,
        'learning_rate': LEARNING_RATE,
        'warmup_ratio': WARMUP_RATIO,
        'warmup_steps': warmup_steps,
        'total_steps': total_steps,
        'scale': SCALE,
        'seed': SEED,
        'device': device,
        'elapsed_seconds': round(elapsed, 1),
    }
    metrics_path = Path(OUTPUT_MODEL + '_train_metrics.json')
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Metrics saved to {metrics_path}')


if __name__ == '__main__':
    main()
