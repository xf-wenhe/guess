from __future__ import annotations

import argparse
import json
from pathlib import Path

from hint_quality_v29_common import normalize_hint

GENERIC_META = {
    "核心语义",
    "信息聚焦",
    "语义锚点",
    "场景锚定",
    "辨识稳定",
    "含义清楚",
    "语义连贯",
    "核心属性",
    "关联明确",
    "语用自然",
    "关系连贯",
    "上下文连贯",
    "关系清楚",
    "功能描述",
    "过程阶段",
    "结构要素",
    "使用情境",
    "场景要素",
    "表达方式",
    "行为路径",
    "对象属性",
    "典型表现",
    "互动方式",
    "关系要点",
    "结果状态",
    "步骤衔接",
    "执行方式",
    "角色叙事",
    "剧情推进",
    "叙事节奏",
    "作品风格",
    "世界设定",
    "角色关系",
    "关键桥段",
    "冲突主线",
    "设定元素",
    "人物成长",
    "角色羁绊",
}

SAFE_BY_CATEGORY = {
    "游戏": ["玩法线索", "对局目标", "操作路径", "反馈机制", "进阶策略", "协作要点", "胜负条件"],
    "美食": ["风味线索", "口感描述", "食用场景", "制作步骤", "食材组合", "味型特征", "餐桌语境"],
    "动漫": ["剧情线索", "角色线索", "冲突关系", "叙事节点", "作品辨识", "情节转折", "人物动机"],
    "节日": ["节庆线索", "民俗活动", "时令背景", "仪式环节", "参与方式", "文化符号", "传统关联"],
    "宇宙": ["天文线索", "观测方式", "空间尺度", "运行现象", "科学解释", "研究证据", "宇宙背景"],
    "工作": ["任务线索", "协作环节", "执行节点", "交付标准", "职责边界", "流程节点", "结果导向"],
    "学习": ["学习线索", "理解过程", "练习路径", "知识应用", "能力目标", "复盘方法", "成长轨迹"],
    "旅游": ["出行线索", "路线规划", "在地体验", "行程安排", "场景感受", "目的地信息", "活动选择"],
    "生活": ["日常线索", "居家场景", "习惯养成", "操作步骤", "场景应用", "效率提升", "稳定实践"],
    "神话": ["传说线索", "神祇背景", "故事母题", "象征意涵", "角色冲突", "文化源流", "叙事结构"],
    "动作": ["动作线索", "发力路径", "姿态变化", "节奏控制", "动作过程", "结果反馈", "场景触发"],
    "感情": ["情绪线索", "关系变化", "触发情境", "心理反应", "行为外显", "状态演变", "关系走向"],
    "情感": ["情绪线索", "关系变化", "触发情境", "心理反应", "行为外显", "状态演变", "关系走向"],
    "狼人杀": ["发言线索", "身份博弈", "回合判断", "阵营策略", "投票逻辑", "信息博弈", "局势推进"],
    "人物": ["人物线索", "时代背景", "关键事迹", "身份定位", "贡献影响", "事件节点", "历史定位"],
    "典故": ["典故线索", "出处背景", "故事脉络", "寓意指向", "语义映射", "流传路径", "文化关联"],
    "歌手": ["演唱线索", "音色特征", "舞台表现", "作品风格", "听感辨识", "情绪表达", "代表作品"],
    "歌曲": ["旋律线索", "节拍结构", "歌词意象", "编曲层次", "副歌记忆", "情绪推进", "听感特征"],
    "风景": ["景观线索", "地貌特征", "空间层次", "视觉焦点", "季节变化", "环境氛围", "地域特性"],
    "成语": ["成语线索", "字面义项", "引申含义", "使用场景", "语用强度", "典故来源", "表达语气"],
    "歇后语": ["歇后语线索", "前后结构", "言外之意", "口语语感", "表达语气", "常见场景", "理解路径"],
}

FALLBACK = ["语义线索", "场景线索", "核心线索", "辨识线索", "关联线索", "补充线索", "延展线索"]


def pick_safe(category: str, used: set[str], i: int) -> str:
    pool = SAFE_BY_CATEGORY.get(category, FALLBACK) + FALLBACK
    for offset in range(len(pool)):
        cand = pool[(i + offset) % len(pool)]
        if cand not in used:
            return cand
    return pool[i % len(pool)]


def run_replace(input_path: Path, out_dir: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise SystemExit('invalid puzzles json: root must be list')

    changed_items = 0
    replaced_hints = 0

    for item in data:
        category = str(item.get('category', '')).strip()
        hints = [normalize_hint(h) for h in (item.get('hints') or []) if normalize_hint(h)]
        if not hints:
            continue
        used = set(hints)
        new_hints = []
        touched = False
        for i, h in enumerate(hints[:7]):
            if h in GENERIC_META:
                nh = pick_safe(category, set(new_hints), i)
                new_hints.append(nh)
                replaced_hints += 1
                touched = True
            else:
                new_hints.append(h)
        if new_hints != hints[:7]:
            item['hints'] = new_hints
            changed_items += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / 'puzzles.generic_meta_replaced.v30.json'
    report = out_dir / 'hints_generic_meta_replaced_v30_report.json'
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
    parser = argparse.ArgumentParser(description='Replace generic meta tokens v30')
    parser.add_argument('--input', default='assets/puzzles.json')
    parser.add_argument('--out-dir', default='tmp')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    result = run_replace(Path(args.input), Path(args.out_dir), args.apply)
    rpt = result['report']
    print(f"changed_items={rpt['changed_items']} replaced_hints={rpt['replaced_hints']} apply={rpt['apply']}")
    print(f"report={result['report_path']}")


if __name__ == '__main__':
    main()
