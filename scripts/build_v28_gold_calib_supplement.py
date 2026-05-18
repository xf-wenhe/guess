import csv
import random
from pathlib import Path
from collections import Counter

TRAIN_CSV = Path('data/train_v28_phoenix.csv')
CALIB_CSV = Path('data/gold_v26_calib.csv')
EVAL_CSV = Path('data/gold_v26_eval.csv')
OUTPUT_CALIB = Path('data/gold_v28_calib.csv')
OUTPUT_EVAL = Path('data/gold_v28_eval.csv')

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer',
]

SUPPLEMENT_TARGETS = {
    (60, 69): 10,
    (70, 79): 15,
    (80, 89): 15,
    (90, 95): 8,
}


def main():
    calib_rows = []
    with CALIB_CSV.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            calib_rows.append(row)

    eval_rows = []
    with EVAL_CSV.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            eval_rows.append(row)

    train_rows = []
    with TRAIN_CSV.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            train_rows.append(row)

    calib_scores = [int(float(r.get('score_0_100', 0))) for r in calib_rows]
    print(f'Original calib: {len(calib_rows)} rows')
    buckets = Counter((s // 10) * 10 for s in calib_scores)
    for b in sorted(buckets):
        print(f'  {b:3d}-{b+9:3d}: {buckets[b]:3d}')

    train_by_score = {}
    for r in train_rows:
        s = int(float(r.get('score_0_100', 0)))
        bucket = (s // 10) * 10
        if bucket not in train_by_score:
            train_by_score[bucket] = []
        train_by_score[bucket].append(r)

    rng = random.Random(20260515)
    supplements = []

    for (lo, hi), target_count in SUPPLEMENT_TARGETS.items():
        current = sum(1 for s in calib_scores if lo <= s <= hi)
        needed = max(0, target_count - current)
        if needed == 0:
            print(f'  {lo}-{hi}: already {current}, skip')
            continue

        candidates = []
        for bucket in range(lo, hi + 1, 10):
            candidates.extend(train_by_score.get(bucket, []))

        rng.shuffle(candidates)
        picked = candidates[:needed]
        for r in picked:
            r2 = dict(r)
            r2['reviewer'] = 'calib_supplement_v28'
            r2['reason'] = f'校准补充:{r2.get("reason", "")}'
            supplements.append(r2)
        print(f'  {lo}-{hi}: had {current}, adding {len(picked)}')

    new_calib = calib_rows + supplements
    rng.shuffle(new_calib)

    max_id = 0
    for row in new_calib:
        try:
            rid = int(row.get('id', 0))
            if rid > max_id:
                max_id = rid
        except ValueError:
            pass
    for i, row in enumerate(new_calib):
        row['id'] = str(max_id + i + 1)

    OUTPUT_CALIB.parent.mkdir(parents=True, exist_ok=True)
    fn = fieldnames or FIELDNAMES
    with OUTPUT_CALIB.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fn)
        writer.writeheader()
        writer.writerows(new_calib)

    with OUTPUT_EVAL.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fn)
        writer.writeheader()
        writer.writerows(eval_rows)

    new_scores = [int(float(r.get('score_0_100', 0))) for r in new_calib]
    new_buckets = Counter((s // 10) * 10 for s in new_scores)
    print(f'\nNew calib: {len(new_calib)} rows (original {len(calib_rows)} + supplement {len(supplements)})')
    for b in sorted(new_buckets):
        print(f'  {b:3d}-{b+9:3d}: {new_buckets[b]:3d}')

    print(f'\nWritten: {OUTPUT_CALIB}')
    print(f'Written: {OUTPUT_EVAL}')


if __name__ == '__main__':
    main()
