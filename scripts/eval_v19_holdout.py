import csv
import json
import os
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

HOLDOUT_CSV = Path(os.getenv('SEM_HOLDOUT_CSV', 'data/splits/semantic_holdout.csv'))
MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v19')
CALIB_PATH = Path(os.getenv('SEM_CALIB_PATH', 'data/semantic_calibration_v19.json'))


def load_rows(path: Path):
    rows = []
    for r in csv.DictReader(path.open('r', encoding='utf-8')):
        a = (r.get('answer') or '').strip()
        b = (r.get('user_input') or '').strip()
        s = (r.get('score_0_100') or '').strip()
        if not a or not b or not s:
            continue
        try:
            y = float(s)
        except ValueError:
            continue
        if 0 <= y <= 100:
            rows.append((a, b, y))
    return rows


def bucket(score: float):
    if score < 20:
        return '0-20'
    if score < 40:
        return '20-40'
    if score < 60:
        return '40-60'
    if score < 80:
        return '60-80'
    return '80-100'


def apply_calibration(pred, x, y):
    if pred <= x[0]:
        return y[0]
    if pred >= x[-1]:
        return y[-1]
    for i in range(len(x) - 1):
        if x[i] <= pred <= x[i + 1]:
            span = x[i + 1] - x[i]
            if span == 0:
                return y[i]
            t = (pred - x[i]) / span
            return y[i] + t * (y[i + 1] - y[i])
    return pred


def summarize(name, pred, truth):
    labels = ['0-20', '20-40', '40-60', '60-80', '80-100']
    total = len(truth)
    hit = 0
    per_total = {k: 0 for k in labels}
    per_hit = {k: 0 for k in labels}

    for t, p in zip(truth, pred):
        tb = bucket(float(t))
        pb = bucket(float(p))
        per_total[tb] += 1
        if tb == pb:
            hit += 1
            per_hit[tb] += 1

    mae = float(np.mean(np.abs(pred - truth)))
    print(f'[{name}] mae={mae:.3f} bucket_acc={hit/total*100:.2f}%')
    for k in labels:
        n = per_total[k]
        if n == 0:
            print(f'  {k}: total=0')
        else:
            print(f'  {k}: {per_hit[k]}/{n} ({per_hit[k]/n*100:.1f}%)')


def main():
    rows = load_rows(HOLDOUT_CSV)
    if len(rows) < 50:
        raise SystemExit('not enough holdout rows, run split_semantic_dataset.py first')

    try:
        model = SentenceTransformer(
            MODEL_PATH,
            device='cpu',
            tokenizer_kwargs={'fix_mistral_regex': True},
            local_files_only=True,
        )
    except TypeError:
        model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))

    a = [r[0] for r in rows]
    b = [r[1] for r in rows]
    truth = np.array([r[2] for r in rows], dtype=np.float32)

    va = model.encode(a, normalize_embeddings=True, batch_size=64)
    vb = model.encode(b, normalize_embeddings=True, batch_size=64)
    raw = np.sum(va * vb, axis=1) * 100.0
    calibrated = np.array([apply_calibration(float(p), calib['x_pred'], calib['y_calibrated']) for p in raw], dtype=np.float32)

    print(f'rows={len(rows)}')
    summarize('raw', raw, truth)
    summarize('calibrated_v19', calibrated, truth)


if __name__ == '__main__':
    main()
