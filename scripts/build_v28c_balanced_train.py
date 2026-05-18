import csv
import json
import random
import os
from pathlib import Path
from collections import Counter

PUZZLES_JSON = Path(os.getenv('SEM_PUZZLES_JSON', 'assets/puzzles.json'))
MANUAL_OVERRIDES = Path(os.getenv('SEM_MANUAL_OVERRIDES', 'data/manual_similarity_overrides.json'))
GOLD_POOL = Path(os.getenv('SEM_GOLD_POOL', 'data/gold_v26_pool.csv'))
OUTPUT = Path(os.getenv('SEM_OUTPUT_CSV', 'data/train_v28c_balanced.csv'))

EXTRA_CSVS = [
    ('data/antonym_pairs_v28.csv', 'antonym_script'),
    ('data/function_word_pairs_v28.csv', 'function_word_script'),
    ('data/same_category_graded_v28.csv', 'category_graded_script'),
    ('data/subset_relation_pairs_v28.csv', 'subset_script'),
    ('data/synonym_expansion_v28.csv', 'synonym_script'),
]

HINT_MAX = int(os.getenv('SEM_HINT_MAX', '2000'))
SEED = int(os.getenv('SEM_SEED', '20260515'))

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer',
]

HARD_NEG_TAGS = {
    'antonym_low', 'function_word_low', 'function_word_vs_real_low',
    'hard_negative_low', 'hard_negative_mid', 'cross_category_low',
    'cross_category_negative', 'nonsense_low',
}


def main():
    seen = set()
    rows = []

    def push(answer, user_input, score, category, relation_tag, reason, reviewer):
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
        tag = relation_tag if relation_tag else 'unknown'
        left = max(0, score - 5)
        right = min(100, score + 5)
        rows.append({
            'id': '',
            'answer': a,
            'user_input': b,
            'answer_category': category,
            'input_category_guess': '',
            'relation_tag': tag,
            'expected_range': f'{left}-{right}',
            'score_0_100': str(score),
            'reason': reason,
            'reviewer': reviewer,
        })

    # 1. Manual overrides
    if MANUAL_OVERRIDES.exists():
        manual = json.loads(MANUAL_OVERRIDES.read_text(encoding='utf-8'))
        for item in manual:
            if not isinstance(item, dict):
                continue
            answer = str(item.get('answer', '')).strip()
            user_input = str(item.get('user_input', '')).strip()
            score = item.get('score')
            if not answer or not user_input or not isinstance(score, (int, float)):
                continue
            push(answer, user_input, int(round(float(score))), '', '', str(item.get('reason', '')), 'manual_gold')

    # 2. Gold pool
    if GOLD_POOL.exists():
        with GOLD_POOL.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                a = (row.get('answer') or '').strip()
                b = (row.get('user_input') or '').strip()
                s = (row.get('score_0_100') or '').strip()
                if not a or not b or not s:
                    continue
                try:
                    score = int(float(s))
                except ValueError:
                    continue
                push(a, b, score, row.get('answer_category', ''), row.get('relation_tag', ''),
                     row.get('reason', ''), row.get('reviewer', 'gold_v26'))

    # 3. Extra CSVs (all hard neg + synonym + category + subset data)
    for csv_path, reviewer in EXTRA_CSVS:
        p = Path(csv_path)
        if not p.exists():
            continue
        count = 0
        with p.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                a = (row.get('answer') or '').strip()
                b = (row.get('user_input') or '').strip()
                s = (row.get('score_0_100') or '').strip()
                if not a or not b or not s:
                    continue
                try:
                    score = int(float(s))
                except ValueError:
                    continue
                push(a, b, score, '', row.get('relation_tag', ''), row.get('reason', ''), reviewer)
                count += 1
        print(f'  {csv_path}: +{count}')

    # 4. Puzzle self-anchors + hint pairs (LIMITED)
    puzzles = json.loads(PUZZLES_JSON.read_text(encoding='utf-8'))
    hint_targets = [30, 40, 50, 60, 70, 80, 90]
    hint_count = 0

    rng = random.Random(SEED)
    puzzle_hints = []
    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = [str(h).strip() for h in (item.get('hints') or [])]
        if not answer:
            continue
        push(answer, answer, 98, category, 'same_answer_exact', 'self anchor', 'auto_v28c')
        if len(hints) == 7:
            for idx, hint in enumerate(hints):
                if not hint:
                    continue
                target = hint_targets[idx]
                puzzle_hints.append((answer, hint, target, category, idx))

    rng.shuffle(puzzle_hints)
    for answer, hint, target, category, idx in puzzle_hints:
        if hint_count >= HINT_MAX:
            break
        push(answer, hint, target, category, '', f'puzzle_hint_lvl_{idx+1}', 'auto_v28c')
        if target >= 70:
            push(hint, answer, min(95, target + 5), category, '', f'reverse_hint_lvl_{idx+1}', 'auto_v28c')
        hint_count += 1

    # 5. Cross-category negatives
    from collections import defaultdict
    by_cat = defaultdict(list)
    all_answers = []
    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        if answer:
            all_answers.append(answer)
            by_cat[category].append(answer)

    unique_answers = list(dict.fromkeys(all_answers))
    answer_cat = {}
    for cat, arr in by_cat.items():
        for a in arr:
            answer_cat[a] = cat

    neg_per_answer = 2
    for ans in unique_answers:
        cat = answer_cat.get(ans, '')
        neg_pool = [x for x in unique_answers if x != ans and answer_cat.get(x, '') != cat]
        rng.shuffle(neg_pool)
        for neg in neg_pool[:neg_per_answer]:
            push(ans, neg, rng.choice([4, 6, 8, 10]), cat, 'cross_category_negative', 'cross_category_negative', 'auto_v28c')

    # Shuffle & ID
    rng.shuffle(rows)
    for i, row in enumerate(rows, 1):
        row['id'] = str(i)

    # Stats
    tag_counts = Counter(r['relation_tag'] for r in rows)
    score_buckets = Counter((int(r['score_0_100']) // 10) * 10 for r in rows)
    hard_count = sum(1 for r in rows if r['relation_tag'] in HARD_NEG_TAGS)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f'\n=== train_v28c_balanced.csv ===')
    print(f'Total: {len(rows)} rows')
    print(f'Hint rows capped at: {HINT_MAX}')
    print(f'Hard negatives: {hard_count} ({hard_count/len(rows)*100:.1f}%)')

    print(f'\nBy relation_tag:')
    for tag, cnt in tag_counts.most_common():
        marker = ' ★' if tag in HARD_NEG_TAGS else ''
        print(f'  {tag}: {cnt}{marker}')

    print(f'\nBy score bucket:')
    for b in sorted(score_buckets):
        print(f'  {b:3d}-{b+9:3d}: {score_buckets[b]:4d}')

    print(f'\nWritten: {OUTPUT}')


if __name__ == '__main__':
    main()
