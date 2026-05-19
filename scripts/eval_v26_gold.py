import json
import os
import argparse
from pathlib import Path
import time

from sentence_transformers import SentenceTransformer

from semantic_common import (
    apply_calibration,
    build_calibration,
    build_embedding_cache,
    metric,
    predict_scored_rows,
    read_scored_rows,
    resolve_device,
)

MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v27-semreal-anchor')
CALIB_CSV = Path(os.getenv('SEM_CALIB_CSV', 'data/gold_v26_calib.csv'))
EVAL_CSV = Path(os.getenv('SEM_EVAL_CSV', 'data/gold_v26_eval.csv'))
CALIB_JSON = Path(os.getenv('SEM_CALIB_JSON', 'data/semantic_calibration_v27_semreal_anchor.json'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()
ENCODE_BATCH_SIZE = int(os.getenv('SEM_ENCODE_BATCH_SIZE', '32'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json-out', default='')
    args = parser.parse_args()

    if not CALIB_CSV.exists() or not EVAL_CSV.exists():
        raise SystemExit('missing gold calib/eval csv')

    calib_rows = read_scored_rows(CALIB_CSV)
    eval_rows = read_scored_rows(EVAL_CSV)
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
    cache = build_embedding_cache(model, all_rows, ENCODE_BATCH_SIZE)
    print(f'cache_built_secs={time.time() - started:.2f}')

    calib_pred = predict_scored_rows(calib_rows, cache)
    calib_target = [s for _, _, s in calib_rows]
    calib = build_calibration(calib_pred, calib_target)
    CALIB_JSON.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding='utf-8')

    eval_raw = predict_scored_rows(eval_rows, cache)
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
