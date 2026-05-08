import json
import random
from pathlib import Path

from sentence_transformers import SentenceTransformer

random.seed(20260225)

puzzles = json.loads(Path('assets/puzzles.json').read_text(encoding='utf-8'))
answers = [item['answer'] for item in puzzles if item.get('answer')]
answer_to_category = {item['answer']: item.get('category', '') for item in puzzles if item.get('answer')}

model = SentenceTransformer('models/bge-m3-finetuned-v13', device='cpu')

pairs = []
seen = set()
while len(pairs) < 30:
    a, b = random.sample(answers, 2)
    key = tuple(sorted((a, b)))
    if key in seen:
        continue
    seen.add(key)
    pairs.append((a, b))

vec_a = model.encode([a for a, _ in pairs], normalize_embeddings=True, batch_size=32)
vec_b = model.encode([b for _, b in pairs], normalize_embeddings=True, batch_size=32)

print('model=v13 random_pairs=30')
print('word_a\tword_b\tcat_a\tcat_b\tsimilarity_percent')
scores = []
for (a, b), va, vb in zip(pairs, vec_a, vec_b):
    score = float((va * vb).sum() * 100)
    scores.append(score)
    print(f'{a}\t{b}\t{answer_to_category.get(a, "")}\t{answer_to_category.get(b, "")}\t{score:.2f}')

same_cat = [s for (a, b), s in zip(pairs, scores) if answer_to_category.get(a, '') == answer_to_category.get(b, '')]
diff_cat = [s for (a, b), s in zip(pairs, scores) if answer_to_category.get(a, '') != answer_to_category.get(b, '')]

def summary(arr):
    if not arr:
        return 'n=0'
    arr_sorted = sorted(arr)
    mid = arr_sorted[len(arr_sorted)//2]
    return f'n={len(arr_sorted)} mean={sum(arr_sorted)/len(arr_sorted):.2f} median={mid:.2f} min={arr_sorted[0]:.2f} max={arr_sorted[-1]:.2f}'

print('\nsummary_all:', summary(scores))
print('summary_same_category:', summary(same_cat))
print('summary_diff_category:', summary(diff_cat))
