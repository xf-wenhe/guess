import csv
import json
import random
import re
from pathlib import Path
from typing import Optional

RANDOM_SEED = 20260228
TARGET_ROWS = 300

INPUT_PUZZLES = Path('assets/puzzles.json')
OUTPUT_CSV = Path('data/semantic_anchor_template_v20.csv')

# 放宽到 1-8，确保“猫”这类单字词能进入锚点集
CHINESE_RE = re.compile(r'^[\u4e00-\u9fff]{1,8}$')

# 高价值人工锚点（优先覆盖别称/近义）
HIGH_ANCHORS = [
    ('猫咪', '猫', 'alias_synonym_high', '90-98', '昵称与本词'),
    ('狗狗', '狗', 'alias_synonym_high', '90-98', '昵称与本词'),
    ('小狗', '狗', 'alias_synonym_high', '88-96', '口语近义'),
    ('小猫', '猫', 'alias_synonym_high', '88-96', '口语近义'),
    ('诸葛亮', '孔明', 'alias_synonym_high', '90-98', '同一人物别名'),
    ('李白', '青莲居士', 'alias_synonym_high', '85-95', '人物号'),
    ('杜甫', '少陵野老', 'alias_synonym_high', '85-95', '人物号'),
    ('孙悟空', '齐天大圣', 'alias_synonym_high', '90-98', '同一角色称谓'),
    ('哪吒', '三太子', 'alias_synonym_high', '85-95', '角色称谓'),
    ('饺子', '水饺', 'near_synonym_high', '85-95', '同义常用词'),
    ('火锅', '涮锅', 'near_synonym_high', '80-92', '近义称呼'),
    ('寿司', '饭团', 'related_mid', '45-70', '相关但非严格同义'),
    ('披萨', '比萨', 'near_synonym_high', '88-96', '异写同词'),
    ('手机', '电话', 'related_mid', '55-78', '强相关'),
    ('电脑', '计算机', 'near_synonym_high', '80-92', '常见近义'),
    ('天气', '气候', 'related_mid', '50-72', '相关概念'),
    ('医生', '大夫', 'near_synonym_high', '82-94', '职业近义'),
    ('老师', '教师', 'near_synonym_high', '82-94', '职业近义'),
    ('学生', '学员', 'related_mid', '60-80', '语义接近'),
    ('高兴', '开心', 'near_synonym_high', '86-96', '情绪近义'),
    ('难过', '伤心', 'near_synonym_high', '86-96', '情绪近义'),
    ('愤怒', '生气', 'near_synonym_high', '84-94', '情绪近义'),
    ('孤独', '孤寂', 'near_synonym_high', '84-94', '情绪近义'),
    ('跑步', '奔跑', 'near_synonym_high', '82-92', '动作近义'),
    ('行走', '走路', 'near_synonym_high', '82-92', '动作近义'),
    ('看见', '看到', 'near_synonym_high', '84-94', '动词近义'),
    ('思考', '思索', 'near_synonym_high', '82-92', '动词近义'),
    ('工作', '上班', 'related_mid', '58-80', '场景相关'),
    ('学习', '读书', 'related_mid', '58-80', '场景相关'),
    ('医院', '诊所', 'related_mid', '55-78', '同域相关'),
    ('学校', '校园', 'related_mid', '60-82', '同域相关'),
    ('地铁', '公交', 'related_mid', '45-68', '交通相关'),
    ('汽车', '卡车', 'related_mid', '45-70', '同类相关'),
    ('苹果', '水果', 'related_mid', '48-72', '上下位相关'),
    ('猫咪', '刘备', 'hard_negative_low', '0-20', '无关对照'),
    ('火锅', '诸葛亮', 'hard_negative_low', '0-20', '跨域无关'),
    ('医生', '海贼王', 'hard_negative_low', '0-20', '跨域无关'),
    ('学校', '寿司', 'hard_negative_low', '0-20', '跨域无关'),
    ('李白', '披萨', 'hard_negative_low', '0-20', '跨域无关'),
]


def is_valid_word(text: str) -> bool:
    return bool(text) and CHINESE_RE.fullmatch(text) is not None


def expected_range(tag: str) -> str:
    mapping = {
        'exact_match': '98-100',
        'alias_synonym_high': '90-98',
        'near_synonym_high': '80-92',
        'related_mid': '45-75',
        'hard_negative_low': '0-20',
    }
    return mapping.get(tag, '0-100')


def load_puzzle_words(path: Path):
    data = json.loads(path.read_text(encoding='utf-8'))

    answers = []
    answer_to_category = {}
    hints_by_answer = {}
    by_category = {}

    for item in data:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = [str(h).strip() for h in item.get('hints', []) if isinstance(h, str)]

        if not is_valid_word(answer):
            continue

        answers.append(answer)
        answer_to_category[answer] = category
        valid_hints = [h for h in hints if is_valid_word(h)]
        hints_by_answer[answer] = valid_hints
        by_category.setdefault(category, []).append(answer)

    return answers, answer_to_category, hints_by_answer, by_category


def main():
    random.seed(RANDOM_SEED)

    answers, answer_to_category, hints_by_answer, by_category = load_puzzle_words(INPUT_PUZZLES)
    if not answers:
        raise SystemExit('no valid answers found in puzzles')

    rows = []
    seen = set()

    def push_row(answer: str, user_input: str, relation_tag: str, expected: Optional[str] = None, reason: str = ''):
        if not is_valid_word(answer) or not is_valid_word(user_input):
            return False
        key = (answer, user_input)
        if key in seen:
            return False
        seen.add(key)
        rows.append({
            'id': len(rows) + 1,
            'answer': answer,
            'user_input': user_input,
            'answer_category': answer_to_category.get(answer, ''),
            'input_category_guess': '',
            'relation_tag': relation_tag,
            'expected_range': expected or expected_range(relation_tag),
            'score_0_100': '',
            'reason': reason,
            'reviewer': '',
        })
        return True

    # A. 先注入人工高价值锚点（如果 answer 不在题库，也允许保留）
    for a, b, tag, exp, reason in HIGH_ANCHORS:
        if a not in answer_to_category:
            answer_to_category[a] = '锚点词'
        push_row(a, b, tag, exp, reason)

    # B. 同词锚点（确保上边界）
    same_targets = min(60, len(answers))
    for a in random.sample(answers, k=same_targets):
        push_row(a, a, 'exact_match', '98-100', '完全一致')

    # C. 题面提示高相关
    while len([r for r in rows if r['relation_tag'] == 'near_synonym_high']) < 90 and len(rows) < TARGET_ROWS:
        a = random.choice(answers)
        hints = hints_by_answer.get(a, [])
        if not hints:
            continue
        h = random.choice(hints)
        push_row(a, h, 'near_synonym_high', '80-92', '答案提示词（需人工复核）')

    # D. 同类中相关（中分）
    while len([r for r in rows if r['relation_tag'] == 'related_mid']) < 80 and len(rows) < TARGET_ROWS:
        a = random.choice(answers)
        cat = answer_to_category.get(a, '')
        pool = [x for x in by_category.get(cat, []) if x != a]
        if not pool:
            continue
        b = random.choice(pool)
        push_row(a, b, 'related_mid', '45-75', '同类词（需人工复核）')

    # E. 跨类硬负样本（低分）
    while len([r for r in rows if r['relation_tag'] == 'hard_negative_low']) < 70 and len(rows) < TARGET_ROWS:
        a = random.choice(answers)
        cat = answer_to_category.get(a, '')
        pool = [x for x in answers if answer_to_category.get(x, '') != cat]
        if not pool:
            continue
        b = random.choice(pool)
        push_row(a, b, 'hard_negative_low', '0-20', '跨类无关（需人工复核）')

    # F. 不足则补充 related/hard negative
    while len(rows) < TARGET_ROWS:
        a = random.choice(answers)
        if random.random() < 0.5:
            cat = answer_to_category.get(a, '')
            pool = [x for x in by_category.get(cat, []) if x != a]
            if not pool:
                continue
            b = random.choice(pool)
            push_row(a, b, 'related_mid', '45-75', '补齐样本')
        else:
            cat = answer_to_category.get(a, '')
            pool = [x for x in answers if answer_to_category.get(x, '') != cat]
            if not pool:
                continue
            b = random.choice(pool)
            push_row(a, b, 'hard_negative_low', '0-20', '补齐样本')

    rows = rows[:TARGET_ROWS]
    for idx, row in enumerate(rows, start=1):
        row['id'] = idx

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts = {}
    for r in rows:
        tag = r['relation_tag']
        counts[tag] = counts.get(tag, 0) + 1

    print(f'written={OUTPUT_CSV} rows={len(rows)}')
    for k in sorted(counts):
        print(f'{k}={counts[k]}')


if __name__ == '__main__':
    main()
