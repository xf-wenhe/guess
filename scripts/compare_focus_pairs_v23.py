import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

ANGLES = ['从含义角度看：', '从用途角度看：', '从场景角度看：', '从特征角度看：', '从关联角度看：']
PAIRS = [('猫咪', '猫'), ('猫咪', '刘备')]
MODELS = [
    ('v21_refine', 'models/bge-m3-finetuned-v21-refine', 'data/semantic_calibration_v21_refine.json'),
    ('v23', 'models/bge-m3-finetuned-v23', 'data/semantic_calibration_v23.json'),
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
    return sum(trimmed) / len(trimmed) * 100.0


def apply_calibration(pred, x, y):
    if pred <= x[0]:
        return y[0]
    if pred >= x[-1]:
        return y[-1]
    for i in range(len(x) - 1):
        left, right = x[i], x[i + 1]
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return y[i]
            t = (pred - left) / span
            return y[i] + (y[i + 1] - y[i]) * t
    return pred


def lexical_score(guess: str, target: str):
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


def normalize_similarity(value: int):
    n = max(10, min(100, value))
    if n >= 95:
        return 95
    if 20 <= n <= 40:
        return 10 + ((n - 20) * 10 // 20)
    return n


def final_score(cal_sem: float, lexical: int):
    combined = round(cal_sem * 0.8 + lexical * 0.2)

    if lexical == 0:
        if cal_sem < 20:
            combined = min(combined, 10)
        elif cal_sem < 25:
            combined = min(combined, 12)

    final = normalize_similarity(combined)
    if lexical >= 40 and cal_sem >= 20:
        final = max(final, 30)
    return final


def main():
    print('pair,model,raw_sem,cal_sem,lexical,final')
    for name, model_path, calib_path in MODELS:
        model = SentenceTransformer(model_path, device='cpu')
        calib = json.loads(Path(calib_path).read_text(encoding='utf-8'))
        x = calib['x_pred']
        y = calib['y_calibrated']

        for guess, answer in PAIRS:
            raw_sem = semantic_multi_angle(model, guess, answer)
            cal_sem = apply_calibration(raw_sem, x, y)
            lex = lexical_score(guess, answer)
            final = final_score(cal_sem, lex)
            print(f'{guess}-{answer},{name},{raw_sem:.2f},{cal_sem:.2f},{lex},{final}')


if __name__ == '__main__':
    main()
