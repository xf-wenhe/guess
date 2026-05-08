import csv
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

INPUT_CSV = Path('data/semantic_scoring_user_input_template.csv')
MODEL_PATH = 'models/bge-m3-finetuned-v18'
OUTPUT_JSON = Path('data/semantic_calibration_v18_v2.json')


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


def sample_weight(score: float) -> float:
    if 20 <= score < 40:
        return 2.8
    if 40 <= score < 60:
        return 2.8
    if 60 <= score < 80:
        return 1.8
    return 1.0


def weighted_pav(y_vals, w_vals):
    blocks = [[float(y), float(w), 1] for y, w in zip(y_vals, w_vals)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] <= blocks[i + 1][0]:
            i += 1
            continue

        y1, w1, c1 = blocks[i]
        y2, w2, c2 = blocks[i + 1]
        w = w1 + w2
        y = (y1 * w1 + y2 * w2) / w
        c = c1 + c2
        blocks[i] = [y, w, c]
        del blocks[i + 1]
        if i > 0:
            i -= 1

    out = []
    for y, _, count in blocks:
        out.extend([y] * count)
    return out


def compress_points(x_sorted, y_iso, max_points=120):
    n = len(x_sorted)
    step = max(1, n // max_points)
    xs = []
    ys = []
    for i in range(0, n, step):
        j = min(n, i + step)
        xs.append(float(np.mean(x_sorted[i:j])))
        ys.append(float(np.mean(y_iso[i:j])))
    if xs[-1] < x_sorted[-1]:
        xs.append(float(x_sorted[-1]))
        ys.append(float(y_iso[-1]))
    return xs, ys


def main():
    rows = load_rows(INPUT_CSV)
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
    x_sorted = y_pred[order]
    y_sorted = y_true[order]
    w_sorted = np.array([sample_weight(float(v)) for v in y_sorted], dtype=np.float32)

    y_iso = np.array(weighted_pav(y_sorted.tolist(), w_sorted.tolist()), dtype=np.float32)
    x_points, y_points = compress_points(x_sorted, y_iso)

    payload = {
        'model': MODEL_PATH,
        'method': 'weighted_isotonic_v2',
        'x_pred': x_points,
        'y_calibrated': y_points,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'written={OUTPUT_JSON} points={len(x_points)} rows={len(rows)}')


if __name__ == '__main__':
    main()
