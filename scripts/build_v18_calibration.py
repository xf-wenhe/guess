import csv
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

INPUT_CSV = Path('data/semantic_scoring_user_input_template.csv')
MODEL_PATH = 'models/bge-m3-finetuned-v18'
OUTPUT_JSON = Path('data/semantic_calibration_v18.json')
BINS = 40


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


def pav(y_vals):
    blocks = [[v, 1] for v in y_vals]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] <= blocks[i + 1][0]:
            i += 1
            continue
        tot_w = blocks[i][1] + blocks[i + 1][1]
        avg = (blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]) / tot_w
        blocks[i] = [avg, tot_w]
        del blocks[i + 1]
        if i > 0:
            i -= 1
    out = []
    for avg, w in blocks:
        out.extend([avg] * w)
    return out


def main():
    rows = load_rows(INPUT_CSV)
    print(f'rows={len(rows)}')
    if len(rows) < 100:
        raise SystemExit('not enough labeled rows')

    model = SentenceTransformer(MODEL_PATH, device='cpu')
    a_texts = [a for a, _, _ in rows]
    b_texts = [b for _, b, _ in rows]
    y_true = np.array([y for _, _, y in rows], dtype=np.float32)

    va = model.encode(a_texts, normalize_embeddings=True, batch_size=64)
    vb = model.encode(b_texts, normalize_embeddings=True, batch_size=64)
    y_pred = np.sum(va * vb, axis=1) * 100.0

    order = np.argsort(y_pred)
    y_pred_sorted = y_pred[order]
    y_true_sorted = y_true[order]

    n = len(y_pred_sorted)
    bin_size = max(1, n // BINS)
    x_points = []
    y_points = []

    for i in range(0, n, bin_size):
        j = min(n, i + bin_size)
        x_points.append(float(np.mean(y_pred_sorted[i:j])))
        y_points.append(float(np.mean(y_true_sorted[i:j])))

    y_iso = pav(y_points)

    calib = {
        'model': MODEL_PATH,
        'x_pred': x_points,
        'y_calibrated': y_iso,
    }

    OUTPUT_JSON.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'written={OUTPUT_JSON} points={len(x_points)}')


if __name__ == '__main__':
    main()
