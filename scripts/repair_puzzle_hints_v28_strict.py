import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

PUZZLES_PATH = Path('assets/puzzles.json')
MODEL_PATH = 'models/bge-m3-finetuned-v26-unsup'
CALIB_PATH = Path('data/semantic_calibration_v26_gold.json')

TARGETS = [30, 40, 50, 60, 70, 80, 90]
FLOORS = [16, 24, 32, 42, 52, 62, 72]
MIN_GAP = 1.0

CATEGORY_KEYWORDS = {
    '文化': ['传统', '曲艺', '民俗', '舞台', '表演', '戏剧', '艺术'],
    '风景': ['自然', '景观', '地貌', '山川', '户外', '水域', '远眺'],
    '学科': ['知识', '理论', '学习', '研究', '方法', '体系', '课程'],
    '人物': ['历史人物', '角色称谓', '生平事迹', '时代背景', '人物特征', '典故', '代表形象'],
    '成语': ['固定词组', '寓意', '比喻', '语义凝练', '常见表达', '典型说法', '习用语'],
    '典故': ['历史事件', '出处', '故事背景', '人物线索', '典籍', '传说', '寓意'],
    '歇后语': ['俗语', '前后句', '言外之意', '口语表达', '民间说法', '比喻', '俚语'],
    '旅游': ['出行', '行程', '游玩', '目的地', '路线', '在地体验', '旅行场景'],
    '工作': ['职场', '任务', '流程', '协作', '执行', '汇报', '岗位'],
    '学习': ['课堂', '练习', '复习', '理解', '作业', '知识点', '方法'],
    '动作': ['行为', '姿态', '移动', '发力', '步骤', '过程', '执行'],
    '情感': ['情绪', '心境', '感受', '心理', '状态', '内心', '表达'],
    '感情': ['情绪', '心境', '感受', '心理', '状态', '内心', '表达'],
}


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


def valid(text, answer):
    t = text.strip()
    if not t or t == answer:
        return False
    if len(t) < 2 or len(t) > 10:
        return False
    return True


def calibrate_vec(raw_scores, x, y):
    out = np.zeros_like(raw_scores)
    for i, v in enumerate(raw_scores):
        out[i] = apply_calibration(float(v), x, y)
    return out


def main():
    data = json.loads(PUZZLES_PATH.read_text(encoding='utf-8'))
    calib = json.loads(CALIB_PATH.read_text(encoding='utf-8'))
    x, y = calib['x_pred'], calib['y_calibrated']

    answers = []
    by_cat = defaultdict(list)
    all_hints = set()

    for item in data:
        a = str(item.get('answer', '')).strip()
        c = str(item.get('category', '')).strip()
        if a:
            answers.append(a)
            by_cat[c].append(a)
        for h in (item.get('hints') or []):
            hs = str(h).strip()
            if hs:
                all_hints.add(hs)

    uniq_answers = list(dict.fromkeys(answers))

    pool = set(uniq_answers)
    pool.update(all_hints)
    for ws in CATEGORY_KEYWORDS.values():
        pool.update(ws)
    pool = [p for p in pool if len(p) >= 2]

    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)
    pool_emb = model.encode(pool, normalize_embeddings=True, batch_size=256)

    pool_index = {t: i for i, t in enumerate(pool)}
    answer_index = {a: pool_index[a] for a in uniq_answers if a in pool_index}

    changed = 0

    for item in data:
        ans = str(item.get('answer', '')).strip()
        cat = str(item.get('category', '')).strip()
        old_hints = [str(h).strip() for h in (item.get('hints') or [])]
        if ans not in answer_index:
            continue

        ans_vec = pool_emb[answer_index[ans]]
        sims = np.dot(pool_emb, ans_vec) * 100.0
        cal_scores = calibrate_vec(sims, x, y)

        # build candidate subset: global high-sim + same-cat answers + category words + old hints
        top_idx = np.argsort(-sims)[:260]
        subset = set(int(i) for i in top_idx)

        for t in by_cat.get(cat, []):
            idx = pool_index.get(t)
            if idx is not None:
                subset.add(idx)

        for t in CATEGORY_KEYWORDS.get(cat, []):
            idx = pool_index.get(t)
            if idx is not None:
                subset.add(idx)

        for t in old_hints:
            idx = pool_index.get(t)
            if idx is not None:
                subset.add(idx)

        cands = []
        for idx in subset:
            t = pool[idx]
            if valid(t, ans):
                sc = float(cal_scores[idx])
                if sc >= 12:
                    cands.append((t, sc))

        cands.sort(key=lambda z: z[1])

        new_hints = []
        used = set()
        last = -1e9

        for i, target in enumerate(TARGETS):
            floor = FLOORS[i]
            best = None
            best_cost = 1e9
            for t, sc in cands:
                if t in used:
                    continue
                if sc < floor:
                    continue
                if sc < last + MIN_GAP:
                    continue
                cost = abs(sc - target)
                if cost < best_cost:
                    best_cost = cost
                    best = (t, sc)
            if best is None:
                for t, sc in cands:
                    if t in used:
                        continue
                    if sc < max(12, floor - 10):
                        continue
                    if sc < last + 0.2:
                        continue
                    cost = abs(sc - target)
                    if cost < best_cost:
                        best_cost = cost
                        best = (t, sc)
            if best is None:
                break
            new_hints.append(best[0])
            used.add(best[0])
            last = best[1]

        if len(new_hints) < 7:
            for t, _ in cands:
                if t not in used:
                    new_hints.append(t)
                    used.add(t)
                if len(new_hints) >= 7:
                    break

        if len(new_hints) < 7:
            fallback = CATEGORY_KEYWORDS.get(cat, []) + old_hints
            for t in fallback:
                if valid(t, ans) and t not in used:
                    new_hints.append(t)
                    used.add(t)
                if len(new_hints) >= 7:
                    break

        new_hints = new_hints[:7]
        if len(new_hints) == 7 and new_hints != old_hints[:7]:
            item['hints'] = new_hints
            changed += 1

    PUZZLES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    report = {
        'changed': changed,
        'items': len(data),
        'model': MODEL_PATH,
        'calibration': str(CALIB_PATH),
    }
    out = Path('tmp/hints_repair_v28_strict_report.json')
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'changed={changed} items={len(data)}')
    print(f'written={PUZZLES_PATH}')
    print(f'report={out}')


if __name__ == '__main__':
    main()
