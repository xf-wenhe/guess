from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from hint_quality_v29_common import detect_cross_domain, normalize_hint

GENERIC_META = {
    "语义指向", "信息指向", "场景线索", "关系脉络", "上下文脉络", "结构框架", "因果链条",
    "细节线索", "节奏推进", "关键特征", "层级递进", "语义线索", "核心线索", "关联线索",
    "补充线索", "延展线索", "语用自然", "语义锚点", "辨识稳定", "含义清楚", "语义连贯",
    "场景锚定", "核心语义", "核心属性", "关联明确", "关系连贯",
}

CATEGORY_POOL = {
    "美食": ["烤制火候", "食材搭配", "咸香口感", "炭火香气", "烹饪流程", "餐桌场景", "热食风味", "街头小吃", "鲜香层次"],
    "动漫": ["角色关系", "剧情推进", "世界设定", "关键桥段", "冲突主线", "作品风格", "热血对抗", "连载改编", "叙事节奏"],
    "游戏": ["玩法机制", "任务推进", "对局节奏", "角色成长", "资源管理", "操作反馈", "策略协作", "胜负目标", "副本挑战"],
    "生活": ["日常场景", "居家事务", "习惯养成", "实际操作", "生活流程", "场景应用", "效率改进", "家庭互动", "日常安排"],
    "情感": ["情绪变化", "关系波动", "心理反应", "触发情境", "行为外显", "关系走向", "内心体验", "共鸣感受", "价值认同"],
    "感情": ["相处细节", "情绪变化", "关系波动", "心理反应", "行为外显", "关系走向", "内心体验", "共鸣感受", "价值认同"],
    "神话": ["传说母题", "神祇体系", "典籍出处", "叙事原型", "仪式遗存", "故事流变", "象征意义", "角色冲突", "天地设定"],
    "宇宙": ["天体运行", "轨道参数", "观测方式", "空间尺度", "光谱特征", "引力作用", "星系结构", "物理机制", "深空观测"],
    "人物": ["时代背景", "关键事迹", "身份定位", "历史影响", "事件节点", "社会评价", "生平轨迹", "贡献评价", "史料记载"],
    "典故": ["历史出处", "故事脉络", "寓意指向", "典籍来源", "语义映射", "流传路径", "背景线索", "关键情节", "文化关联"],
    "成语": ["字面义项", "引申含义", "使用场景", "语用强度", "典故来源", "表达语气", "词义边界", "语法位置", "常用语境"],
    "歇后语": ["前后结构", "言外之意", "口语语感", "表达语气", "常见场景", "理解路径", "俗语风格", "双关意味", "收尾点题"],
    "歌手": ["音色特征", "演唱表现", "舞台风格", "作品路线", "听感辨识", "公开演出", "代表曲风", "情绪表达", "唱腔特色"],
    "歌曲": ["旋律线条", "节拍结构", "歌词意象", "编曲层次", "副歌记忆", "情绪推进", "听感特征", "乐句变化", "主题表达"],
    "风景": ["地貌特征", "空间层次", "光线变化", "季节差异", "环境氛围", "视觉焦点", "地域特性", "观赏角度", "现场体感"],
    "学习": ["知识体系", "理解过程", "练习路径", "应用验证", "复盘方法", "概念框架", "方法归纳", "训练巩固", "题型拆解"],
    "工作": ["任务分解", "协作流程", "执行节点", "交付标准", "职责边界", "项目推进", "沟通机制", "时间安排", "结果复盘"],
    "节日": ["节庆背景", "民俗活动", "时令特征", "仪式环节", "参与方式", "文化符号", "传统关联", "家庭团聚", "庆祝场景"],
    "旅游": ["路线规划", "目的地体验", "行程安排", "景点信息", "活动选择", "交通衔接", "在地文化", "出行准备", "旅行节奏"],
    "动作": ["动作过程", "执行方式", "发力路径", "姿态变化", "步骤衔接", "节奏控制", "结果反馈", "场景触发", "肢体协调"],
    "文化": ["历史传承", "民俗表达", "礼仪场景", "工艺特征", "审美风格", "地域文化", "叙事母题", "符号意涵", "仪式流程"],
    "学科": ["概念体系", "方法路径", "题型框架", "实验观察", "逻辑推演", "应用场景", "学习重点", "常见误区", "解题步骤"],
    "狼人杀": ["身份推理", "回合发言", "阵营博弈", "投票逻辑", "局势判断", "信息管理", "站边策略", "夜间信息", "发言链条"],
}


def apply_calibration(pred: float, x: list[float], y: list[float]) -> float:
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


def run_boost(input_path: Path, out_dir: Path, model_path: str, calib_path: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise SystemExit('invalid puzzles json: root must be list')

    calib = json.loads(calib_path.read_text(encoding='utf-8'))
    x, y = calib['x_pred'], calib['y_calibrated']

    texts = []
    for item in data:
        a = str(item.get('answer', '')).strip()
        if a:
            texts.append(a)
        for h in (item.get('hints') or []):
            hs = normalize_hint(h)
            if hs:
                texts.append(hs)
        for t in CATEGORY_POOL.get(str(item.get('category', '')).strip(), []):
            texts.append(t)

    uniq = list(dict.fromkeys(texts))
    model = SentenceTransformer(model_path, device='cpu', local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    changed_items = 0
    replaced_hints = 0

    for item in data:
        category = str(item.get('category', '')).strip()
        answer = str(item.get('answer', '')).strip()
        hints = [normalize_hint(h) for h in (item.get('hints') or []) if normalize_hint(h)][:7]
        if not answer or answer not in idx or len(hints) < 1:
            continue

        a_vec = emb[idx[answer]]
        scores = []
        for h in hints:
            if h in idx:
                sc = apply_calibration(float(np.dot(a_vec, emb[idx[h]]) * 100.0), x, y)
            else:
                sc = -1.0
            scores.append(sc)

        bad_idx = []
        for i, h in enumerate(hints):
            if h in GENERIC_META:
                bad_idx.append(i)
                continue
            if detect_cross_domain(category, h):
                bad_idx.append(i)
                continue
            if scores[i] < 18:
                bad_idx.append(i)

        if not bad_idx:
            continue

        used = set(hints)
        cands = []
        for t in CATEGORY_POOL.get(category, []):
            if t in used or t == answer:
                continue
            if t not in idx:
                continue
            sc = apply_calibration(float(np.dot(a_vec, emb[idx[t]]) * 100.0), x, y)
            cands.append((sc, t))
        cands.sort(key=lambda z: -z[0])

        new_hints = hints[:]
        cptr = 0
        touched = False
        for bi in bad_idx:
            while cptr < len(cands) and cands[cptr][1] in used:
                cptr += 1
            if cptr >= len(cands):
                break
            nh = cands[cptr][1]
            cptr += 1
            if nh != new_hints[bi]:
                used.discard(new_hints[bi])
                new_hints[bi] = nh
                used.add(nh)
                replaced_hints += 1
                touched = True

        if touched:
            item['hints'] = new_hints
            changed_items += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / 'puzzles.semantic_boosted.v30.json'
    report = out_dir / 'hints_semantic_boost_v30_report.json'
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    snapshot.write_text(text, encoding='utf-8')
    if apply:
        input_path.write_text(text, encoding='utf-8')

    rpt = {
        'input': str(input_path),
        'snapshot': str(snapshot),
        'apply': apply,
        'changed_items': changed_items,
        'replaced_hints': replaced_hints,
    }
    report.write_text(json.dumps(rpt, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'report': rpt, 'report_path': str(report)}


def main() -> None:
    parser = argparse.ArgumentParser(description='Boost hint semantic fit v30')
    parser.add_argument('--input', default='assets/puzzles.json')
    parser.add_argument('--out-dir', default='tmp')
    parser.add_argument('--model-path', default='models/bge-m3-finetuned-v27-semreal-anchor')
    parser.add_argument('--calib-path', default='data/semantic_calibration_v27_semreal_anchor.json')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    result = run_boost(Path(args.input), Path(args.out_dir), args.model_path, Path(args.calib_path), args.apply)
    rpt = result['report']
    print(f"changed_items={rpt['changed_items']} replaced_hints={rpt['replaced_hints']} apply={rpt['apply']}")
    print(f"report={result['report_path']}")


if __name__ == '__main__':
    main()
