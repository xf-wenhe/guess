import csv
import json
import os
import random
import time
from pathlib import Path
from collections import Counter

import numpy as np
import torch
from sentence_transformers import SentenceTransformer, InputExample
from sentence_transformers.losses import CoSENTLoss
from torch.utils.data import DataLoader

TRAIN_CSV = Path(os.getenv('SEM_TRAIN_CSV', 'data/train_v28_phoenix.csv'))
BASE_MODEL = os.getenv('SEM_BASE_MODEL', 'models/bge-m3-finetuned-v27-semreal-anchor')
OUTPUT_MODEL = os.getenv('SEM_OUTPUT_MODEL', 'models/bge-m3-finetuned-v28b-phoenix')
EPOCHS = int(os.getenv('SEM_EPOCHS', '3'))
BATCH_SIZE = int(os.getenv('SEM_BATCH_SIZE', '8'))
LEARNING_RATE = float(os.getenv('SEM_LR', '2e-5'))
WARMUP_RATIO = float(os.getenv('SEM_WARMUP_RATIO', '0.1'))
MAX_TRAIN_ROWS = int(os.getenv('SEM_MAX_TRAIN_ROWS', '0'))
SEED = int(os.getenv('SEM_SEED', '20260515'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()
SCALE = float(os.getenv('SEM_COSSENT_SCALE', '20.0'))
OVERSAMPLE_HARD = int(os.getenv('SEM_OVERSAMPLE_HARD', '5'))


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
            tag = (row.get('relation_tag') or '').strip()
            if not a or not b or not s:
                continue
            try:
                score = float(s) / 100.0
            except ValueError:
                continue
            rows.append({
                'text_a': a,
                'text_b': b,
                'score': score,
                'tag': tag,
            })
    return rows


def oversample_hard_negatives(rows, factor=5):
    hard_tags = {
        'antonym_low', 'function_word_low', 'function_word_vs_real_low',
        'hard_negative_low', 'hard_negative_mid', 'cross_category_low',
    }
    hard_rows = [r for r in rows if r['tag'] in hard_tags]
    normal_rows = [r for r in rows if r['tag'] not in hard_tags]
    oversampled = hard_rows * factor
    combined = normal_rows + oversampled
    return combined


def main():
    if not TRAIN_CSV.exists():
        raise SystemExit(f'missing: {TRAIN_CSV}')

    device = resolve_device()
    print(f'base_model={BASE_MODEL}')
    print(f'output_model={OUTPUT_MODEL}')
    print(f'device={device}')
    print(f'epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}')
    print(f'warmup_ratio={WARMUP_RATIO} seed={SEED} scale={SCALE}')
    print(f'oversample_hard={OVERSAMPLE_HARD}')

    raw_rows = load_train_data(TRAIN_CSV)
    print(f'train_rows_loaded={len(raw_rows)}')

    tag_counts = Counter(r['tag'] for r in raw_rows)
    print('\nTag distribution (before oversample):')
    for tag, cnt in tag_counts.most_common():
        print(f'  {tag}: {cnt}')

    rows = oversample_hard_negatives(raw_rows, OVERSAMPLE_HARD)
    print(f'\nAfter oversample: {len(rows)} rows')

    oversampled_tags = Counter(r['tag'] for r in rows)
    print('Tag distribution (after oversample):')
    for tag, cnt in oversampled_tags.most_common(10):
        print(f'  {tag}: {cnt}')

    if MAX_TRAIN_ROWS > 0 and len(rows) > MAX_TRAIN_ROWS:
        random.Random(SEED).shuffle(rows)
        rows = rows[:MAX_TRAIN_ROWS]
        print(f'trimmed to {MAX_TRAIN_ROWS}')

    random.Random(SEED).shuffle(rows)

    examples = [InputExample(texts=[r['text_a'], r['text_b']], label=r['score']) for r in rows]

    model = SentenceTransformer(
        BASE_MODEL,
        device=device,
        local_files_only=True,
    )

    train_loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    train_loss = CoSENTLoss(model=model, scale=SCALE)

    total_steps = len(train_loader) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)

    print(f'\ntotal_steps={total_steps} warmup_steps={warmup_steps}')
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
        'train_rows_loaded': len(raw_rows),
        'train_rows_after_oversample': len(rows),
        'oversample_factor': OVERSAMPLE_HARD,
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
