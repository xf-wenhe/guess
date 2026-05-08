import json
import random
from collections import defaultdict
from pathlib import Path

from sentence_transformers import SentenceTransformer

random.seed(20260225)

puzzles = json.loads(Path('assets/puzzles.json').read_text(encoding='utf-8'))
by_category = defaultdict(list)
for item in puzzles:
    answer = item.get('answer')
    category = item.get('category', '')
    if answer:
        by_category[category].append(answer)

eligible_categories = [c for c, words in by_category.items() if len(words) >= 2]
if not eligible_categories:
    raise SystemExit('No categories with at least 2 answers.')

pairs = []
seen = set()
attempts = 0
while len(pairs) < 30 and attempts < 5000:
    attempts += 1
    category = random.choice(eligible_categories)
    a, b = random.sample(by_category[category], 2)
    key = tuple(sorted((a, b)))
    if key in seen:
        continue
    seen.add(key)
    pairs.append((a, b, category))

if len(pairs) < 30:
    raise SystemExit(f'Only sampled {len(pairs)} same-category pairs.')

model = SentenceTransformer('models/bge-m3-finetuned-v14', device='cpu')
vec_a = model.encode([a for a, _, _ in pairs], normalize_embeddings=True, batch_size=32)
vec_b = model.encode([b for _, b, _ in pairs], normalize_embeddings=True, batch_size=32)

scores = []
print('model=v13 same_category_pairs=30')
print('word_a\tword_b\tcategory\tsimilarity_percent')
for (a, b, category), va, vb in zip(pairs, vec_a, vec_b):
    score = float((va * vb).sum() * 100)
    scores.append(score)
    print(f'{a}\t{b}\t{category}\t{score:.2f}')

in_target = [s for s in scores if 60 <= s <= 80]
below = [s for s in scores if s < 60]
above = [s for s in scores if s > 80]

scores_sorted = sorted(scores)
median = scores_sorted[len(scores_sorted) // 2]

print('\nsummary:')
print(f'total=30 mean={sum(scores)/len(scores):.2f} median={median:.2f} min={scores_sorted[0]:.2f} max={scores_sorted[-1]:.2f}')
print(f'in_60_80={len(in_target)} ({len(in_target)/30*100:.1f}%)')
print(f'below_60={len(below)} ({len(below)/30*100:.1f}%)')
print(f'above_80={len(above)} ({len(above)/30*100:.1f}%)')
