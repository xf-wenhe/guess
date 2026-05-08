import csv
from pathlib import Path

BASE_CSV = Path('data/semantic_scoring_user_input_template.csv')
ANCHOR_CSV = Path('data/semantic_anchor_template_v20.csv')
OUTPUT_CSV = Path('data/semantic_scoring_v23_combined.csv')

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer'
]


def parse_score(r):
    s = (r.get('score_0_100') or '').strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if 0 <= v <= 100:
        return v
    return None


def load_rows(path: Path):
    rows = []
    for r in csv.DictReader(path.open('r', encoding='utf-8')):
        a = (r.get('answer') or '').strip()
        b = (r.get('user_input') or '').strip()
        score = parse_score(r)
        if not a or not b or score is None:
            continue
        row = {k: (r.get(k) or '').strip() for k in FIELDNAMES}
        row['answer'] = a
        row['user_input'] = b
        row['score_0_100'] = str(int(score) if abs(score - int(score)) < 1e-9 else score)
        rows.append(row)
    return rows


def keep_anchor_row(row):
    tag = (row.get('relation_tag') or '').strip()
    score = parse_score(row) or 0.0

    if tag == 'exact_match':
        return True
    if tag == 'alias_synonym_high':
        return True
    if tag == 'hard_negative_low':
        return True

    if tag == 'near_synonym_high':
        return score >= 70

    if tag == 'related_mid':
        return 40 <= score <= 80

    return False


def row_repeat(row):
    tag = (row.get('relation_tag') or '').strip()
    score = parse_score(row) or 0.0
    if tag in {'alias_synonym_high', 'hard_negative_low'}:
        return 3
    if tag == 'near_synonym_high' and score >= 85:
        return 2
    return 1


def main():
    base_rows = load_rows(BASE_CSV)
    anchor_rows_all = load_rows(ANCHOR_CSV)
    anchor_rows = [r for r in anchor_rows_all if keep_anchor_row(r)]

    merged = []
    seen = set()

    for r in base_rows:
        key = (r['answer'], r['user_input'])
        if key in seen:
            continue
        seen.add(key)
        merged.append(r)

    for r in anchor_rows:
        key = (r['answer'], r['user_input'])
        repeat = row_repeat(r)
        if key in seen:
            for _ in range(max(0, repeat - 1)):
                merged.append(dict(r))
        else:
            seen.add(key)
            for _ in range(repeat):
                merged.append(dict(r))

    for idx, r in enumerate(merged, start=1):
        r['id'] = str(idx)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged)

    print(f'base_valid={len(base_rows)} anchor_valid={len(anchor_rows_all)} anchor_kept={len(anchor_rows)} merged={len(merged)}')
    print(f'written={OUTPUT_CSV}')


if __name__ == '__main__':
    main()
