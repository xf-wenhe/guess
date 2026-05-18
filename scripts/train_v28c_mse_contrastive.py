import csv
import json
import os
import random
import time
from pathlib import Path
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer
from torch.utils.data import Dataset, DataLoader

TRAIN_CSV = Path(os.getenv('SEM_TRAIN_CSV', 'data/train_v28_phoenix.csv'))
BASE_MODEL = os.getenv('SEM_BASE_MODEL', 'models/bge-m3-finetuned-v27-semreal-anchor')
OUTPUT_MODEL = os.getenv('SEM_OUTPUT_MODEL', 'models/bge-m3-finetuned-v28c-phoenix')
EPOCHS = int(os.getenv('SEM_EPOCHS', '3'))
BATCH_SIZE = int(os.getenv('SEM_BATCH_SIZE', '8'))
LEARNING_RATE = float(os.getenv('SEM_LR', '2e-5'))
WARMUP_RATIO = float(os.getenv('SEM_WARMUP_RATIO', '0.1'))
MAX_TRAIN_ROWS = int(os.getenv('SEM_MAX_TRAIN_ROWS', '0'))
SEED = int(os.getenv('SEM_SEED', '20260515'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()
MSE_WEIGHT = float(os.getenv('SEM_MSE_WEIGHT', '0.5'))
CONTRASTIVE_WEIGHT = float(os.getenv('SEM_CONTRASTIVE_WEIGHT', '0.5'))
CONTRASTIVE_MARGIN = float(os.getenv('SEM_CONTRASTIVE_MARGIN', '0.5'))
HARD_NEG_BOOST = float(os.getenv('SEM_HARD_NEG_BOOST', '3.0'))

HARD_NEG_TAGS = {
    'antonym_low', 'function_word_low', 'function_word_vs_real_low',
    'hard_negative_low', 'hard_negative_mid', 'cross_category_low',
    'cross_category_negative',
}


def resolve_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


class PairDataset(Dataset):
    def __init__(self, path: Path, seed: int = 42, max_rows: int = 0):
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
                weight = HARD_NEG_BOOST if tag in HARD_NEG_TAGS else 1.0
                rows.append((a, b, score, weight, tag))

        random.Random(seed).shuffle(rows)
        if max_rows > 0 and len(rows) > max_rows:
            rows = rows[:max_rows]

        self.rows = rows
        tag_counts = Counter(r[4] for r in rows)
        print(f'  dataset: {len(rows)} pairs')
        hard_count = sum(1 for r in rows if r[4] in HARD_NEG_TAGS)
        print(f'  hard negatives: {hard_count} ({hard_count/len(rows)*100:.1f}%)')
        print(f'  hard neg weight boost: {HARD_NEG_BOOST}x')

        score_buckets = Counter((int(r[2]*100) // 10) * 10 for r in rows)
        print(f'  score distribution:')
        for b in sorted(score_buckets):
            print(f'    {b:3d}-{b+9:3d}: {score_buckets[b]:4d}')

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        return self.rows[idx]


class MSEContrastiveLoss(nn.Module):
    def __init__(self, mse_weight=0.5, contrastive_weight=0.5, margin=0.5):
        super().__init__()
        self.mse_weight = mse_weight
        self.contrastive_weight = contrastive_weight
        self.margin = margin

    def forward(self, cos_sims, labels, weights):
        mse_loss = F.mse_loss(cos_sims, labels, reduction='none')
        mse_loss = (mse_loss * weights).mean()

        dist = 1.0 - cos_sims
        contrastive_pos = labels * dist * dist
        contrastive_neg = (1.0 - labels) * F.relu(self.margin - dist) ** 2
        contrastive_loss = (contrastive_pos + contrastive_neg) * weights
        contrastive_loss = contrastive_loss.mean()

        total = self.mse_weight * mse_loss + self.contrastive_weight * contrastive_loss
        return total


def train_epoch(model, dataloader, optimizer, loss_fn, device, epoch):
    model.train()
    total_loss = 0.0
    n_batches = 0

    for batch_idx, batch in enumerate(dataloader):
        texts_a = [item[0] for item in batch]
        texts_b = [item[1] for item in batch]
        labels = torch.tensor([item[2] for item in batch], dtype=torch.float32, device=device)
        weights = torch.tensor([item[3] for item in batch], dtype=torch.float32, device=device)

        emb_a = model.encode(texts_a, convert_to_tensor=True, device=device, show_progress_bar=False, normalize_embeddings=True)
        emb_b = model.encode(texts_b, convert_to_tensor=True, device=device, show_progress_bar=False, normalize_embeddings=True)

        cos_sims = F.cosine_similarity(emb_a, emb_b)
        cos_sims = torch.clamp(cos_sims, -1.0, 1.0)

        loss = loss_fn(cos_sims, labels, weights)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item()
        n_batches += 1

        if (batch_idx + 1) % 100 == 0:
            avg = total_loss / n_batches
            print(f'  epoch {epoch} [{batch_idx+1}/{len(dataloader)}] loss={loss.item():.4f} avg={avg:.4f}')

    return total_loss / max(n_batches, 1)


def main():
    if not TRAIN_CSV.exists():
        raise SystemExit(f'missing: {TRAIN_CSV}')

    device_name = resolve_device()
    device = torch.device(device_name)
    print(f'base_model={BASE_MODEL}')
    print(f'output_model={OUTPUT_MODEL}')
    print(f'device={device_name}')
    print(f'epochs={EPOCHS} batch_size={BATCH_SIZE} lr={LEARNING_RATE}')
    print(f'mse_weight={MSE_WEIGHT} contrastive_weight={CONTRASTIVE_WEIGHT} margin={CONTRASTIVE_MARGIN}')
    print(f'hard_neg_boost={HARD_NEG_BOOST}')
    print(f'warmup_ratio={WARMUP_RATIO} seed={SEED}')

    dataset = PairDataset(TRAIN_CSV, seed=SEED, max_rows=MAX_TRAIN_ROWS)
    dataloader = DataLoader(
        dataset, batch_size=BATCH_SIZE, shuffle=True,
        num_workers=0, pin_memory=False,
    )

    model = SentenceTransformer(
        BASE_MODEL,
        device=device_name,
        local_files_only=True,
    )

    loss_fn = MSEContrastiveLoss(
        mse_weight=MSE_WEIGHT,
        contrastive_weight=CONTRASTIVE_WEIGHT,
        margin=CONTRASTIVE_MARGIN,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

    total_steps = len(dataloader) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)

    def lr_lambda(step):
        if step < warmup_steps:
            return step / max(warmup_steps, 1)
        progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
        return max(0.0, 0.5 * (1.0 + np.cos(np.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    print(f'\ntotal_steps={total_steps} warmup_steps={warmup_steps}')
    print(f'Starting training...\n')

    started = time.time()
    best_loss = float('inf')

    for epoch in range(1, EPOCHS + 1):
        avg_loss = train_epoch(model, dataloader, optimizer, loss_fn, device, epoch)
        print(f'epoch {epoch} done. avg_loss={avg_loss:.4f}')

        if avg_loss < best_loss:
            best_loss = avg_loss
            model.save(OUTPUT_MODEL)
            print(f'  best model saved (loss={best_loss:.4f})')

        scheduler.step()

    elapsed = time.time() - started
    print(f'\nTraining completed in {elapsed:.1f}s ({elapsed/60:.1f}min)')
    print(f'Best loss: {best_loss:.4f}')
    print(f'Model saved to {OUTPUT_MODEL}')

    metrics = {
        'base_model': BASE_MODEL,
        'train_csv': str(TRAIN_CSV),
        'train_rows': len(dataset),
        'epochs': EPOCHS,
        'batch_size': BATCH_SIZE,
        'learning_rate': LEARNING_RATE,
        'mse_weight': MSE_WEIGHT,
        'contrastive_weight': CONTRASTIVE_WEIGHT,
        'contrastive_margin': CONTRASTIVE_MARGIN,
        'hard_neg_boost': HARD_NEG_BOOST,
        'warmup_ratio': WARMUP_RATIO,
        'warmup_steps': warmup_steps,
        'total_steps': total_steps,
        'best_loss': round(best_loss, 6),
        'seed': SEED,
        'device': device_name,
        'elapsed_seconds': round(elapsed, 1),
    }
    metrics_path = Path(OUTPUT_MODEL + '_train_metrics.json')
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Metrics saved to {metrics_path}')


if __name__ == '__main__':
    main()
