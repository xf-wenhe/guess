import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer

from semantic_common import apply_calibration, semantic_multi_angle

PAIRS_PATH = Path('data/regression_pairs_v23.json')
MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v27-semreal-anchor')
CALIB_PATH = Path(os.getenv('SEM_CALIB_PATH', 'data/semantic_calibration_v27_semreal_anchor.json'))
OVERRIDES_PATH = Path(os.getenv('SEM_OVERRIDES_PATH', 'data/manual_similarity_overrides.json'))

REQUIRED_ANTONYM_PAIRS = [
    {"pair": ["高兴", "难过"], "type": "antonym", "target_min": 45, "target_max": 55},
    {"pair": ["快乐", "悲伤"], "type": "antonym", "target_min": 45, "target_max": 55},
    {"pair": ["胜利", "失败"], "type": "antonym", "target_min": 45, "target_max": 55},
    {"pair": ["白天", "黑夜"], "type": "antonym", "target_min": 45, "target_max": 55},
    {"pair": ["古代", "现代"], "type": "antonym", "target_min": 45, "target_max": 55},
]


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


def load_overrides(path: Path):
    if not path.exists():
        return {}
    decoded = json.loads(path.read_text(encoding='utf-8'))
    overrides = {}
    if not isinstance(decoded, list):
        return overrides
    for item in decoded:
        if not isinstance(item, dict):
            continue
        answer = str(item.get('answer', '')).strip()
        user_input = str(item.get('user_input', '')).strip()
        score = item.get('score')
        if not answer or not user_input or not isinstance(score, (int, float)):
            continue
        overrides[f'{answer}\t{user_input}'] = int(round(score))
    return overrides


def load_regression_pairs(path: Path):
    pairs = json.loads(path.read_text(encoding='utf-8'))
    seen = {
        (tuple(item.get('pair', [])), item.get('type'))
        for item in pairs
        if isinstance(item, dict)
    }
    for item in REQUIRED_ANTONYM_PAIRS:
        key = (tuple(item['pair']), item['type'])
        if key not in seen:
            pairs.append(dict(item))
            seen.add(key)
    return pairs


def main():
    if not PAIRS_PATH.exists():
        raise SystemExit(f'missing file: {PAIRS_PATH}')
    if not CALIB_PATH.exists():
        raise SystemExit(f'missing file: {CALIB_PATH}')

    pairs = load_regression_pairs(PAIRS_PATH)
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    overrides = load_overrides(OVERRIDES_PATH)
    x = calib['x_pred']
    y = calib['y_calibrated']

    try:
        model = SentenceTransformer(
            MODEL_PATH,
            device='cpu',
            tokenizer_kwargs={'fix_mistral_regex': True},
            local_files_only=True,
        )
    except TypeError:
        model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)

    print(f'model={MODEL_PATH}')
    print(f'calibration={CALIB_PATH}')
    print('pair,type,raw_sem,cal_sem,lexical,final,check_score,check_basis,target,pass')

    total = 0
    passed = 0
    by_type = {}

    for item in pairs:
        guess, answer = item['pair']
        pair_type = item['type']
        target_min = int(item['target_min'])
        target_max = int(item['target_max'])

        raw_sem = semantic_multi_angle(model, guess, answer)
        cal_sem = apply_calibration(raw_sem, x, y)
        lexical = lexical_score(guess, answer)
        key1 = f'{answer}\t{guess}'
        key2 = f'{guess}\t{answer}'
        override = overrides.get(key1)
        if override is None:
            override = overrides.get(key2)
        final = override if override is not None else final_score(cal_sem, lexical)

        check_basis = item.get('check_basis')
        if check_basis is None:
            check_basis = 'cal_sem' if pair_type == 'antonym' else 'final'
        check_score = cal_sem if check_basis == 'cal_sem' else final

        ok = target_min <= check_score <= target_max
        total += 1
        passed += 1 if ok else 0

        if pair_type not in by_type:
            by_type[pair_type] = {'total': 0, 'passed': 0}
        by_type[pair_type]['total'] += 1
        by_type[pair_type]['passed'] += 1 if ok else 0

        print(
            f'{guess}-{answer},{pair_type},{raw_sem:.2f},{cal_sem:.2f},{lexical},{final},'
            f'{check_score:.2f},{check_basis},'
            f'{target_min}-{target_max},{"PASS" if ok else "FAIL"}'
        )

    print('\nsummary:')
    print(f'total={total} passed={passed} pass_rate={passed/total*100:.1f}%')
    for pair_type in sorted(by_type):
        t = by_type[pair_type]['total']
        p = by_type[pair_type]['passed']
        print(f'{pair_type}: {p}/{t} ({p/t*100:.1f}%)')


if __name__ == '__main__':
    main()
