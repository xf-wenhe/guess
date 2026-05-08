import csv
from pathlib import Path

BASE_CSV = Path('data/semantic_scoring_user_input_template.csv')
ANCHOR_CSV = Path('data/semantic_anchor_template_v20.csv')
OUTPUT_CSV = Path('data/semantic_scoring_v21_combined.csv')

FIELDNAMES = [
    'id',
    'answer',
    'user_input',
    'answer_category',
    'input_category_guess',
    'relation_tag',
    'expected_range',
    'score_0_100',
    'reason',
    'reviewer',
]

HIGH_CONF_TAGS = {
    'exact_match',
    'alias_synonym_high',
    'hard_negative_low',
}


def parse_score(row):
    raw = (row.get('score_0_100') or '').strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if 0 <= value <= 100:
        return value
    return None


def load_valid_rows(path: Path):
    rows = []
    for r in csv.DictReader(path.open('r', encoding='utf-8')):
        answer = (r.get('answer') or '').strip()
        user_input = (r.get('user_input') or '').strip()
        score = parse_score(r)
        if not answer or not user_input or score is None:
            continue
        row = {k: (r.get(k) or '').strip() for k in FIELDNAMES}
        row['answer'] = answer
        row['user_input'] = user_input
        row['score_0_100'] = str((r.get('score_0_100') or '').strip())
        rows.append(row)
    return rows


def keep_anchor_row(row):
    tag = (row.get('relation_tag') or '').strip()
    score = parse_score(row)
    if score is None:
        return False

    if tag in HIGH_CONF_TAGS:
        return True

    if tag == 'near_synonym_high' and score >= 88:
        return True

    if score <= 12:
        return True

    return False


def main():
    if not BASE_CSV.exists():
        raise SystemExit(f'missing file: {BASE_CSV}')
    if not ANCHOR_CSV.exists():
        raise SystemExit(f'missing file: {ANCHOR_CSV}')

    base_rows = load_valid_rows(BASE_CSV)
    anchor_rows_all = load_valid_rows(ANCHOR_CSV)
    anchor_rows = [r for r in anchor_rows_all if keep_anchor_row(r)]

    merged = []
    seen = set()

    for r in base_rows + anchor_rows:
        key = (r['answer'], r['user_input'])
        if key in seen:
            continue
        seen.add(key)
        merged.append(r)

    for idx, row in enumerate(merged, start=1):
        row['id'] = str(idx)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged)

    tag_counts = {}
    for r in anchor_rows:
        t = r['relation_tag'] or 'unknown'
        tag_counts[t] = tag_counts.get(t, 0) + 1

    print(f'base_valid={len(base_rows)} anchor_valid={len(anchor_rows_all)} anchor_kept={len(anchor_rows)} merged={len(merged)}')
    for k in sorted(tag_counts):
        print(f'anchor_{k}={tag_counts[k]}')
    print(f'written={OUTPUT_CSV}')


if __name__ == '__main__':
    main()
