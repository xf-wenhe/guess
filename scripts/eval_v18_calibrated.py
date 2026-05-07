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
    pred = np.sum(va * vb, axis=1) * 100.0

    cal = np.array([apply_calibration(float(p), x, y) for p in pred], dtype=np.float32)

    mae_raw = float(np.mean(np.abs(pred - truth)))
    mae_cal = float(np.mean(np.abs(cal - truth)))

    print(f'rows={len(rows)} mae_raw={mae_raw:.3f} mae_calibrated={mae_cal:.3f}')


if __name__ == '__main__':
    main()
