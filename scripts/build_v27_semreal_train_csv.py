import csv
import json
import os
import random
from collections import defaultdict
from pathlib import Path

PUZZLES_JSON = Path(os.getenv('SEM_PUZZLES_JSON', 'assets/puzzles.json'))
MANUAL_OVERRIDES = Path(os.getenv('SEM_MANUAL_OVERRIDES', 'data/manual_similarity_overrides.json'))
OUTPUT_CSV = Path(os.getenv('SEM_OUTPUT_CSV', 'data/train_v27_semreal.csv'))
SEED = int(os.getenv('SEM_SEED', '20260304'))
MAX_NEG_PER_ANSWER = int(os.getenv('SEM_MAX_NEG_PER_ANSWER', '4'))

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer'
]

TARGETS = [30, 40, 50, 60, 70, 80, 90]


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


def range_for_score(score: int) -> str:
    left = max(0, score - 5)
    right = min(100, score + 5)
    return f'{left}-{right}'


def push(rows, seen, answer, user_input, score, category, reason, reviewer):
    a = str(answer).strip()
    b = str(user_input).strip()
    if not a or not b:
        return
    if a == b:
        score = max(score, 96)
    score = int(max(0, min(100, round(float(score)))))
    key = (a, b)
    if key in seen:
        return
    seen.add(key)
    rows.append({
        'id': '',
        'answer': a,
        'user_input': b,
        'answer_category': category,
        'input_category_guess': '',
        'relation_tag': relation_for_score(score),
        'expected_range': range_for_score(score),
        'score_0_100': str(score),
        'reason': reason,
        'reviewer': reviewer,
    })


def main():
    if not PUZZLES_JSON.exists():
        raise SystemExit(f'missing file: {PUZZLES_JSON}')

    rng = random.Random(SEED)

    puzzles = json.loads(PUZZLES_JSON.read_text(encoding='utf-8'))
    rows = []
    seen = set()

    by_cat = defaultdict(list)
    all_answers = []

    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = [str(h).strip() for h in (item.get('hints') or [])]
        if not answer:
            continue

        all_answers.append(answer)
        by_cat[category].append(answer)

        push(rows, seen, answer, answer, 98, category, 'self anchor', 'auto_semreal_v27')

        if len(hints) == 7:
            for idx, hint in enumerate(hints):
                if not hint:
                    continue
                target = TARGETS[idx]
                push(rows, seen, answer, hint, target, category, f'puzzle_hint_lvl_{idx+1}', 'auto_semreal_v27')
                if target >= 70:
                    push(rows, seen, hint, answer, min(95, target + 5), category, f'reverse_hint_lvl_{idx+1}', 'auto_semreal_v27')

    # Add manual overrides as high-quality anchors
    if MANUAL_OVERRIDES.exists():
        try:
            manual = json.loads(MANUAL_OVERRIDES.read_text(encoding='utf-8'))
        except Exception:
            manual = []
        for item in manual:
            if not isinstance(item, dict):
                continue
            answer = str(item.get('answer', '')).strip()
            user_input = str(item.get('user_input', '')).strip()
            score = item.get('score')
            if not answer or not user_input or not isinstance(score, (int, float)):
                continue
            category = ''
            push(rows, seen, answer, user_input, int(round(float(score))), category, 'manual_override', 'manual_gold')

    # Hard negatives: cross-category random answers
    unique_answers = list(dict.fromkeys(all_answers))
    answer_cat = {}
    for cat, arr in by_cat.items():
        for a in arr:
            answer_cat[a] = cat

    for ans in unique_answers:
        cat = answer_cat.get(ans, '')
        neg_pool = [x for x in unique_answers if x != ans and answer_cat.get(x, '') != cat]
        rng.shuffle(neg_pool)
        for neg in neg_pool[:MAX_NEG_PER_ANSWER]:
            push(rows, seen, ans, neg, rng.choice([4, 6, 8, 10, 12]), cat, 'cross_category_negative', 'auto_semreal_v27')

    rng.shuffle(rows)
    for i, row in enumerate(rows, start=1):
        row['id'] = str(i)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f'rows={len(rows)}')
    print(f'written={OUTPUT_CSV}')


if __name__ == '__main__':
    main()
