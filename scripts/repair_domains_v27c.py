import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

import numpy as np
from sentence_transformers import SentenceTransformer

PUZZLES_PATH = Path('assets/puzzles.json')
MODEL_PATH = 'models/bge-m3-finetuned-v26-unsup'
CALIB_PATH = Path('data/semantic_calibration_v26_gold.json')

TARGET_CATEGORIES = {'人物', '学科', '旅游'}
TARGETS = [30, 40, 50, 60, 70, 80, 90]
FLOORS = [22, 30, 38, 48, 58, 68, 78]
MIN_GAP = 2.0

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    '人物': ['历史人物', '角色称谓', '生平事迹', '人物特征', '相关典故', '时代背景', '代表形象'],
    '学科': ['课程知识', '概念体系', '研究方法', '核心理论', '学习内容', '学科框架', '知识结构'],
    '旅游': ['旅行场景', '出行安排', '行程体验', '目的地要素', '在地活动', '路线规划', '游玩方式'],
}


@dataclass
class Candidate:
    text: str
    score: float
    source_rank: int


def apply_calibration(pred: float, x: List[float], y: List[float]) -> float:
    if pred <= x[0]:
        return float(y[0])
    if pred >= x[-1]:
        return float(y[-1])
    for i in range(len(x) - 1):
        left = float(x[i])
        right = float(x[i + 1])
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return float(y[i])
            t = (pred - left) / span
            return float(y[i] + (y[i + 1] - y[i]) * t)
    return pred


def is_valid_hint(text: str, answer: str) -> bool:
    txt = text.strip()
    if not txt or txt == answer:
        return False
    if len(txt) < 2 or len(txt) > 10:
        return False
    return True


def pick_hints(cands: List[Candidate]) -> List[str]:
    selected: List[Candidate] = []
    used: Set[str] = set()
    last_score = -1e9

    for idx, target in enumerate(TARGETS):
        floor = FLOORS[idx]
        best = None
        best_cost = 1e9

        for c in cands:
            if c.text in used:
                continue
            if c.score < floor:
                continue
            if c.score < last_score + MIN_GAP:
                continue
            cost = abs(c.score - target) + c.source_rank * 0.7
            if cost < best_cost:
                best_cost = cost
                best = c

        if best is None:
            for c in cands:
                if c.text in used:
                    continue
                if c.score < max(15, floor - 10):
                    continue
                if c.score < last_score + 0.5:
                    continue
                cost = abs(c.score - target) + c.source_rank * 1.1
                if cost < best_cost:
                    best_cost = cost
                    best = c

        if best is None:
            break

        selected.append(best)
        used.add(best.text)
        last_score = best.score

    if len(selected) < 7:
        for c in cands:
            if c.text in used:
                continue
            if c.score < 15:
                continue
            selected.append(c)
            used.add(c.text)
            if len(selected) >= 7:
                break

    return [c.text for c in selected[:7]]


def main() -> None:
    puzzles = json.loads(PUZZLES_PATH.read_text(encoding='utf-8'))
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    x = calib['x_pred']
    y = calib['y_calibrated']

    answers = []
    by_category: Dict[str, List[str]] = {}
    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        cat = str(item.get('category', '')).strip()
        if not answer:
            continue
        answers.append(answer)
        by_category.setdefault(cat, []).append(answer)

    uniq_answers = list(dict.fromkeys(answers))
    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)
    ans_emb = model.encode(uniq_answers, normalize_embeddings=True)
    ans_index = {a: i for i, a in enumerate(uniq_answers)}

    changed = 0

    for item in puzzles:
        cat = str(item.get('category', '')).strip()
        if cat not in TARGET_CATEGORIES:
            continue

        answer = str(item.get('answer', '')).strip()
        if not answer or answer not in ans_index:
            continue

        raw_hints = [str(h).strip() for h in (item.get('hints') or []) if str(h).strip()]
        same_cat_answers = [a for a in by_category.get(cat, []) if a != answer]
        cat_keywords = CATEGORY_KEYWORDS.get(cat, [])

        candidates_text = []
        source_rank: Dict[str, int] = {}

        # strongest: existing hints (but later filtered by score)
        for txt in raw_hints:
            if is_valid_hint(txt, answer):
                candidates_text.append(txt)
                source_rank.setdefault(txt, 0)

        # medium: category-specific keywords
        for txt in cat_keywords:
            if is_valid_hint(txt, answer):
                candidates_text.append(txt)
                source_rank.setdefault(txt, 1)

        # weak-mid: same-category answers for diversity
        for txt in same_cat_answers[:120]:
            if is_valid_hint(txt, answer):
                candidates_text.append(txt)
                source_rank.setdefault(txt, 2)

        # dedup keep order
        dedup = []
        seen = set()
        for txt in candidates_text:
            if txt not in seen:
                seen.add(txt)
                dedup.append(txt)
        candidates_text = dedup

        if not candidates_text:
            continue

        a_vec = ans_emb[ans_index[answer]]
        c_emb = model.encode(candidates_text, normalize_embeddings=True)
        sims = np.dot(c_emb, a_vec)

        cands: List[Candidate] = []
        for txt, sim in zip(candidates_text, sims):
            raw = float(sim * 100.0)
            cal = apply_calibration(raw, x, y)
            if cal < 15:
                continue
            cands.append(Candidate(text=txt, score=cal, source_rank=source_rank.get(txt, 3)))

        cands.sort(key=lambda c: (c.score, c.source_rank))
        new_hints = pick_hints(cands)

        if len(new_hints) < 7:
            # fallback with category keywords
            for txt in cat_keywords + raw_hints + same_cat_answers:
                if txt == answer or not txt:
                    continue
                if txt not in new_hints:
                    new_hints.append(txt)
                if len(new_hints) >= 7:
                    break

        new_hints = new_hints[:7]
        old_hints = [str(h).strip() for h in (item.get('hints') or [])][:7]
        if old_hints != new_hints:
            item['hints'] = new_hints
            changed += 1

    PUZZLES_PATH.write_text(json.dumps(puzzles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    report = {
        'categories': sorted(TARGET_CATEGORIES),
        'changed': changed,
        'items': len(puzzles),
        'model': MODEL_PATH,
        'calibration': str(CALIB_PATH),
    }
    report_path = Path('tmp/hints_repair_v27c_report.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"changed={changed} items={len(puzzles)}")
    print(f"written={PUZZLES_PATH}")
    print(f"report={report_path}")


if __name__ == '__main__':
    main()
