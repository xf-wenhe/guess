import json
import os
import argparse
import csv
from pathlib import Path
import time
from collections import defaultdict

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

HARD_NEG_TAGS = {
    'antonym_low',
    'function_word_low',
    'function_word_vs_real_low',
    'hard_negative_low',
    'hard_negative_mid',
    'cross_category_low',
    'cross_category_negative',
    'nonsense_low',
    'abstract_confusion',
}


def read_eval_dict_rows(path: Path) -> list[dict]:
    rows = []
    with path.open('r', encoding='utf-8', newline='') as file:
        for row in csv.DictReader(file):
            answer = (row.get('answer') or '').strip()
            user_input = (row.get('user_input') or '').strip()
            score_raw = (row.get('score_0_100') or '').strip()
            if not answer or not user_input or not score_raw:
                continue
            try:
                score = float(score_raw)
            except ValueError:
                continue
            row['_answer'] = answer
            row['_user_input'] = user_input
            row['_score'] = score
            rows.append(row)
    return rows


def eval_group(row: dict) -> str:
    tag = (row.get('relation_tag') or row.get('error_type') or '').strip()
    score = float(row['_score'])
    if tag in HARD_NEG_TAGS or score < 30:
        return 'hard_negative'
    if 'alias' in tag or 'synonym' in tag or score >= 80:
        return 'synonym_alias'
    if 'same_category' in tag:
        return 'same_category'
    if 'hint' in tag:
        return 'hint_like'
    return 'other'


def grouped_metrics(rows: list[dict], raw_pred: list[float], cal_pred: list[float]) -> dict:
    grouped = defaultdict(lambda: {'target': [], 'raw': [], 'cal': []})
    for row, raw, cal in zip(rows, raw_pred, cal_pred):
        bucket = eval_group(row)
        grouped[bucket]['target'].append(float(row['_score']))
        grouped[bucket]['raw'].append(raw)
        grouped[bucket]['cal'].append(cal)

    result = {}
    for name, values in sorted(grouped.items()):
        raw_mae, raw_acc = metric(values['raw'], values['target'])
        cal_mae, cal_acc = metric(values['cal'], values['target'])
        payload = {
            'count': len(values['target']),
            'raw_mae': round(raw_mae, 6),
            'raw_bucket_acc': round(raw_acc, 6),
            'cal_mae': round(cal_mae, 6),
            'cal_bucket_acc': round(cal_acc, 6),
        }
        if name == 'synonym_alias':
            hits = sum(1 for pred in values['cal'] if pred >= 70)
            payload['recall_at_70'] = round(hits / max(len(values['cal']), 1) * 100.0, 6)
        if name == 'hard_negative':
            hits = sum(1 for pred in values['cal'] if pred <= 30)
            payload['low_score_precision_at_30'] = round(
                hits / max(len(values['cal']), 1) * 100.0,
                6,
            )
        result[name] = payload
    return result


def worst_cases(rows: list[dict], raw_pred: list[float], cal_pred: list[float], limit: int) -> list[dict]:
    cases = []
    for row, raw, cal in zip(rows, raw_pred, cal_pred):
        target = float(row['_score'])
        cases.append({
            'answer': row['_answer'],
            'user_input': row['_user_input'],
            'target': round(target, 3),
            'raw_pred': round(raw, 3),
            'cal_pred': round(cal, 3),
            'abs_error': round(abs(cal - target), 3),
            'relation_tag': (row.get('relation_tag') or row.get('error_type') or '').strip(),
            'group': eval_group(row),
        })
    cases.sort(key=lambda item: item['abs_error'], reverse=True)
    return cases[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json-out', default='')
    parser.add_argument('--top-errors', type=int, default=20)
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
    eval_dict_rows = read_eval_dict_rows(EVAL_CSV)

    raw_mae, raw_acc = metric(eval_raw, eval_target)
    cal_mae, cal_acc = metric(eval_cal, eval_target)

    payload = {
        'eval_rows': len(eval_rows),
        'raw_mae': round(raw_mae, 6),
        'raw_bucket_acc': round(raw_acc, 6),
        'cal_mae': round(cal_mae, 6),
        'cal_bucket_acc': round(cal_acc, 6),
        'group_metrics': grouped_metrics(eval_dict_rows, eval_raw, eval_cal),
        'worst_cases': worst_cases(eval_dict_rows, eval_raw, eval_cal, args.top_errors),
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
