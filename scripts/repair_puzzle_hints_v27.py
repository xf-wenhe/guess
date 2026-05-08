import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

PUZZLES_PATH = Path(os.getenv('PUZZLES_PATH', 'assets/puzzles.json'))
MODEL_PATH = os.getenv('SEM_MODEL_PATH', 'models/bge-m3-finetuned-v26-unsup')
CALIB_PATH = Path(os.getenv('SEM_CALIB_PATH', 'data/semantic_calibration_v26_gold.json'))

TARGETS = [30, 40, 50, 60, 70, 80, 90]
FLOORS = [18, 24, 32, 42, 52, 62, 72]
MIN_GAP = 2.0

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    '文化': ['传统', '曲艺', '民俗', '舞台', '表演', '艺术', '戏剧'],
    '风景': ['自然', '景观', '山川', '地貌', '水域', '户外', '远眺'],
    '学科': ['知识', '理论', '学习', '研究', '方法', '体系', '课程'],
    '人物': ['历史', '名人', '角色', '事迹', '生平', '称谓', '典故'],
    '成语': ['典型说法', '固定词组', '比喻', '寓意', '言简意赅', '常见表达', '语义凝练'],
    '典故': ['历史事件', '出处', '人物故事', '寓意', '典籍', '传说', '背景'],
    '歇后语': ['俗语', '民间说法', '前后句', '言外之意', '比喻', '口语表达', '俚语'],
    '旅游': ['行程', '出行', '目的地', '路线', '游玩', '风土', '体验'],
    '工作': ['职场', '流程', '协作', '任务', '汇报', '执行', '岗位'],
    '学习': ['课堂', '练习', '理解', '复习', '知识点', '方法', '作业'],
    '动作': ['行为', '姿态', '移动', '发力', '步骤', '过程', '执行'],
    '情感': ['情绪', '心理', '感受', '状态', '心境', '内心', '表达'],
    '感情': ['情绪', '心理', '感受', '状态', '心境', '内心', '表达'],
}


@dataclass
class Cand:
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
    if not txt:
        return False
    if txt == answer:
        return False
    if len(txt) < 2 or len(txt) > 8:
        return False
    return True


def select_hints(cands: List[Cand]) -> Tuple[List[str], List[float]]:
    selected: List[Cand] = []
    used = set()
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
            cost = abs(c.score - target) + c.source_rank * 0.8
            if cost < best_cost:
                best_cost = cost
                best = c

        if best is None:
            for c in cands:
                if c.text in used:
                    continue
                if c.score < max(12, floor - 8):
                    continue
                if c.score < last_score + 0.5:
                    continue
                cost = abs(c.score - target) + c.source_rank * 1.2
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
            if c.score < max(12, last_score):
                continue
            selected.append(c)
            used.add(c.text)
            last_score = c.score
            if len(selected) >= 7:
                break

    selected = selected[:7]
    return [c.text for c in selected], [float(c.score) for c in selected]


def main() -> None:
    if not PUZZLES_PATH.exists():
        raise SystemExit(f'missing file: {PUZZLES_PATH}')
    if not CALIB_PATH.exists():
        raise SystemExit(f'missing file: {CALIB_PATH}')

    puzzles = json.loads(PUZZLES_PATH.read_text(encoding='utf-8'))
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    x = calib['x_pred']
    y = calib['y_calibrated']

    answers = []
    by_cat = defaultdict(list)
    for item in puzzles:
        a = str(item.get('answer', '')).strip()
        cat = str(item.get('category', '')).strip()
        if a:
            answers.append(a)
            by_cat[cat].append(a)
    uniq_answers = list(dict.fromkeys(answers))

    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)

    ans_emb = model.encode(uniq_answers, normalize_embeddings=True)
    ans_index = {a: i for i, a in enumerate(uniq_answers)}

    changed = 0
    unresolved = 0
    total_mae = 0.0

    for item in puzzles:
        answer = str(item.get('answer', '')).strip()
        cat = str(item.get('category', '')).strip()
        if not answer or answer not in ans_index:
            continue

        raw_hints = [str(h).strip() for h in (item.get('hints') or []) if str(h).strip()]
        same_cat_answers = [x for x in by_cat.get(cat, []) if x != answer]
        cat_words = CATEGORY_KEYWORDS.get(cat, ['相关', '语义', '场景', '特征', '用途', '表达', '关联'])

        candidates_text = []
        source_rank_map = {}

        for txt in same_cat_answers[:120]:
            if is_valid_hint(txt, answer):
                candidates_text.append(txt)
                source_rank_map.setdefault(txt, 0)

        for txt in raw_hints:
            if is_valid_hint(txt, answer):
                candidates_text.append(txt)
                source_rank_map.setdefault(txt, 1)

        for txt in cat_words:
            if is_valid_hint(txt, answer):
                candidates_text.append(txt)
                source_rank_map.setdefault(txt, 2)

        candidates_text = list(dict.fromkeys(candidates_text))

        if not candidates_text:
            unresolved += 1
            continue

        a_vec = ans_emb[ans_index[answer]]
        c_emb = model.encode(candidates_text, normalize_embeddings=True)
        sims = np.dot(c_emb, a_vec)

        cands: List[Cand] = []
        for txt, sim in zip(candidates_text, sims):
            raw = float(sim * 100.0)
            cal = apply_calibration(raw, x, y)
            if cal < 10:
                continue
            cands.append(Cand(text=txt, score=cal, source_rank=source_rank_map.get(txt, 3)))

        cands.sort(key=lambda c: (c.score, c.source_rank))

        new_hints, scores = select_hints(cands)

        if len(new_hints) < 7:
            unresolved += 1
            fill_pool = [t for t in (cat_words + raw_hints + same_cat_answers) if is_valid_hint(t, answer)]
            for txt in fill_pool:
                if txt not in new_hints:
                    new_hints.append(txt)
                if len(new_hints) >= 7:
                    break

        new_hints = new_hints[:7]
        old_hints = [str(h).strip() for h in (item.get('hints') or [])][:7]
        if old_hints != new_hints:
            changed += 1
        item['hints'] = new_hints

        if scores:
            s = scores[:7]
            while len(s) < 7:
                s.append(s[-1] if s else 10.0)
            mae = sum(abs(sv - tv) for sv, tv in zip(s, TARGETS)) / 7.0
            total_mae += mae

    PUZZLES_PATH.write_text(json.dumps(puzzles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    report = {
        'items': len(puzzles),
        'changed': changed,
        'unresolved_fill': unresolved,
        'avg_target_mae': round(total_mae / max(len(puzzles), 1), 3),
        'targets': TARGETS,
        'floors': FLOORS,
        'model': MODEL_PATH,
        'calibration': str(CALIB_PATH),
    }
    report_path = Path('tmp/hints_repair_v27_report.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"items={report['items']} changed={report['changed']} unresolved_fill={report['unresolved_fill']}")
    print(f"avg_target_mae={report['avg_target_mae']}")
    print(f'written={PUZZLES_PATH}')
    print(f'report={report_path}')


if __name__ == '__main__':
    main()
