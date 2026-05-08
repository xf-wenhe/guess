import csv
import json
import os
import argparse
from pathlib import Path
import time

import numpy as np
from sentence_transformers import SentenceTransformer
import torch

MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v27-semreal-anchor')
CALIB_CSV = Path(os.getenv('SEM_CALIB_CSV', 'data/gold_v26_calib.csv'))
EVAL_CSV = Path(os.getenv('SEM_EVAL_CSV', 'data/gold_v26_eval.csv'))
CALIB_JSON = Path(os.getenv('SEM_CALIB_JSON', 'data/semantic_calibration_v27_semreal_anchor.json'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()
ENCODE_BATCH_SIZE = int(os.getenv('SEM_ENCODE_BATCH_SIZE', '32'))

ANGLES = [
    '从含义角度看：',
    '从用途角度看：',
    '从场景角度看：',
    '从特征角度看：',
    '从关联角度看：',
]


def resolve_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def cosine_similarity(a, b):
    dot = float((a * b).sum())
    na = float((a * a).sum()) ** 0.5
    nb = float((b * b).sum()) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / na / nb


def semantic_multi_angle_from_cache(cache, left: str, right: str):
    scores = []
    for angle in ANGLES:
        v1 = cache[(angle, left)]
        v2 = cache[(angle, right)]
        scores.append(cosine_similarity(v1, v2))
    scores.sort()
    trimmed = scores[1:-1] if len(scores) >= 3 else scores
    return (sum(trimmed) / len(trimmed)) * 100.0


def build_embedding_cache(model, rows):
    unique_texts = sorted({text for pair in rows for text in pair[:2]})
    cache = {}
    for angle in ANGLES:
        encoded = model.encode(
            [f'{angle}{text}' for text in unique_texts],
            normalize_embeddings=True,
            batch_size=ENCODE_BATCH_SIZE,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        for text, vec in zip(unique_texts, encoded):
            cache[(angle, text)] = vec
    return cache


def predict_rows(rows, cache):
    return [semantic_multi_angle_from_cache(cache, a, b) for a, b, _ in rows]


def read_rows(path: Path):
    rows = []
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            a = (row.get('answer') or '').strip()
            b = (row.get('user_input') or '').strip()
            s = (row.get('score_0_100') or '').strip()
            if not a or not b or not s:
                continue
            try:
                score = float(s)
            except ValueError:
                continue
            rows.append((a, b, score))
    return rows


def build_calibration(pred, target):
    p = np.array(pred, dtype=np.float32)
    t = np.array(target, dtype=np.float32)
    order = np.argsort(p)
    p = p[order]
    t = t[order]
    x = []
    y = []
    n = len(p)
    n_bins = min(20, max(5, n // 2))
    for i in range(n_bins):
        left = int(i * n / n_bins)
        right = int((i + 1) * n / n_bins)
        if right <= left:
            continue
        x.append(float(np.mean(p[left:right])))
        y.append(float(np.mean(t[left:right])))
    if not x:
        x = [0.0, 100.0]
        y = [0.0, 100.0]
    return {'x_pred': x, 'y_calibrated': y}


def apply_calibration(pred, x, y):
    if pred <= x[0]:
        return y[0]
    if pred >= x[-1]:
        return y[-1]
    for i in range(len(x) - 1):
        left, right = x[i], x[i + 1]
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return y[i]
            t = (pred - left) / span
            return y[i] + (y[i + 1] - y[i]) * t
    return pred


def bucket(score):
    if score < 20:
        return '0-20'
    if score < 40:
        return '20-40'
    if score < 60:
        return '40-60'
    if score < 80:
        return '60-80'
    return '80-100'


def metric(pred, target):
    n = len(pred)
    if n == 0:
        return 0.0, 0.0
    mae = float(np.mean(np.abs(np.array(pred) - np.array(target))))
    hit = 0
    for p, t in zip(pred, target):
        if bucket(p) == bucket(t):
            hit += 1
    return mae, hit / n * 100.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json-out', default='')
    args = parser.parse_args()

    if not CALIB_CSV.exists() or not EVAL_CSV.exists():
        raise SystemExit('missing gold calib/eval csv')

    calib_rows = read_rows(CALIB_CSV)
    eval_rows = read_rows(EVAL_CSV)
    if len(calib_rows) < 5 or len(eval_rows) < 5:
        raise SystemExit('gold rows too small')

    all_rows = calib_rows + eval_rows
    device = resolve_device()
    print(
        f'model_path={MODEL_PATH} device={device} encode_batch_size={ENCODE_BATCH_SIZE} '
        f'unique_texts={len({text for pair in all_rows for text in pair[:2]})}'
    )
    model = SentenceTransformer(MODEL_PATH, device=device, local_files_only=True)
    started = time.time()
    cache = build_embedding_cache(model, all_rows)
    print(f'cache_built_secs={time.time() - started:.2f}')

    calib_pred = predict_rows(calib_rows, cache)
    calib_target = [s for _, _, s in calib_rows]
    calib = build_calibration(calib_pred, calib_target)
    CALIB_JSON.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding='utf-8')

    eval_raw = predict_rows(eval_rows, cache)
    eval_target = [s for _, _, s in eval_rows]
    eval_cal = [apply_calibration(v, calib['x_pred'], calib['y_calibrated']) for v in eval_raw]

    raw_mae, raw_acc = metric(eval_raw, eval_target)
    cal_mae, cal_acc = metric(eval_cal, eval_target)

    payload = {
        'eval_rows': len(eval_rows),
        'raw_mae': round(raw_mae, 6),
        'raw_bucket_acc': round(raw_acc, 6),
        'cal_mae': round(cal_mae, 6),
        'cal_bucket_acc': round(cal_acc, 6),
        'model_path': MODEL_PATH,
        'calib_csv': str(CALIB_CSV),
        'eval_csv': str(EVAL_CSV),
        'calib_json': str(CALIB_JSON),
    }

    print(f'eval_rows={len(eval_rows)}')
    print(f'raw_mae={raw_mae:.3f} raw_bucket_acc={raw_acc:.2f}%')
    print(f'cal_mae={cal_mae:.3f} cal_bucket_acc={cal_acc:.2f}%')
    print(f'written={CALIB_JSON}')

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'metrics_written={out}')


if __name__ == '__main__':
    main()
