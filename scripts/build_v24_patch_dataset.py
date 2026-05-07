import csv
import json
from pathlib import Path

BASE_CSV = Path('data/semantic_scoring_v23_combined.csv')
OVERRIDES_JSON = Path('data/manual_similarity_overrides.json')
OUTPUT_CSV = Path('data/semantic_scoring_v24_patch.csv')

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer'
]

PATCH_ROWS = [
    ('诸葛亮', '孔明', 85, 'alias_synonym_high', '80-90', '人工精调：历史别名'),
    ('孔明', '诸葛亮', 85, 'alias_synonym_high', '80-90', '人工精调：历史别名（反向）'),
    ('诸葛亮', '卧龙', 85, 'alias_synonym_high', '80-90', '人工精调：历史别名'),
    ('卧龙', '诸葛亮', 85, 'alias_synonym_high', '80-90', '人工精调：历史别名（反向）'),
    ('关羽', '武圣', 82, 'alias_synonym_high', '80-90', '人工精调：历史称号'),
    ('武圣', '关羽', 82, 'alias_synonym_high', '80-90', '人工精调：历史称号（反向）'),
    ('关羽', '刮骨疗毒', 60, 'related_mid', '55-65', '人工精调：历史事件关联'),
    ('刮骨疗毒', '关羽', 60, 'related_mid', '55-65', '人工精调：历史事件关联（反向）'),
    ('刮骨疗毒', '华佗', 62, 'related_mid', '58-68', '人工精调：历史事件与人物'),
    ('华佗', '刮骨疗毒', 62, 'related_mid', '58-68', '人工精调：历史事件与人物（反向）'),
    ('你个der', '猫咪', 10, 'hard_negative_low', '0-12', '人工精调：完全无关'),
    ('猫咪', '你个der', 10, 'hard_negative_low', '0-12', '人工精调：完全无关（反向）'),
    ('aaa', '诸葛亮', 10, 'hard_negative_low', '0-12', '人工精调：随机串无关'),
    ('诸葛亮', 'aaa', 10, 'hard_negative_low', '0-12', '人工精调：随机串无关（反向）'),
]


def score_to_str(score: float) -> str:
    value = float(score)
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f'{value:.2f}'


def load_rows(path: Path):
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
            clean['score_0_100'] = score_to_str(score)
            rows.append(clean)
    return rows


def load_override_rows(path: Path):
    if not path.exists():
        return []
    decoded = json.loads(path.read_text(encoding='utf-8'))
    rows = []
    if not isinstance(decoded, list):
        return rows
    for item in decoded:
        if not isinstance(item, dict):
            continue
        answer = str(item.get('answer', '')).strip()
        user_input = str(item.get('user_input', '')).strip()
        score = item.get('score')
        reason = str(item.get('reason', '')).strip()
        if not answer or not user_input or not isinstance(score, (int, float)):
            continue

        relation_tag = 'related_mid'
        expected_range = '40-80'
        if score <= 15:
            relation_tag = 'hard_negative_low'
            expected_range = '0-15'
        elif score >= 80:
            relation_tag = 'alias_synonym_high'
            expected_range = '80-95'

        rows.append({
            'id': '',
            'answer': answer,
            'user_input': user_input,
            'answer_category': '',
            'input_category_guess': '',
            'relation_tag': relation_tag,
            'expected_range': expected_range,
            'score_0_100': score_to_str(score),
            'reason': reason or 'manual override',
            'reviewer': 'manual_override',
        })
    return rows


def main():
    if not BASE_CSV.exists():
        raise SystemExit(f'missing file: {BASE_CSV}')

    base_rows = load_rows(BASE_CSV)
    override_rows = load_override_rows(OVERRIDES_JSON)

    merged = []
    seen = set()

    def upsert(row):
        key = (row['answer'], row['user_input'])
        if key in seen:
            return
        seen.add(key)
        merged.append(row)

    for row in base_rows:
        upsert(dict(row))

    for row in override_rows:
        upsert(dict(row))

    for answer, user_input, score, tag, expected, reason in PATCH_ROWS:
        row = {
            'id': '',
            'answer': answer,
            'user_input': user_input,
            'answer_category': '',
            'input_category_guess': '',
            'relation_tag': tag,
            'expected_range': expected,
            'score_0_100': score_to_str(score),
            'reason': reason,
            'reviewer': 'manual_patch',
        }
        key = (answer, user_input)
        if key in seen:
            for i, old in enumerate(merged):
                if old['answer'] == answer and old['user_input'] == user_input:
                    merged[i] = row
                    break
        else:
            seen.add(key)
            merged.append(row)

    for idx, row in enumerate(merged, start=1):
        row['id'] = str(idx)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged)

    print(f'base={len(base_rows)} overrides={len(override_rows)} merged={len(merged)}')
    print(f'written={OUTPUT_CSV}')


if __name__ == '__main__':
    main()
