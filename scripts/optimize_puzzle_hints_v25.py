import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

PUZZLES_PATH = Path(os.getenv('PUZZLES_PATH', 'assets/puzzles.json'))
MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v24-patch')
CALIB_PATH = Path(os.getenv('SEM_CALIB_PATH', 'data/semantic_calibration_v24_patch.json'))
TARGETS = [30, 40, 50, 60, 70, 80, 90]

MIN_LEN = 2
MAX_LEN = 8


@dataclass
class Candidate:
    text: str
    score: float


def apply_calibration(pred: float, x: List[float], y: List[float]) -> float:
    if pred <= x[0]:
        return float(y[0])
    if pred >= x[-1]:
        return float(y[-1])
    for i in range(len(x) - 1):
        left, right = float(x[i]), float(x[i + 1])
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return float(y[i])
            t = (pred - left) / span
            return float(y[i] + (y[i + 1] - y[i]) * t)
    return pred


def is_usable_hint(text: str, answer: str) -> bool:
    txt = text.strip()
    if not txt or txt == answer:
        return False
    ln = len(txt)
    if ln < MIN_LEN or ln > MAX_LEN:
        return False
    if any(ch.isdigit() for ch in txt):
        return False
    return True


def choose_hints(candidates: List[Candidate], targets: List[int]) -> Tuple[List[str], List[float]]:
    chosen_texts: List[str] = []
    chosen_scores: List[float] = []
    used = set()
    last_score = -1.0

    for target in targets:
        best_idx = -1
        best_cost = 1e9
        for idx, c in enumerate(candidates):
            if c.text in used:
                continue
            if c.score <= last_score + 0.2:
                continue
            cost = abs(c.score - target)
            if cost < best_cost:
                best_cost = cost
                best_idx = idx

        if best_idx < 0:
            for idx, c in enumerate(candidates):
                if c.text in used:
                    continue
                cost = abs(c.score - target) + (0.0 if c.score > last_score else 10.0)
                if cost < best_cost:
                    best_cost = cost
                    best_idx = idx

        if best_idx < 0:
            break

        picked = candidates[best_idx]
        used.add(picked.text)
        chosen_texts.append(picked.text)
        chosen_scores.append(picked.score)
        last_score = max(last_score, picked.score)

    return chosen_texts, chosen_scores


def main() -> None:
    if not PUZZLES_PATH.exists():
        raise SystemExit(f'missing file: {PUZZLES_PATH}')
    if not CALIB_PATH.exists():
        raise SystemExit(f'missing file: {CALIB_PATH}')

    puzzles = json.loads(PUZZLES_PATH.read_text(encoding='utf-8'))
    if not isinstance(puzzles, list) or not puzzles:
        raise SystemExit('invalid puzzles json')

    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    x = calib['x_pred']
    y = calib['y_calibrated']

    answers = [str(item.get('answer', '')).strip() for item in puzzles if str(item.get('answer', '')).strip()]
    uniq_answers = list(dict.fromkeys(answers))

    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)

    answer_emb = model.encode(uniq_answers, normalize_embeddings=True)
    answer_index = {a: i for i, a in enumerate(uniq_answers)}

    all_hint_texts = []
    for item in puzzles:
        for h in (item.get('hints') or []):
            hs = str(h).strip()
            if hs:
                all_hint_texts.append(hs)
    all_hint_texts = list(dict.fromkeys(all_hint_texts))

    hint_emb = model.encode(all_hint_texts, normalize_embeddings=True) if all_hint_texts else np.zeros((0, 1), dtype=np.float32)

    total = 0
    changed = 0
    mae_sum = 0.0
    details = []

    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        if not answer or answer not in answer_index:
            continue
        total += 1
        vec = answer_emb[answer_index[answer]]

        candidates: List[Candidate] = []

        sims_answers = np.dot(answer_emb, vec)
        order = np.argsort(-sims_answers)
        for idx in order:
            txt = uniq_answers[int(idx)]
            if not is_usable_hint(txt, answer):
                continue
            raw = float(sims_answers[int(idx)] * 100.0)
            cal = apply_calibration(raw, x, y)
            candidates.append(Candidate(text=txt, score=cal))
            if len(candidates) >= 400:
                break

        if len(all_hint_texts) > 0:
            sims_hints = np.dot(hint_emb, vec)
            hint_order = np.argsort(-sims_hints)
            for idx in hint_order[:800]:
                txt = all_hint_texts[int(idx)]
                if not is_usable_hint(txt, answer):
                    continue
                raw = float(sims_hints[int(idx)] * 100.0)
                cal = apply_calibration(raw, x, y)
                candidates.append(Candidate(text=txt, score=cal))

        dedup = {}
        for c in candidates:
            old = dedup.get(c.text)
            if old is None or abs(c.score - 60.0) < abs(old.score - 60.0):
                dedup[c.text] = c
        candidates = sorted(dedup.values(), key=lambda c: c.score)

        chosen_hints, chosen_scores = choose_hints(candidates, TARGETS)

        if len(chosen_hints) < 7:
            existing = [str(h).strip() for h in (item.get('hints') or []) if str(h).strip()]
            for h in existing:
                if h not in chosen_hints and is_usable_hint(h, answer):
                    chosen_hints.append(h)
                    chosen_scores.append(float(TARGETS[min(len(chosen_scores), len(TARGETS) - 1)]))
                if len(chosen_hints) >= 7:
                    break

        chosen_hints = chosen_hints[:7]
        chosen_scores = chosen_scores[:7]

        if len(chosen_hints) < 7:
            fallback = ['意象', '场景', '动作', '情绪', '特征', '关联', '近义']
            for token in fallback:
                if token not in chosen_hints:
                    chosen_hints.append(token)
                    chosen_scores.append(float(TARGETS[min(len(chosen_scores), len(TARGETS) - 1)]))
                if len(chosen_hints) >= 7:
                    break

        old_hints = [str(h).strip() for h in (item.get('hints') or [])]
        item['hints'] = chosen_hints
        if old_hints[:7] != chosen_hints:
            changed += 1

        err = 0.0
        for i, score in enumerate(chosen_scores):
            err += abs(score - TARGETS[i])
        mae = err / len(chosen_scores) if chosen_scores else 100.0
        mae_sum += mae
        details.append({'answer': answer, 'mae_to_targets': round(mae, 2)})

    PUZZLES_PATH.write_text(json.dumps(puzzles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    report_path = Path('tmp/hint_optimization_v25_report.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'total_puzzles': total,
        'changed_puzzles': changed,
        'avg_mae_to_targets': round(mae_sum / max(total, 1), 3),
        'targets': TARGETS,
        'top10': details[:10],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'total={total} changed={changed} avg_mae={report["avg_mae_to_targets"]}')
    print(f'written={PUZZLES_PATH}')
    print(f'report={report_path}')


if __name__ == '__main__':
    main()