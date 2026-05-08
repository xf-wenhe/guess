import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

PUZZLES_PATH = Path('assets/puzzles.json')
MODEL_PATH = 'models/bge-m3-finetuned-v26-unsup'
CALIB_PATH = Path('data/semantic_calibration_v26_gold.json')
TARGETS = [30, 40, 50, 60, 70, 80, 90]


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


def main():
    data = json.loads(PUZZLES_PATH.read_text(encoding='utf-8'))
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    x = calib['x_pred']
    y = calib['y_calibrated']

    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)

    low = []
    total = 0
    mae_sum = 0.0

    for item in data:
        ans = str(item.get('answer', '')).strip()
        hints = [str(h).strip() for h in (item.get('hints') or [])]
        if not ans or len(hints) != 7:
            continue
        total += 1
        ans_vec = model.encode([ans], normalize_embeddings=True)[0]
        scores = []
        for idx, h in enumerate(hints):
            hv = model.encode([h], normalize_embeddings=True)[0]
            raw = float(np.dot(ans_vec, hv) * 100.0)
            cal = float(apply_calibration(raw, x, y))
            scores.append(cal)
            if cal < max(12, TARGETS[idx] - 18):
                low.append({
                    'answer': ans,
                    'hint': h,
                    'index': idx,
                    'target': TARGETS[idx],
                    'score': round(cal, 2),
                })
        mae_sum += sum(abs(s - t) for s, t in zip(scores, TARGETS)) / 7.0

    report = {
        'items': total,
        'low_count': len(low),
        'avg_target_mae': round(mae_sum / max(total, 1), 3),
        'low_top50': low[:50],
    }
    out = Path('tmp/hints_audit_v28_before.json')
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"items={total} low_count={len(low)} avg_target_mae={report['avg_target_mae']}")
    print(f'written={out}')


if __name__ == '__main__':
    main()
