import csv
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

INPUT_CSV = Path('data/semantic_scoring_user_input_template.csv')
MODEL_PATH = 'models/bge-m3-finetuned-v18'
CALIB_PATH = Path('data/semantic_calibration_v18.json')


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


def main():
    rows = load_rows(INPUT_CSV)
    model = SentenceTransformer(MODEL_PATH, device='cpu')
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    x = calib['x_pred']
    y = calib['y_calibrated']

    a = [r[0] for r in rows]
    b = [r[1] for r in rows]
    truth = np.array([r[2] for r in rows], dtype=np.float32)

    va = model.encode(a, normalize_embeddings=True, batch_size=64)
    vb = model.encode(b, normalize_embeddings=True, batch_size=64)

    raw = np.sum(va * vb, axis=1) * 100.0
    calibrated = np.array([apply_calibration(float(p), x, y) for p in raw], dtype=np.float32)

    mae_raw = float(np.mean(np.abs(raw - truth)))
    mae_cal = float(np.mean(np.abs(calibrated - truth)))

    total = len(rows)
    hit_raw = 0
    hit_cal = 0

    bucket_labels = ['0-20', '20-40', '40-60', '60-80', '80-100']
    per_bucket_total = {k: 0 for k in bucket_labels}
    per_bucket_raw = {k: 0 for k in bucket_labels}
    per_bucket_cal = {k: 0 for k in bucket_labels}

    for t, r, c in zip(truth, raw, calibrated):
        tb = bucket(float(t))
        rb = bucket(float(r))
        cb = bucket(float(c))

        per_bucket_total[tb] += 1
        if rb == tb:
            hit_raw += 1
            per_bucket_raw[tb] += 1
        if cb == tb:
            hit_cal += 1
            per_bucket_cal[tb] += 1

    print(f'rows={total}')
    print(f'mae_raw={mae_raw:.3f}')
    print(f'mae_calibrated={mae_cal:.3f}')
    print(f'bucket_acc_raw={hit_raw/total*100:.2f}%')
    print(f'bucket_acc_calibrated={hit_cal/total*100:.2f}%')
    print('per_bucket:')
    for bname in bucket_labels:
        n = per_bucket_total[bname]
        if n == 0:
            print(f'  {bname}: total=0 raw=0 cal=0')
            continue
        print(
            f'  {bname}: total={n} '
            f'raw={per_bucket_raw[bname]}/{n} ({per_bucket_raw[bname]/n*100:.1f}%) '
            f'cal={per_bucket_cal[bname]}/{n} ({per_bucket_cal[bname]/n*100:.1f}%)'
        )


if __name__ == '__main__':
    main()
