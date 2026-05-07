import json
import os
import urllib.request
from pathlib import Path

EMBED_URL = 'http://127.0.0.1:8000/embed'
ANGLES = ['从含义角度看：', '从用途角度看：', '从场景角度看：', '从特征角度看：', '从关联角度看：']


def embed(text: str):
    body = json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(
        EMBED_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['embedding']


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def semantic_multi_angle(guess: str, answer: str):
    scores = []
    for angle in ANGLES:
        vg = embed(f'{angle}{guess}')
        va = embed(f'{angle}{answer}')
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


def main():
    calib_path = Path(os.getenv('SEM_CALIB_PATH', 'data/semantic_calibration_v21_refine.json'))
    calib = json.loads(calib_path.read_text(encoding='utf-8'))
    x = calib['x_pred']
    y = calib['y_calibrated']

    print(f'calibration={calib_path}')

    for guess, answer in [('猫咪', '猫'), ('猫咪', '刘备')]:
        semantic = semantic_multi_angle(guess, answer)
        raw_sem_percent = semantic * 100.0
        calibrated_percent = apply_calibration(raw_sem_percent, x, y)
        lexical = calculate_similarity(guess, answer)

        semantic_weight = 0.8
        lexical_weight = 0.2
        is_near_synonym_like = lexical >= 40 and calibrated_percent >= 20

        combined = round((calibrated_percent * semantic_weight) + (lexical * lexical_weight))

        if lexical == 0:
            if calibrated_percent < 20:
                combined = min(combined, 10)
            elif calibrated_percent < 25:
                combined = min(combined, 12)

        final = normalize_similarity(combined)
        if is_near_synonym_like:
            final = max(final, 30)
        print(
            f'{guess}-{answer}\traw_sem={raw_sem_percent:.2f}\tcal_sem={calibrated_percent:.2f}\t'
            f'lexical={lexical}\tfinal={final}\tweights={semantic_weight:.1f}/{lexical_weight:.1f}'
        )


if __name__ == '__main__':
    main()
