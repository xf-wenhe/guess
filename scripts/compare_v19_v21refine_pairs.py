import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

ANGLES = ['从含义角度看：', '从用途角度看：', '从场景角度看：', '从特征角度看：', '从关联角度看：']
PAIRS = [('猫咪', '猫'), ('猫咪', '刘备')]

MODELS = [
    ('v19', 'models/bge-m3-finetuned-v19', 'data/semantic_calibration_v19.json'),
    ('v21_refine', 'models/bge-m3-finetuned-v21-refine', 'data/semantic_calibration_v21_refine.json'),
]


def cosine_similarity(a, b):
    dot = float((a * b).sum())
    na = float((a * a).sum()) ** 0.5
    nb = float((b * b).sum()) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def semantic_multi_angle(model, guess: str, answer: str):
    scores = []
    for angle in ANGLES:
        vg = model.encode([f'{angle}{guess}'], normalize_embeddings=True)[0]
        va = model.encode([f'{angle}{answer}'], normalize_embeddings=True)[0]
        scores.append(cosine_similarity(vg, va))
    scores.sort()
    trimmed = scores[1:-1] if len(scores) >= 3 else scores
    return sum(trimmed) / len(trimmed)


def calculate_similarity(guess: str, target: str):
    guess_chars = [ord(c) for c in guess]
    target_chars = [ord(c) for c in target]

    freq_guess = {}
    freq_target = {}

    for c in guess_chars:
        freq_guess[c] = freq_guess.get(c, 0) + 1
    for c in target_chars:
        freq_target[c] = freq_target.get(c, 0) + 1

    common = 0
    for k, v in freq_guess.items():
        other = freq_target.get(k)
        if other is not None:
            common += min(v, other)

    position_match = 0
    min_len = min(len(guess_chars), len(target_chars))
    for i in range(min_len):
        if guess_chars[i] == target_chars[i]:
            position_match += 1

    denom = max(len(target_chars), len(guess_chars)) or 1
    score = (common * 0.6 + position_match * 0.4) / denom
    return round(max(0, min(100, score * 100)))


def normalize_similarity(similarity: int):
    normalized = max(10, min(100, similarity))
    if normalized >= 95:
        return 95
    if 20 <= normalized <= 40:
        return 10 + ((normalized - 20) * 10 // 20)
    return normalized


def apply_calibration(pred, x, y):
    if pred <= x[0]:
        return y[0]
    if pred >= x[-1]:
        return y[-1]
    for i in range(len(x) - 1):
        left = x[i]
        right = x[i + 1]
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return y[i]
            t = (pred - left) / span
            return y[i] + (y[i + 1] - y[i]) * t
    return pred


def final_score(raw_sem_percent, cal_sem_percent, lexical):
    semantic_weight = 0.8
    lexical_weight = 0.2
    if lexical >= 40 and cal_sem_percent >= 20:
        semantic_weight = 0.6
        lexical_weight = 0.4

    combined = round((cal_sem_percent * semantic_weight) + (lexical * lexical_weight))

    if lexical == 0:
        if cal_sem_percent < 20:
            combined = min(combined, 10)
        elif cal_sem_percent < 25:
            combined = min(combined, 12)

    return normalize_similarity(combined)


def main():
    for name, model_path, calib_path in MODELS:
        model = SentenceTransformer(model_path, device='cpu')
        calib = json.loads(Path(calib_path).read_text(encoding='utf-8'))
        x = calib['x_pred']
        y = calib['y_calibrated']

        print(f'[{name}] model={model_path} calib={calib_path}')
        for guess, answer in PAIRS:
            sem = semantic_multi_angle(model, guess, answer)
            raw_sem_percent = sem * 100.0
            cal_sem = apply_calibration(raw_sem_percent, x, y)
            lexical = calculate_similarity(guess, answer)
            final = final_score(raw_sem_percent, cal_sem, lexical)
            print(
                f'  {guess}-{answer}: raw_sem={raw_sem_percent:.2f} cal_sem={cal_sem:.2f} '
                f'lexical={lexical} final={final}'
            )


if __name__ == '__main__':
    main()
