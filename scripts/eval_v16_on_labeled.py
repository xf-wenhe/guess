import csv
import random
from sentence_transformers import SentenceTransformer

random.seed(20260227)
rows = list(csv.DictReader(open('data/semantic_scoring_user_input_template.csv', encoding='utf-8')))
rows = [r for r in rows if (r.get('score_0_100') or '').strip()]
sample = random.sample(rows, 30)

model = SentenceTransformer('models/bge-m3-finetuned-v16', device='cpu')
answers = [r['answer'] for r in sample]
inputs = [r['user_input'] for r in sample]
va = model.encode(answers, normalize_embeddings=True, batch_size=32)
vb = model.encode(inputs, normalize_embeddings=True, batch_size=32)

mae = 0.0
print('answer\tuser_input\tlabel\tpred')
for r, x, y in zip(sample, va, vb):
    pred = float((x * y).sum() * 100)
    label = float(r['score_0_100'])
    mae += abs(pred - label)
    print(f"{r['answer']}\t{r['user_input']}\t{label:.1f}\t{pred:.2f}")

print('MAE=', round(mae / len(sample), 2))
