import json
import random
import statistics as st
from sentence_transformers import SentenceTransformer

random.seed(42)
model = SentenceTransformer('models/bge-m3-finetuned-v11', device='cpu')

def cosine_batch(texts_a, texts_b):
    ea = model.encode(texts_a, normalize_embeddings=True, batch_size=32)
    eb = model.encode(texts_b, normalize_embeddings=True, batch_size=32)
    return [(va * vb).sum() for va, vb in zip(ea, eb)]

pairs = [('啊啊', '夸父'), ('你是猪', '夸父'), ('夸父', '逐日'), ('夸父', '神话')]
print('key pairs:')
scores = cosine_batch([a for a, _ in pairs], [b for _, b in pairs])
for (a, b), s in zip(pairs, scores):
    print(a, b, round(s * 100, 2))

puzzles = json.loads(open('assets/puzzles.json', 'r', encoding='utf-8').read())
answers = [p['answer'] for p in puzzles]
answer_to_category = {p['answer']: p.get('category', '') for p in puzzles}
by_cat = {}
for p in puzzles:
    by_cat.setdefault(p.get('category', ''), []).append(p['answer'])

# unrelated (diff category)
unrel_pairs = []
for _ in range(200):
    a = random.choice(answers)
    cat = answer_to_category[a]
    other = random.choice([x for x in answers if answer_to_category[x] != cat])
    unrel_pairs.append((a, other))
unrel = [s * 100 for s in cosine_batch([a for a, _ in unrel_pairs], [b for _, b in unrel_pairs])]

# same category (slight)
rel_pairs = []
for _ in range(200):
    a = random.choice(answers)
    cat = answer_to_category[a]
    pool = [x for x in by_cat.get(cat, []) if x != a]
    if not pool:
        continue
    other = random.choice(pool)
    rel_pairs.append((a, other))
rel = [s * 100 for s in cosine_batch([a for a, _ in rel_pairs], [b for _, b in rel_pairs])]

# answer-hint
hint_pairs = []
for p in random.sample(puzzles, 100):
    a = p['answer']
    for h in p.get('hints', []):
        hint_pairs.append((a, h))
hint_scores = [s * 100 for s in cosine_batch([a for a, _ in hint_pairs], [b for _, b in hint_pairs])]


def stats(arr):
    q1, q2, q3 = st.quantiles(arr, n=4)
    return (round(st.mean(arr), 2), round(q1, 2), round(q2, 2), round(q3, 2))

print('unrelated mean/q1/median/q3:', stats(unrel))
print('same-category mean/q1/median/q3:', stats(rel))
print('answer-hint mean/q1/median/q3:', stats(hint_scores))
