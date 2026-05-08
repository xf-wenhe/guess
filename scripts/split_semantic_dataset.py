import csv
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

INPUT_CSV = Path(os.getenv('SEM_INPUT_CSV', 'data/semantic_scoring_user_input_template.csv'))
OUTPUT_DIR = Path(os.getenv('SEM_OUTPUT_DIR', 'data/splits'))
TRAIN_CSV = OUTPUT_DIR / 'semantic_train.csv'
CALIB_CSV = OUTPUT_DIR / 'semantic_calib.csv'
HOLDOUT_CSV = OUTPUT_DIR / 'semantic_holdout.csv'
META_JSON = OUTPUT_DIR / 'semantic_split_meta.json'

SEED = 20260227
TRAIN_RATIO = 0.70
CALIB_RATIO = 0.15
HOLDOUT_RATIO = 0.15


def score_bin(score: float) -> str:
    if score < 20:
        return '0-19'
    if score < 40:
        return '20-39'
    if score < 60:
        return '40-59'
    if score < 80:
        return '60-79'
    if score < 100:
        return '80-99'
    return '100'


def load_rows(path: Path):
    rows = []
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            answer = (row.get('answer') or '').strip()
            user_input = (row.get('user_input') or '').strip()
            score_raw = (row.get('score_0_100') or '').strip()
            if not answer or not user_input or not score_raw:
                continue
            try:
                score = float(score_raw)
            except ValueError:
                continue
            if 0 <= score <= 100:
                rows.append(row)
    return fieldnames, rows


def compute_bucket_key(row: dict) -> str:
    score = float((row.get('score_0_100') or '0').strip())
    relation_tag = (row.get('relation_tag') or '').strip() or 'unknown'
    return f"{score_bin(score)}|{relation_tag}"


def split_rows(rows):
    random.seed(SEED)

    buckets = defaultdict(list)
    for row in rows:
        buckets[compute_bucket_key(row)].append(row)

    train_rows, calib_rows, holdout_rows = [], [], []

    for _, bucket_rows in buckets.items():
        random.shuffle(bucket_rows)
        n = len(bucket_rows)

        n_train = int(round(n * TRAIN_RATIO))
        n_calib = int(round(n * CALIB_RATIO))

        if n >= 3:
            n_train = min(max(1, n_train), n - 2)
            n_calib = min(max(1, n_calib), n - n_train - 1)
        elif n == 2:
            n_train = 1
            n_calib = 0
        else:
            n_train = 1
            n_calib = 0

        n_holdout = n - n_train - n_calib
        if n >= 3 and n_holdout <= 0:
            n_holdout = 1
            if n_train > n_calib:
                n_train -= 1
            else:
                n_calib = max(0, n_calib - 1)

        train_rows.extend(bucket_rows[:n_train])
        calib_rows.extend(bucket_rows[n_train:n_train + n_calib])
        holdout_rows.extend(bucket_rows[n_train + n_calib:])

    random.shuffle(train_rows)
    random.shuffle(calib_rows)
    random.shuffle(holdout_rows)

    return train_rows, calib_rows, holdout_rows


def write_csv(path: Path, fieldnames, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    scores = [float(r['score_0_100']) for r in rows]
    bins = Counter(score_bin(s) for s in scores)
    return {
        'rows': len(rows),
        'min_score': min(scores) if scores else None,
        'max_score': max(scores) if scores else None,
        'bins': dict(sorted(bins.items())),
    }


def main():
    if not INPUT_CSV.exists():
        raise SystemExit(f'missing file: {INPUT_CSV}')

    if abs((TRAIN_RATIO + CALIB_RATIO + HOLDOUT_RATIO) - 1.0) > 1e-9:
        raise SystemExit('split ratios must sum to 1.0')

    fieldnames, rows = load_rows(INPUT_CSV)
    if len(rows) < 100:
        raise SystemExit('not enough valid rows to split (<100)')

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    train_rows, calib_rows, holdout_rows = split_rows(rows)

    write_csv(TRAIN_CSV, fieldnames, train_rows)
    write_csv(CALIB_CSV, fieldnames, calib_rows)
    write_csv(HOLDOUT_CSV, fieldnames, holdout_rows)

    meta = {
        'seed': SEED,
        'ratios': {
            'train': TRAIN_RATIO,
            'calib': CALIB_RATIO,
            'holdout': HOLDOUT_RATIO,
        },
        'input_rows': len(rows),
        'splits': {
            'train': summarize(train_rows),
            'calib': summarize(calib_rows),
            'holdout': summarize(holdout_rows),
        },
        'files': {
            'train_csv': str(TRAIN_CSV),
            'calib_csv': str(CALIB_CSV),
            'holdout_csv': str(HOLDOUT_CSV),
        },
    }
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"input_rows={len(rows)}")
    print(f"train={len(train_rows)} calib={len(calib_rows)} holdout={len(holdout_rows)}")
    print(f"written={TRAIN_CSV} {CALIB_CSV} {HOLDOUT_CSV} {META_JSON}")


if __name__ == '__main__':
    main()
