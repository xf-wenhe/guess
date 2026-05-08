import csv
import json
import os
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

PUZZLES_JSON = Path(os.getenv('SEM_PUZZLES_JSON', 'assets/puzzles.json'))
MANUAL_OVERRIDES = Path(os.getenv('SEM_MANUAL_OVERRIDES', 'data/manual_similarity_overrides.json'))
AUDIT_JSON = Path(os.getenv('SEM_HINT_AUDIT_JSON', 'tmp/hints_audit_v28_after.json'))
BASE_MODEL = os.getenv('SEM_BASE_MODEL', 'models/bge-m3-finetuned-v27-semreal-anchor')
OUTPUT_CSV = Path(os.getenv('SEM_OUTPUT_CSV', 'data/train_v27_hard_mining.csv'))
SEED = int(os.getenv('SEM_SEED', '20260304'))
TOP_K_CROSS = int(os.getenv('SEM_TOP_K_CROSS', '10'))
TOP_K_SAME = int(os.getenv('SEM_TOP_K_SAME', '8'))

FIELDNAMES = [
    'id', 'answer', 'user_input', 'answer_category', 'input_category_guess',
    'relation_tag', 'expected_range', 'score_0_100', 'reason', 'reviewer'
]

TARGETS = [30, 40, 50, 60, 70, 80, 90]


def relation_for_score(score: int) -> str:
    if score >= 85:
        return 'alias_synonym_high'
    if score >= 70:
        return 'near_synonym_high'
    if score >= 50:
        return 'related_mid'
    if score >= 30:
        return 'related_low'
    return 'hard_negative_low'


def range_for_score(score: int) -> str:
    left = max(0, score - 5)
    right = min(100, score + 5)
    return f'{left}-{right}'


def clamp_score(v):
    return int(max(0, min(100, round(float(v)))))


def add_row(rows, seen, answer, user_input, score, category, reason, reviewer):
    a = str(answer).strip()
    b = str(user_input).strip()
    if not a or not b:
        return
    score = clamp_score(score)
    if a == b:
        score = max(score, 98)
    key = (a, b)
    if key in seen:
        return
    seen.add(key)
    rows.append({
        'id': '',
        'answer': a,
        'user_input': b,
        'answer_category': category,
        'input_category_guess': '',
        'relation_tag': relation_for_score(score),
        'expected_range': range_for_score(score),
        'score_0_100': str(score),
        'reason': reason,
        'reviewer': reviewer,
    })


def main():
    if not PUZZLES_JSON.exists():
        raise SystemExit(f'missing file: {PUZZLES_JSON}')

    rng = random.Random(SEED)
    puzzles = json.loads(PUZZLES_JSON.read_text(encoding='utf-8'))

    rows = []
    seen = set()

    answers = []
    categories = {}
    by_cat = defaultdict(list)

    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        hints = [str(h).strip() for h in (item.get('hints') or [])]
        if not answer:
            continue
        answers.append(answer)
        categories[answer] = category
        by_cat[category].append(answer)

        add_row(rows, seen, answer, answer, 98, category, 'self_anchor', 'hard_mining_v27')

        if len(hints) == 7:
            for idx, h in enumerate(hints):
                if not h:
                    continue
                t = TARGETS[idx]
                add_row(rows, seen, answer, h, t, category, f'hint_lvl_{idx+1}', 'hard_mining_v27')
                if t >= 70:
                    add_row(rows, seen, h, answer, min(95, t + 5), category, f'reverse_hint_lvl_{idx+1}', 'hard_mining_v27')

    uniq_answers = list(dict.fromkeys(answers))

    model = SentenceTransformer(BASE_MODEL, device='cpu', local_files_only=True)
    emb = model.encode(uniq_answers, normalize_embeddings=True, batch_size=256)

    # Hard negatives: highly similar cross-category answers should be pushed lower.
    for i, a in enumerate(uniq_answers):
        cat = categories.get(a, '')
        sims = np.dot(emb, emb[i])
        order = np.argsort(-sims)
        picked = 0
        for j in order:
            j = int(j)
            if j == i:
                continue
            b = uniq_answers[j]
            if categories.get(b, '') == cat:
                continue
            sim = float(sims[j])
            score = 18 - (picked * 2)
            if sim > 0.68:
                score = min(score, 8)
            elif sim > 0.62:
                score = min(score, 10)
            elif sim > 0.56:
                score = min(score, 12)
            add_row(rows, seen, a, b, max(4, score), cat, f'hard_negative_cross_sim_{sim:.3f}', 'hard_mining_v27')
            picked += 1
            if picked >= TOP_K_CROSS:
                break

    # Hard positives: closest same-category answers should keep medium/high relatedness.
    for i, a in enumerate(uniq_answers):
        cat = categories.get(a, '')
        sims = np.dot(emb, emb[i])
        order = np.argsort(-sims)
        picked = 0
        for j in order:
            j = int(j)
            if j == i:
                continue
            b = uniq_answers[j]
            if categories.get(b, '') != cat:
                continue
            sim = float(sims[j])
            base = 52 + max(0, min(28, int((sim - 0.45) * 100)))
            add_row(rows, seen, a, b, base, cat, f'hard_positive_same_cat_{sim:.3f}', 'hard_mining_v27')
            picked += 1
            if picked >= TOP_K_SAME:
                break

    # Manual high-quality anchors
    if MANUAL_OVERRIDES.exists():
        decoded = json.loads(MANUAL_OVERRIDES.read_text(encoding='utf-8'))
        for item in decoded:
            if not isinstance(item, dict):
                continue
            a = str(item.get('answer', '')).strip()
            b = str(item.get('user_input', '')).strip()
            s = item.get('score')
            if not a or not b or not isinstance(s, (int, float)):
                continue
            add_row(rows, seen, a, b, int(round(float(s))), categories.get(a, ''), 'manual_override', 'manual_gold')

    # Recover false negatives from hint audit
    if AUDIT_JSON.exists():
        try:
            audit = json.loads(AUDIT_JSON.read_text(encoding='utf-8'))
        except Exception:
            audit = {}
        lows = audit.get('low_top50') or []
        for row in lows:
            if not isinstance(row, dict):
                continue
            a = str(row.get('answer', '')).strip()
            h = str(row.get('hint', '')).strip()
            target = row.get('target', 60)
            if not a or not h:
                continue
            score = max(35, min(92, int(target)))
            add_row(rows, seen, a, h, score, categories.get(a, ''), 'recover_false_negative_from_audit', 'hard_mining_v27')

    rng.shuffle(rows)
    for idx, row in enumerate(rows, start=1):
        row['id'] = str(idx)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)

    print(f'rows={len(rows)}')
    print(f'answers={len(uniq_answers)}')
    print(f'written={OUTPUT_CSV}')


if __name__ == '__main__':
    main()
