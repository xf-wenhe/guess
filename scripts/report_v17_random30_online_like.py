import json
import random
from pathlib import Path

from sentence_transformers import SentenceTransformer

random.seed(20260227)

puzzles = json.loads(Path('assets/puzzles.json').read_text(encoding='utf-8'))
answers = [item['answer'] for item in puzzles if item.get('answer')]
answer_to_category = {item['answer']: item.get('category', '') for item in puzzles if item.get('answer')}

# 模拟用户输入池：answer + 常见口语 + hints
common_inputs = [
    '不知道', '不会', '乱猜', '啊啊', '哈哈', '你是猪', '好难', '再来', '无语', '提示少',
]
hint_pool = []
for item in puzzles:
    for h in item.get('hints', []):
        if isinstance(h, str) and h.strip():
            hint_pool.append(h.strip())

user_pool = list(set(common_inputs + hint_pool + answers))

pairs = []
for _ in range(30):
    answer = random.choice(answers)
    user_input = random.choice(user_pool)
    pairs.append((answer, user_input))

model = SentenceTransformer('models/bge-m3-finetuned-v17', device='cpu')
va = model.encode([a for a, _ in pairs], normalize_embeddings=True, batch_size=32)
vb = model.encode([b for _, b in pairs], normalize_embeddings=True, batch_size=32)

scores = [float((x * y).sum() * 100) for x, y in zip(va, vb)]

print('model=v17 report=random30 online-like')
print('answer\tuser_input\tanswer_cat\tscore')
for (a, b), s in zip(pairs, scores):
    print(f'{a}\t{b}\t{answer_to_category.get(a, "")}\t{s:.2f}')

bucket_0_20 = sum(1 for s in scores if s < 20)
bucket_20_40 = sum(1 for s in scores if 20 <= s < 40)
bucket_40_60 = sum(1 for s in scores if 40 <= s < 60)
bucket_60_80 = sum(1 for s in scores if 60 <= s < 80)
bucket_80_100 = sum(1 for s in scores if s >= 80)

scores_sorted = sorted(scores)
median = scores_sorted[len(scores_sorted) // 2]

print('\nsummary:')
print(f'mean={sum(scores)/len(scores):.2f} median={median:.2f} min={scores_sorted[0]:.2f} max={scores_sorted[-1]:.2f}')
print(f'0-20: {bucket_0_20}')
print(f'20-40: {bucket_20_40}')
print(f'40-60: {bucket_40_60}')
print(f'60-80: {bucket_60_80}')
print(f'80-100: {bucket_80_100}')
