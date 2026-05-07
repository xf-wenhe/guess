import csv
import json
import os
from pathlib import Path

BASE_CSV = Path(os.getenv('SEM_BASE_CSV', 'data/semantic_scoring_v24_patch.csv'))
PUZZLES_JSON = Path(os.getenv('SEM_PUZZLES_JSON', 'assets/puzzles.json'))
OUTPUT_CSV = Path(os.getenv('SEM_OUTPUT_CSV', 'data/semantic_scoring_v25_hintdistill.csv'))

TARGETS = [30, 40, 50, 60, 70, 80, 90]

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer'
]


def to_score_str(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f'{value:.2f}'


def range_for_score(score: int) -> str:
    left = max(0, score - 5)
    right = min(100, score + 5)
    return f'{left}-{right}'


def load_base_rows(path: Path):
    rows = []
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
            clean = {k: (row.get(k) or '').strip() for k in FIELDNAMES}
            clean['answer'] = answer
            clean['user_input'] = user_input
            clean['score_0_100'] = to_score_str(score)
            rows.append(clean)
    return rows


def load_hint_rows(path: Path):
    decoded = json.loads(path.read_text(encoding='utf-8'))
    rows = []
    for item in decoded:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = item.get('hints') or []
        if not answer or not isinstance(hints, list):
            continue
        for idx, hint in enumerate(hints[:7]):
            hint_text = str(hint).strip()
            if not hint_text:
                continue
            score = TARGETS[idx]
            if score <= 35:
                tag = 'hint_distill_low'
            elif score <= 55:
                tag = 'hint_distill_mid'
            elif score <= 75:
                tag = 'hint_distill_high'
            else:
                tag = 'hint_distill_top'
            rows.append({
                'id': '',
                'answer': answer,
                'user_input': hint_text,
                'answer_category': category,
                'input_category_guess': category,
                'relation_tag': tag,
                'expected_range': range_for_score(score),
                'score_0_100': to_score_str(float(score)),
                'reason': f'hint distill target {score}',
                'reviewer': 'hint_distill_v25',
            })
    return rows


def main():
    if not BASE_CSV.exists():
        raise SystemExit(f'missing file: {BASE_CSV}')
    if not PUZZLES_JSON.exists():
        raise SystemExit(f'missing file: {PUZZLES_JSON}')

    base_rows = load_base_rows(BASE_CSV)
    hint_rows = load_hint_rows(PUZZLES_JSON)

    merged = []
    index = {}

    for row in base_rows:
        key = (row['answer'], row['user_input'])
        index[key] = len(merged)
        merged.append(dict(row))

    replaced = 0
    added = 0
    for row in hint_rows:
        key = (row['answer'], row['user_input'])
        if key in index:
            merged[index[key]] = dict(row)
            replaced += 1
        else:
            index[key] = len(merged)
            merged.append(dict(row))
            added += 1

    for i, row in enumerate(merged, start=1):
        row['id'] = str(i)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged)

    print(f'base={len(base_rows)} hint_rows={len(hint_rows)} added={added} replaced={replaced} merged={len(merged)}')
    print(f'written={OUTPUT_CSV}')


if __name__ == '__main__':
    main()