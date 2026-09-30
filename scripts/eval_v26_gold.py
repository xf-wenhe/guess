import json
import os
import argparse
import csv
import math
from pathlib import Path
import time
from collections import defaultdict

from sentence_transformers import SentenceTransformer

from semantic_common import (
    apply_global_calibration,
    augment_masked_calibration_samples,
    augment_midpoint_calibration_samples,
    build_calibration,
    build_embedding_cache,
    metric,
    predict_scored_rows,
    read_scored_rows,
    resolve_device,
    score_bucket,
)

MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v27-semreal-anchor')
CALIB_CSV = Path(os.getenv('SEM_CALIB_CSV', 'data/gold_v26_calib.csv'))
EVAL_CSV = Path(os.getenv('SEM_EVAL_CSV', 'data/gold_v26_eval.csv'))
CALIB_JSON = Path(os.getenv('SEM_CALIB_JSON', 'data/semantic_calibration_v27_semreal_anchor.json'))
DEVICE = os.getenv('SEM_DEVICE', '').strip().lower()
ENCODE_BATCH_SIZE = int(os.getenv('SEM_ENCODE_BATCH_SIZE', '32'))
MIDPOINT_CALIB_TAGS = {
    item.strip()
    for item in os.getenv('SEM_CALIB_MIDPOINT_TAGS', 'antonym_mid').split(',')
    if item.strip()
}
MIDPOINT_CALIB_TARGET_LOW = float(os.getenv('SEM_CALIB_MIDPOINT_TARGET_LOW', '45'))
MIDPOINT_CALIB_TARGET_HIGH = float(os.getenv('SEM_CALIB_MIDPOINT_TARGET_HIGH', '55'))
# Smooth the global curve around sparse antonym calibration scores; evaluation
# still uses this same global curve, not a relation-aware output clamp.
MIDPOINT_CALIB_AUGMENT_RADIUS = float(os.getenv('SEM_CALIB_MIDPOINT_AUGMENT_RADIUS', '3.5'))
MIDPOINT_CALIB_AUGMENT_STEPS = int(os.getenv('SEM_CALIB_MIDPOINT_AUGMENT_STEPS', '2'))
MIDPOINT_CALIB_AUGMENT_WEIGHT = float(os.getenv('SEM_CALIB_MIDPOINT_AUGMENT_WEIGHT', '0.5'))
SUPPORT_POSITIVE_CALIB_TAGS = {
    item.strip()
    for item in os.getenv(
        'SEM_CALIB_SUPPORT_POSITIVE_TAGS',
        'same_category_mid,hint_like_high',
    ).split(',')
    if item.strip()
}
SUPPORT_POSITIVE_CALIB_TARGET_LOW = float(os.getenv('SEM_CALIB_SUPPORT_POSITIVE_TARGET_LOW', '40'))
SUPPORT_POSITIVE_CALIB_TARGET_HIGH = float(os.getenv('SEM_CALIB_SUPPORT_POSITIVE_TARGET_HIGH', '80'))
SUPPORT_POSITIVE_CALIB_AUGMENT_RADIUS = float(
    os.getenv('SEM_CALIB_SUPPORT_POSITIVE_AUGMENT_RADIUS', '2.0')
)
SUPPORT_POSITIVE_CALIB_AUGMENT_STEPS = int(
    os.getenv('SEM_CALIB_SUPPORT_POSITIVE_AUGMENT_STEPS', '2')
)
SUPPORT_POSITIVE_CALIB_AUGMENT_WEIGHT = float(
    os.getenv('SEM_CALIB_SUPPORT_POSITIVE_AUGMENT_WEIGHT', '0.05')
)
CALIBRATION_EVAL_MODE = 'global_curve_v1'

HARD_NEG_TAGS = {
    'function_word_low',
    'function_word_vs_real_low',
    'hard_negative_low',
    'hard_negative_mid',
    'cross_category_low',
    'cross_category_negative',
    'nonsense_low',
    'abstract_confusion',
}

ANTONYM_TAGS = {
    'antonym_low',
    'antonym_mid',
    'antonym_or_conflict',
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


def read_scored_weighted_rows(path: Path) -> list[tuple[str, str, float, float]]:
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
            sample_weight_raw = (row.get('sample_weight') or '').strip()
            try:
                sample_weight = float(sample_weight_raw) if sample_weight_raw else 1.0
            except ValueError:
                sample_weight = 1.0
            rows.append((answer, user_input, score, max(1e-6, sample_weight)))
    return rows


def eval_group(row: dict) -> str:
    tag = (row.get('relation_tag') or row.get('error_type') or '').strip()
    score = float(row['_score'])
    if tag in ANTONYM_TAGS:
        return 'antonym'
    if tag in HARD_NEG_TAGS or score < 30:
        return 'hard_negative'
    # Explicit relation tags must win over the high-score synonym fallback.
    # Keep the low-score fallback so the hard-negative gate retains its scope.
    if 'alias' in tag or 'synonym' in tag:
        return 'synonym_alias'
    if 'same_category' in tag:
        return 'same_category'
    if 'hint' in tag:
        return 'hint_like'
    if score >= 80:
        return 'synonym_alias'
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
        if name == 'antonym':
            hits = sum(1 for pred in values['cal'] if 40 <= pred <= 60)
            payload['mid_score_recall_40_60'] = round(
                hits / max(len(values['cal']), 1) * 100.0,
                6,
            )
            strict_hits = sum(1 for pred in values['cal'] if 45 <= pred <= 55)
            payload['mid_score_recall_45_55'] = round(
                strict_hits / max(len(values['cal']), 1) * 100.0,
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


def bucket_misses(rows: list[dict], raw_pred: list[float], cal_pred: list[float], limit: int) -> list[dict]:
    misses = []
    for row, raw, cal in zip(rows, raw_pred, cal_pred):
        target = float(row['_score'])
        target_bucket = score_bucket(target)
        raw_bucket = score_bucket(raw)
        cal_bucket = score_bucket(cal)
        if raw_bucket == target_bucket and cal_bucket == target_bucket:
            continue
        misses.append({
            'answer': row['_answer'],
            'user_input': row['_user_input'],
            'target': round(target, 3),
            'target_bucket': target_bucket,
            'raw_pred': round(raw, 3),
            'raw_bucket': raw_bucket,
            'raw_hit': raw_bucket == target_bucket,
            'cal_pred': round(cal, 3),
            'cal_bucket': cal_bucket,
            'cal_hit': cal_bucket == target_bucket,
            'relation_tag': (row.get('relation_tag') or row.get('error_type') or '').strip(),
            'group': eval_group(row),
            'cal_abs_error': round(abs(cal - target), 3),
        })
    misses.sort(key=lambda item: (item['cal_hit'], -item['cal_abs_error']))
    return misses[:limit]


def bucket_confusion(rows: list[dict], cal_pred: list[float], limit: int) -> list[dict]:
    summary = defaultdict(lambda: {'count': 0, 'errors': [], 'examples': [], 'tags': defaultdict(int), 'groups': defaultdict(int)})
    for row, cal in zip(rows, cal_pred):
        target = float(row['_score'])
        target_bucket = score_bucket(target)
        cal_bucket = score_bucket(cal)
        if cal_bucket == target_bucket:
            continue
        tag = (row.get('relation_tag') or row.get('error_type') or '').strip() or '(untagged)'
        group = eval_group(row)
        key = (target_bucket, cal_bucket)
        error = abs(cal - target)
        payload = summary[key]
        payload['count'] += 1
        payload['errors'].append(error)
        payload['tags'][tag] += 1
        payload['groups'][group] += 1
        if len(payload['examples']) < 3:
            payload['examples'].append(f"{row['_answer']}->{row['_user_input']}")

    rows_out = []
    for (target_bucket, cal_bucket), values in summary.items():
        errors = values['errors']
        rows_out.append({
            'target_bucket': target_bucket,
            'cal_bucket': cal_bucket,
            'count': values['count'],
            'avg_abs_error': round(sum(errors) / max(len(errors), 1), 3),
            'max_abs_error': round(max(errors), 3),
            'top_tags': [
                {'tag': tag, 'count': count}
                for tag, count in sorted(values['tags'].items(), key=lambda item: (-item[1], item[0]))[:3]
            ],
            'top_groups': [
                {'group': group, 'count': count}
                for group, count in sorted(values['groups'].items(), key=lambda item: (-item[1], item[0]))[:3]
            ],
            'examples': values['examples'],
        })
    rows_out.sort(key=lambda item: (-item['count'], -item['avg_abs_error'], item['target_bucket'], item['cal_bucket']))
    return rows_out[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json-out', default='')
    parser.add_argument('--top-errors', type=int, default=20)
    args = parser.parse_args()

    if not CALIB_CSV.exists() or not EVAL_CSV.exists():
        raise SystemExit('missing gold calib/eval csv')

    calib_rows = read_scored_rows(CALIB_CSV)
    calib_dict_rows = read_eval_dict_rows(CALIB_CSV)
    calib_weighted_rows = read_scored_weighted_rows(CALIB_CSV)
    eval_rows = read_scored_rows(EVAL_CSV)
    eval_dict_rows = read_eval_dict_rows(EVAL_CSV)
    if len(calib_rows) < 5 or len(eval_rows) < 5:
        raise SystemExit('gold rows too small')
    if len(calib_rows) != len(calib_dict_rows) or len(calib_rows) != len(calib_weighted_rows):
        raise SystemExit('calibration row readers are misaligned')
    if len(eval_rows) != len(eval_dict_rows):
        raise SystemExit('evaluation row readers are misaligned')

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
    calib_weights = [weight for _, _, _, weight in calib_weighted_rows]
    midpoint_mask = [
        (
            (row.get('relation_tag') or row.get('error_type') or '').strip() in MIDPOINT_CALIB_TAGS
            and MIDPOINT_CALIB_TARGET_LOW <= float(row['_score']) <= MIDPOINT_CALIB_TARGET_HIGH
        )
        for row in calib_dict_rows
    ]
    support_positive_mask = [
        (
            (row.get('relation_tag') or row.get('error_type') or '').strip()
            in SUPPORT_POSITIVE_CALIB_TAGS
            and SUPPORT_POSITIVE_CALIB_TARGET_LOW <= float(row['_score']) <= SUPPORT_POSITIVE_CALIB_TARGET_HIGH
        )
        for row in calib_dict_rows
    ]
    midpoint_pred = [value for value, selected in zip(calib_pred, midpoint_mask) if selected]
    global_midpoint_pred_aug, global_midpoint_target_aug, global_midpoint_weights_aug = (
        augment_midpoint_calibration_samples(
            calib_pred,
            calib_target,
            calib_weights,
            midpoint_mask,
            radius=MIDPOINT_CALIB_AUGMENT_RADIUS,
            steps=MIDPOINT_CALIB_AUGMENT_STEPS,
            weight_multiplier=MIDPOINT_CALIB_AUGMENT_WEIGHT,
        )
    )
    support_pred_aug, support_target_aug, support_weights_aug = augment_masked_calibration_samples(
        calib_pred,
        calib_target,
        calib_weights,
        support_positive_mask,
        radius=SUPPORT_POSITIVE_CALIB_AUGMENT_RADIUS,
        steps=SUPPORT_POSITIVE_CALIB_AUGMENT_STEPS,
        weight_multiplier=SUPPORT_POSITIVE_CALIB_AUGMENT_WEIGHT,
    )
    # Keep midpoint calibration support in the same global curve used at inference.
    calib_pred_aug = global_midpoint_pred_aug + support_pred_aug[len(calib_pred):]
    calib_target_aug = global_midpoint_target_aug + support_target_aug[len(calib_target):]
    calib_weights_aug = global_midpoint_weights_aug + support_weights_aug[len(calib_weights):]
    midpoint_calibration_augmented_rows = len(global_midpoint_pred_aug) - len(calib_pred)
    support_positive_calibration_augmented_rows = len(support_pred_aug) - len(calib_pred)
    calib = build_calibration(calib_pred_aug, calib_target_aug, calib_weights_aug)
    midpoint_raw_scores = [
        float(value)
        for value in midpoint_pred
        if math.isfinite(float(value))
    ]
    midpoint_interval_low = None
    midpoint_interval_high = None
    if midpoint_raw_scores and MIDPOINT_CALIB_AUGMENT_RADIUS > 0.0:
        midpoint_interval_low = max(
            0.0,
            min(midpoint_raw_scores) - MIDPOINT_CALIB_AUGMENT_RADIUS,
        )
        midpoint_interval_high = min(
            100.0,
            max(midpoint_raw_scores) + MIDPOINT_CALIB_AUGMENT_RADIUS,
        )
    calib["midpoint_calibration_interval_low"] = midpoint_interval_low
    calib["midpoint_calibration_interval_high"] = midpoint_interval_high
    calib["midpoint_calibration_target_low"] = MIDPOINT_CALIB_TARGET_LOW
    calib["midpoint_calibration_target_high"] = MIDPOINT_CALIB_TARGET_HIGH
    CALIB_JSON.write_text(json.dumps(calib, ensure_ascii=False, indent=2), encoding='utf-8')

    eval_raw = predict_scored_rows(eval_rows, cache)
    eval_target = [s for _, _, s in eval_rows]
    eval_cal = [apply_global_calibration(raw, calib) for raw in eval_raw]

    raw_mae, raw_acc = metric(eval_raw, eval_target)
    cal_mae, cal_acc = metric(eval_cal, eval_target)

    payload = {
        'eval_rows': len(eval_rows),
        'calibration_eval_mode': CALIBRATION_EVAL_MODE,
        'raw_mae': round(raw_mae, 6),
        'raw_bucket_acc': round(raw_acc, 6),
        'cal_mae': round(cal_mae, 6),
        'cal_bucket_acc': round(cal_acc, 6),
        'group_metrics': grouped_metrics(eval_dict_rows, eval_raw, eval_cal),
        'worst_cases': worst_cases(eval_dict_rows, eval_raw, eval_cal, args.top_errors),
        'bucket_misses': bucket_misses(eval_dict_rows, eval_raw, eval_cal, args.top_errors),
        'bucket_confusion': bucket_confusion(eval_dict_rows, eval_cal, args.top_errors),
        'model_path': MODEL_PATH,
        'calib_csv': str(CALIB_CSV),
        'eval_csv': str(EVAL_CSV),
        'calib_json': str(CALIB_JSON),
        'calibration_method': calib.get('method', 'unknown'),
        'midpoint_calibration_tags': sorted(MIDPOINT_CALIB_TAGS),
        'midpoint_calibration_rows': sum(1 for flag in midpoint_mask if flag),
        'midpoint_calibration_augmented_rows': midpoint_calibration_augmented_rows,
        'midpoint_calibration_augment_radius': MIDPOINT_CALIB_AUGMENT_RADIUS,
        'midpoint_calibration_augment_steps': MIDPOINT_CALIB_AUGMENT_STEPS,
        'midpoint_calibration_augment_weight': MIDPOINT_CALIB_AUGMENT_WEIGHT,
        'midpoint_calibration_interval_low': midpoint_interval_low,
        'midpoint_calibration_interval_high': midpoint_interval_high,
        'midpoint_calibration_target_low': MIDPOINT_CALIB_TARGET_LOW,
        'midpoint_calibration_target_high': MIDPOINT_CALIB_TARGET_HIGH,
        'support_positive_calibration_tags': sorted(SUPPORT_POSITIVE_CALIB_TAGS),
        'support_positive_calibration_rows': sum(1 for flag in support_positive_mask if flag),
        'support_positive_calibration_augmented_rows': support_positive_calibration_augmented_rows,
        'support_positive_calibration_target_low': SUPPORT_POSITIVE_CALIB_TARGET_LOW,
        'support_positive_calibration_target_high': SUPPORT_POSITIVE_CALIB_TARGET_HIGH,
        'support_positive_calibration_augment_radius': SUPPORT_POSITIVE_CALIB_AUGMENT_RADIUS,
        'support_positive_calibration_augment_steps': SUPPORT_POSITIVE_CALIB_AUGMENT_STEPS,
        'support_positive_calibration_augment_weight': SUPPORT_POSITIVE_CALIB_AUGMENT_WEIGHT,
    }

    print(f'eval_rows={len(eval_rows)}')
    print(f'raw_mae={raw_mae:.3f} raw_bucket_acc={raw_acc:.2f}%')
    print(f'cal_mae={cal_mae:.3f} cal_bucket_acc={cal_acc:.2f}%')
    print(f"calibration_method={calib.get('method', 'unknown')}")
    print(
        f'midpoint_calibration_rows={sum(1 for flag in midpoint_mask if flag)} '
        f'augmented_rows={midpoint_calibration_augmented_rows}'
    )
    if midpoint_interval_low is not None and midpoint_interval_high is not None:
        print(
            f'midpoint_calibration_interval={midpoint_interval_low:.6f}-'
            f'{midpoint_interval_high:.6f} '
            f'target={MIDPOINT_CALIB_TARGET_LOW:.6f}-{MIDPOINT_CALIB_TARGET_HIGH:.6f}'
        )
    print(
        f'support_positive_calibration_rows={sum(1 for flag in support_positive_mask if flag)} '
        f'augmented_rows={support_positive_calibration_augmented_rows}'
    )
    print(f'written={CALIB_JSON}')

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'metrics_written={out}')


if __name__ == '__main__':
    main()
