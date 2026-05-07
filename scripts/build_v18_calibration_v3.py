import csv
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

INPUT_CSV = Path('data/semantic_scoring_user_input_template.csv')
MODEL_PATH = 'models/bge-m3-finetuned-v18'
CALIB_V1 = Path('data/semantic_calibration_v18.json')
CALIB_V2 = Path('data/semantic_calibration_v18_v2.json')
OUTPUT_JSON = Path('data/semantic_calibration_v18_v3.json')


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


def summarize(pred, truth):
    total = len(truth)
    hit = 0
    labels = ['0-20', '20-40', '40-60', '60-80', '80-100']
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
    acc = hit / total * 100.0
    per_acc = {k: (per_hit[k] / per_total[k] * 100.0 if per_total[k] else 0.0) for k in labels}
    return mae, acc, per_acc


def weighted_pav(y_vals):
    blocks = [[float(v), 1] for v in y_vals]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] <= blocks[i + 1][0]:
            i += 1
            continue
        w = blocks[i][1] + blocks[i + 1][1]
        y = (blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]) / w
        blocks[i] = [y, w]
        del blocks[i + 1]
        if i > 0:
            i -= 1
    out = []
    for y, w in blocks:
        out.extend([y] * w)
    return out


def main():
    rows = load_rows(INPUT_CSV)
    model = SentenceTransformer(MODEL_PATH, device='cpu')

    a = [r[0] for r in rows]
    b = [r[1] for r in rows]
    truth = np.array([r[2] for r in rows], dtype=np.float32)

    va = model.encode(a, normalize_embeddings=True, batch_size=64)
    vb = model.encode(b, normalize_embeddings=True, batch_size=64)
    raw = np.sum(va * vb, axis=1) * 100.0

    c1 = json.loads(CALIB_V1.read_text(encoding='utf-8'))
    c2 = json.loads(CALIB_V2.read_text(encoding='utf-8'))

    pred1 = np.array([apply_calibration(float(p), c1['x_pred'], c1['y_calibrated']) for p in raw], dtype=np.float32)
    pred2 = np.array([apply_calibration(float(p), c2['x_pred'], c2['y_calibrated']) for p in raw], dtype=np.float32)

    mae1, acc1, per1 = summarize(pred1, truth)

    best = None
    for alpha in np.linspace(0.0, 1.0, 51):
        blend = (1 - alpha) * pred1 + alpha * pred2
        mae, acc, per = summarize(blend, truth)

        if mae > mae1 + 0.15:
            continue
        if acc < acc1 - 0.8:
            continue

        mid_gain = (per['20-40'] + per['40-60']) - (per1['20-40'] + per1['40-60'])
        hi_loss = max(0.0, per1['60-80'] - per['60-80']) + max(0.0, per1['80-100'] - per['80-100'])
        score = mid_gain - 0.35 * hi_loss - 0.2 * max(0.0, mae - mae1)

        cand = {
            'alpha': float(alpha),
            'score': float(score),
            'mae': float(mae),
            'acc': float(acc),
            'per': per,
            'blend': blend,
        }
        if best is None or cand['score'] > best['score']:
            best = cand

    if best is None:
        best = {
            'alpha': 0.0,
            'mae': mae1,
            'acc': acc1,
            'per': per1,
            'blend': pred1,
            'score': 0.0,
        }

    order = np.argsort(raw)
    x_sorted = raw[order]
    y_target = np.array(best['blend'])[order]

    y_iso = np.array(weighted_pav(y_target.tolist()), dtype=np.float32)

    points = 120
    step = max(1, len(x_sorted) // points)
    x_points = []
    y_points = []
    for i in range(0, len(x_sorted), step):
        j = min(len(x_sorted), i + step)
        x_points.append(float(np.mean(x_sorted[i:j])))
        y_points.append(float(np.mean(y_iso[i:j])))

    payload = {
        'model': MODEL_PATH,
        'method': 'blend_v1_v2_then_isotonic_v3',
        'alpha_to_v2': best['alpha'],
        'x_pred': x_points,
        'y_calibrated': y_points,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"written={OUTPUT_JSON}")
    print(f"chosen_alpha={best['alpha']:.2f}")
    print(f"mae={best['mae']:.3f} acc={best['acc']:.2f}%")
    print(
        'bucket_acc 20-40={:.1f}% 40-60={:.1f}% 60-80={:.1f}% 80-100={:.1f}%'.format(
            best['per']['20-40'],
            best['per']['40-60'],
            best['per']['60-80'],
            best['per']['80-100'],
        )
    )


if __name__ == '__main__':
    main()
