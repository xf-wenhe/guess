import csv
import json
import os
import random
from collections import defaultdict
from pathlib import Path

MANUAL_OVERRIDES = Path(os.getenv('SEM_MANUAL_OVERRIDES', 'data/manual_similarity_overrides.json'))
PUZZLES_JSON = Path(os.getenv('SEM_PUZZLES_JSON', 'assets/puzzles.json'))
SCORED_CSV = Path(os.getenv('SEM_SCORED_CSV', 'data/semantic_scoring_user_input_template.csv'))

GOLD_POOL_CSV = Path(os.getenv('SEM_GOLD_POOL_CSV', 'data/gold_v26_pool.csv'))
GOLD_CALIB_CSV = Path(os.getenv('SEM_GOLD_CALIB_CSV', 'data/gold_v26_calib.csv'))
GOLD_EVAL_CSV = Path(os.getenv('SEM_GOLD_EVAL_CSV', 'data/gold_v26_eval.csv'))
GOLD_MANUAL_ANCHOR_CSV = Path(os.getenv('SEM_GOLD_MANUAL_ANCHOR_CSV', 'data/gold_v26_manual_anchor.csv'))
UNSUP_PAIRS_JSONL = Path(os.getenv('SEM_UNSUP_PAIRS_JSONL', 'data/unsupervised_pairs_v26.jsonl'))

SEED = int(os.getenv('SEM_SEED', '20260303'))
CALIB_RATIO = float(os.getenv('SEM_GOLD_CALIB_RATIO', '0.55'))
TARGET_GOLD_TOTAL = int(os.getenv('SEM_GOLD_TARGET_TOTAL', '260'))

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer'
]

ANGLES = [
    '从含义角度看：',
    '从用途角度看：',
    '从场景角度看：',
    '从特征角度看：',
    '从关联角度看：',
]


def score_bin(score: float) -> str:
    if score < 20:
        return '0-19'
    if score < 40:
        return '20-39'
    if score < 60:
        return '40-59'
    if score < 80:
        return '60-79'
    return '80-100'


def range_for_score(score: int) -> str:
    left = max(0, score - 5)
    right = min(100, score + 5)
    return f'{left}-{right}'


def relation_for_score(score: int) -> str:
    if score >= 85:
        return 'alias_synonym_high'
    if score >= 70:
        return 'near_synonym_high'
    if score >= 50:
        return 'related_mid'
    if score >= 30:
        return 'related_low'
    return 'hard_negative_low'


def load_manual_gold(path: Path):
    rows = []
    decoded = json.loads(path.read_text(encoding='utf-8'))
    for item in decoded:
        answer = str(item.get('answer', '')).strip()
        user_input = str(item.get('user_input', '')).strip()
        score = item.get('score')
        reason = str(item.get('reason', '')).strip()
        if not answer or not user_input or not isinstance(score, (int, float)):
            continue
        score_i = int(round(float(score)))
        rows.append({
            'id': '',
            'answer': answer,
            'user_input': user_input,
            'answer_category': '',
            'input_category_guess': '',
            'relation_tag': relation_for_score(score_i),
            'expected_range': range_for_score(score_i),
            'score_0_100': str(score_i),
            'reason': reason or 'manual gold',
            'reviewer': 'manual_gold_v26',
        })
    return rows


def load_scored_gold_candidates(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
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
            if not (0 <= score <= 100):
                continue
            score_i = int(round(score))
            reason = (row.get('reason') or '').strip() or 'scored gold candidate'
            reviewer = (row.get('reviewer') or '').strip() or 'gold_candidate_v26'
            relation_tag = (row.get('relation_tag') or '').strip() or relation_for_score(score_i)
            expected_range = (row.get('expected_range') or '').strip() or range_for_score(score_i)

            rows.append({
                'id': '',
                'answer': answer,
                'user_input': user_input,
                'answer_category': (row.get('answer_category') or '').strip(),
                'input_category_guess': (row.get('input_category_guess') or '').strip(),
                'relation_tag': relation_tag,
                'expected_range': expected_range,
                'score_0_100': str(score_i),
                'reason': reason,
                'reviewer': reviewer,
            })
    return rows


def stratified_sample(rows, n_target: int, seed: int):
    if n_target <= 0 or not rows:
        return []
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for row in rows:
        buckets[score_bin(float(row['score_0_100']))].append(row)

    bucket_items = list(buckets.items())
    for _, bucket_rows in bucket_items:
        rng.shuffle(bucket_rows)

    total = sum(len(v) for _, v in bucket_items)
    if total <= n_target:
        out = []
        for _, bucket_rows in bucket_items:
            out.extend(bucket_rows)
        rng.shuffle(out)
        return out

    out = []
    remain = n_target
    remain_total = total

    for idx, (_, bucket_rows) in enumerate(bucket_items):
        left_buckets = len(bucket_items) - idx
        if remain <= 0:
            break
        if left_buckets == 1:
            take = min(len(bucket_rows), remain)
        else:
            take = int(round(remain * len(bucket_rows) / max(remain_total, 1)))
            if take == 0 and bucket_rows:
                take = 1
            take = min(len(bucket_rows), take)
            take = min(take, remain - (left_buckets - 1))
            take = max(0, take)

        out.extend(bucket_rows[:take])
        remain -= take
        remain_total -= len(bucket_rows)

    if len(out) < n_target:
        left = []
        used = {(r['answer'], r['user_input']) for r in out}
        for _, bucket_rows in bucket_items:
            for row in bucket_rows:
                key = (row['answer'], row['user_input'])
                if key not in used:
                    left.append(row)
        rng.shuffle(left)
        out.extend(left[: n_target - len(out)])

    rng.shuffle(out)
    return out[:n_target]


def dedup_pair_rows(rows):
    result = []
    seen = set()
    for row in rows:
        key = (row['answer'], row['user_input'])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    for i, row in enumerate(result, start=1):
        row['id'] = str(i)
    return result


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def split_gold(rows):
    rng = random.Random(SEED)
    buckets = defaultdict(list)
    for row in rows:
        buckets[score_bin(float(row['score_0_100']))].append(row)

    calib, eval_rows = [], []
    for _, bucket_rows in buckets.items():
        rng.shuffle(bucket_rows)
        n = len(bucket_rows)
        n_calib = int(round(n * CALIB_RATIO))
        if n >= 2:
            n_calib = max(1, min(n - 1, n_calib))
        else:
            n_calib = n
        calib.extend(bucket_rows[:n_calib])
        eval_rows.extend(bucket_rows[n_calib:])

    rng.shuffle(calib)
    rng.shuffle(eval_rows)

    for i, row in enumerate(calib, start=1):
        row['id'] = str(i)
    for i, row in enumerate(eval_rows, start=1):
        row['id'] = str(i)
    return calib, eval_rows


def build_unsup_pairs_from_puzzles(path: Path):
    decoded = json.loads(path.read_text(encoding='utf-8'))
    pairs = []
    seen = set()

    def push(a: str, b: str):
        aa = a.strip()
        bb = b.strip()
        if not aa or not bb:
            return
        key = (aa, bb)
        if key in seen:
            return
        seen.add(key)
        pairs.append({'text_a': aa, 'text_b': bb})

    for item in decoded:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = [str(h).strip() for h in (item.get('hints') or []) if str(h).strip()]
        if not answer:
            continue

        for hint in hints:
            push(answer, hint)
            push(hint, answer)

        if category:
            push(answer, f'{category}类')

        for angle in ANGLES:
            push(f'{angle}{answer}', answer)

    return pairs


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def main():
    if not MANUAL_OVERRIDES.exists():
        raise SystemExit(f'missing file: {MANUAL_OVERRIDES}')
    if not PUZZLES_JSON.exists():
        raise SystemExit(f'missing file: {PUZZLES_JSON}')

    manual_rows = dedup_pair_rows(load_manual_gold(MANUAL_OVERRIDES))
    scored_rows = dedup_pair_rows(load_scored_gold_candidates(SCORED_CSV))

    manual_keys = {(r['answer'], r['user_input']) for r in manual_rows}
    scored_rows = [r for r in scored_rows if (r['answer'], r['user_input']) not in manual_keys]

    need_extra = max(0, TARGET_GOLD_TOTAL - len(manual_rows))
    sampled_scored = stratified_sample(scored_rows, need_extra, SEED)

    gold_rows = dedup_pair_rows([*manual_rows, *sampled_scored])
    calib_rows, eval_rows = split_gold([dict(x) for x in gold_rows])

    unsup_pairs = build_unsup_pairs_from_puzzles(PUZZLES_JSON)

    write_csv(GOLD_POOL_CSV, gold_rows)
    write_csv(GOLD_MANUAL_ANCHOR_CSV, manual_rows)
    write_csv(GOLD_CALIB_CSV, calib_rows)
    write_csv(GOLD_EVAL_CSV, eval_rows)
    write_jsonl(UNSUP_PAIRS_JSONL, unsup_pairs)

    print(
        f'gold_manual={len(manual_rows)} gold_scored_sampled={len(sampled_scored)} '
        f'gold_pool={len(gold_rows)} calib={len(calib_rows)} eval={len(eval_rows)}'
    )
    print(f'unsup_pairs={len(unsup_pairs)}')
    print(
        f'written={GOLD_POOL_CSV} {GOLD_MANUAL_ANCHOR_CSV} '
        f'{GOLD_CALIB_CSV} {GOLD_EVAL_CSV} {UNSUP_PAIRS_JSONL}'
    )


if __name__ == '__main__':
    main()