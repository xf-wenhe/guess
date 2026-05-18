import csv
import json
import random
from pathlib import Path
from collections import Counter

MANUAL_OVERRIDES = Path('data/manual_similarity_overrides.json')
GOLD_POOL = Path('data/gold_v26_pool.csv')
OUTPUT = Path('data/train_v28_phoenix.csv')

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer',
]

EXTRA_CSVS = [
    ('data/antonym_pairs_v28.csv', 'antonym_script'),
    ('data/function_word_pairs_v28.csv', 'function_word_script'),
    ('data/same_category_graded_v28.csv', 'category_graded_script'),
    ('data/subset_relation_pairs_v28.csv', 'subset_script'),
    ('data/synonym_expansion_v28.csv', 'synonym_script'),
]

PUZZLES_JSON = Path('assets/puzzles.json')

def relation_for_score(score: int) -> str:
    if score >= 90:
        return 'alias_synonym_high'
    if score >= 75:
        return 'near_synonym_high'
    if score >= 55:
        return 'related_mid'
    if score >= 35:
        return 'related_low'
    if score >= 20:
        return 'hard_negative_mid'
    return 'hard_negative_low'

def range_for_score(score: int) -> str:
    left = max(0, score - 5)
    right = min(100, score + 5)
    return f'{left}-{right}'

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
        rows.append({
            'id': '',
            'answer': a,
            'user_input': b,
            'answer_category': category,
            'input_category_guess': '',
            'relation_tag': relation_tag if relation_tag else relation_for_score(score),
            'expected_range': range_for_score(score),
            'score_0_100': str(score),
            'reason': reason,
            'reviewer': reviewer,
        })

    # 1. Manual overrides (highest priority)
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
            reason = str(item.get('reason', 'manual_override'))
            push(answer, user_input, int(round(float(score))), '', '', reason, 'manual_gold')

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
                tag = row.get('relation_tag', '')
                reason = row.get('reason', 'gold_pool')
                reviewer = row.get('reviewer', 'gold_v26')
                cat = row.get('answer_category', '')
                push(a, b, score, cat, tag, reason, reviewer)

    # 3. Extra CSVs
    for csv_path, reviewer in EXTRA_CSVS:
        p = Path(csv_path)
        if not p.exists():
            print(f'  SKIP {csv_path}')
            continue
        with p.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
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
                tag = row.get('relation_tag', '')
                reason = row.get('reason', csv_path)
                push(a, b, score, '', tag, reason, reviewer)
                count += 1
        print(f'  {csv_path}: +{count}')

    # 4. Puzzle self-anchors + hint pairs
    puzzles = json.loads(PUZZLES_JSON.read_text(encoding='utf-8'))
    hint_targets = [30, 40, 50, 60, 70, 80, 90]
    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = [str(h).strip() for h in (item.get('hints') or [])]
        if not answer:
            continue
        push(answer, answer, 98, category, 'same_answer_exact', 'self anchor', 'auto_v28')

        if len(hints) == 7:
            for idx, hint in enumerate(hints):
                if not hint:
                    continue
                target = hint_targets[idx]
                push(answer, hint, target, category, '', f'puzzle_hint_lvl_{idx+1}', 'auto_v28')
                if target >= 70:
                    push(hint, answer, min(95, target + 5), category, '', f'reverse_hint_lvl_{idx+1}', 'auto_v28')

    # 5. Cross-category negatives (sampled)
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

    rng = random.Random(20260515)
    neg_per_answer = 2
    for ans in unique_answers:
        cat = answer_cat.get(ans, '')
        neg_pool = [x for x in unique_answers if x != ans and answer_cat.get(x, '') != cat]
        rng.shuffle(neg_pool)
        for neg in neg_pool[:neg_per_answer]:
            push(ans, neg, rng.choice([4, 6, 8, 10]), cat, 'cross_category_negative', 'cross_category_negative', 'auto_v28')

    # Shuffle and assign IDs
    rng.shuffle(rows)
    for i, row in enumerate(rows, 1):
        row['id'] = str(i)

    # Stats
    tag_counts = Counter(r['relation_tag'] for r in rows)
    score_buckets = Counter((int(r['score_0_100']) // 10) * 10 for r in rows)
    reviewer_counts = Counter(r['reviewer'] for r in rows)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f'\n=== train_v28_phoenix.csv ===')
    print(f'Total: {len(rows)} rows')
    print(f'Unique pairs: {len(seen)}')

    print(f'\nBy relation_tag:')
    for tag, cnt in tag_counts.most_common():
        print(f'  {tag}: {cnt}')

    print(f'\nBy score bucket:')
    for b in sorted(score_buckets):
        print(f'  {b:3d}-{b+9:3d}: {score_buckets[b]:4d} {"█" * min(50, score_buckets[b] // 20)}')

    print(f'\nBy reviewer:')
    for rev, cnt in reviewer_counts.most_common():
        print(f'  {rev}: {cnt}')

    print(f'\nWritten: {OUTPUT}')

if __name__ == '__main__':
    main()
