from __future__ import annotations

import argparse
import json
from pathlib import Path

from hint_quality_v29_common import dedupe_keep_order, is_meta_hint, normalize_hint, strip_template_suffix

CATEGORY_CONFIG = {
    "动作": {
        "base": ["身体行为", "动作过程", "执行方式"],
        "keywords": ["移动", "发力", "节奏", "姿态", "起跳", "转身", "步伐", "平衡", "手势"],
        "fallback": ["动作目的", "场景触发", "结果反馈", "细节差异"],
    },
    "感情": {
        "base": ["心理状态", "情绪变化", "关系体验"],
        "keywords": ["想念", "依赖", "失落", "甜蜜", "疏离", "矛盾", "心动", "愧疚", "释怀"],
        "fallback": ["触发事件", "内心反应", "行为表现", "关系走向"],
    },
    "情感": {
        "base": ["心理状态", "情绪变化", "关系体验"],
        "keywords": ["想念", "依赖", "失落", "甜蜜", "疏离", "矛盾", "心动", "愧疚", "释怀"],
        "fallback": ["触发事件", "内心反应", "行为表现", "关系走向"],
    },
    "狼人杀": {
        "base": ["桌游对抗", "身份推理", "回合发言"],
        "keywords": ["预言家", "女巫", "猎人", "投票", "查验", "出局", "悍跳", "金水", "警徽"],
        "fallback": ["阵营博弈", "信息管理", "发言逻辑", "局势判断"],
    },
    "神话": {
        "base": ["古代传说", "神祇体系", "超凡能力"],
        "keywords": ["神祇", "法器", "异兽", "天界", "祭祀", "神力", "封印", "典籍", "传承"],
        "fallback": ["故事背景", "角色冲突", "象征意义", "文化母题"],
    },
    "旅游": {
        "base": ["出行活动", "目的地探索", "在地体验"],
        "keywords": ["景点", "行程", "路线", "住宿", "交通", "打卡", "导览", "门票", "徒步"],
        "fallback": ["时间安排", "场景感受", "活动选择", "旅行反馈"],
    },
    "生活": {
        "base": ["日常事务", "居家场景", "习惯管理"],
        "keywords": ["清洁", "收纳", "通勤", "饮食", "作息", "采购", "家务", "健康", "社交"],
        "fallback": ["操作步骤", "效率提升", "场景应用", "稳定习惯"],
    },
    "工作": {
        "base": ["职场任务", "流程协作", "结果交付"],
        "keywords": ["汇报", "项目", "审批", "会议", "排期", "交接", "绩效", "工单", "复盘"],
        "fallback": ["职责分工", "执行节奏", "沟通方式", "达成标准"],
    },
    "学习": {
        "base": ["知识获取", "练习巩固", "能力提升"],
        "keywords": ["课程", "笔记", "复习", "考试", "错题", "推导", "记忆", "练习", "方法"],
        "fallback": ["输入阶段", "理解过程", "应用验证", "长期积累"],
    },
    "歌手": {
        "base": ["音乐艺人", "演唱表达", "舞台呈现"],
        "keywords": ["嗓音", "音色", "唱腔", "专辑", "巡演", "live", "编曲", "高音", "代表作"],
        "fallback": ["作品风格", "听感辨识", "表演特点", "受众认知"],
    },
    "歌曲": {
        "base": ["音乐作品", "旋律结构", "情绪传达"],
        "keywords": ["副歌", "主歌", "节拍", "旋律", "编曲", "歌词", "hook", "和声", "前奏"],
        "fallback": ["听感记忆", "主题意象", "结构推进", "传播场景"],
    },
    "人物": {
        "base": ["历史人物", "时代背景", "关键事迹"],
        "keywords": ["朝代", "生平", "政治", "军事", "思想", "著作", "改革", "典故", "影响"],
        "fallback": ["身份定位", "事件节点", "贡献评价", "后世影响"],
    },
    "典故": {
        "base": ["历史出处", "故事线索", "寓意表达"],
        "keywords": ["出处", "典籍", "人物", "事件", "演化", "比喻", "寓意", "流传", "语源"],
        "fallback": ["语义指向", "使用语境", "文化背景", "现代映射"],
    },
    "风景": {
        "base": ["自然景观", "地貌特征", "环境感受"],
        "keywords": ["山川", "湖海", "峡谷", "植被", "气候", "云海", "地形", "观景", "季节"],
        "fallback": ["空间层次", "视觉焦点", "旅行体验", "地域特性"],
    },
    "成语": {
        "base": ["固定词组", "典故来源", "比喻含义"],
        "keywords": ["四字", "寓意", "用法", "语义", "场景", "出处", "褒贬", "惯用", "表达"],
        "fallback": ["字面解释", "引申义项", "应用场景", "语用强度"],
    },
    "歇后语": {
        "base": ["俗语表达", "前后结构", "言外之意"],
        "keywords": ["前句", "后句", "双关", "比喻", "口语", "民间", "俚语", "语感", "机锋"],
        "fallback": ["表达场景", "语气效果", "理解路径", "常见用法"],
    },
}

LOW_INFO = {
    "一个人", "传统", "童年", "天才", "巨人", "雨天", "深渊", "目的地", "表面起伏", "鼻子发酸", "用户要", "办理交接", "薪级上调",
}


def clean_hint(text: str, answer: str) -> str:
    out = strip_template_suffix(normalize_hint(text))
    if not out or out == answer:
        return ""
    bad, _ = is_meta_hint(out)
    if bad or out in LOW_INFO:
        return ""
    if len(out) < 2 or len(out) > 10:
        return ""
    return out


def build_tail(category: str, answer: str, old_hints: list[str]) -> list[str]:
    cfg = CATEGORY_CONFIG[category]
    keywords = cfg["keywords"]

    scored = []
    for h in old_hints:
        c = clean_hint(h, answer)
        if not c:
            continue
        score = 0
        for kw in keywords:
            if kw in c:
                score += 2
        score += min(len(set(c).intersection(set(answer))), 2)
        scored.append((score, c))

    scored.sort(key=lambda x: (-x[0], x[1]))
    selected = dedupe_keep_order([h for _, h in scored])[:4]
    for fb in cfg["fallback"]:
        if fb not in selected and fb != answer:
            selected.append(fb)
        if len(selected) >= 4:
            break
    return selected[:4]


def run_rewrite(input_path: Path, out_dir: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    changed = 0
    touched = {k: [] for k in CATEGORY_CONFIG}

    out = []
    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        new_item = dict(item)
        if category in CATEGORY_CONFIG and answer:
            base = CATEGORY_CONFIG[category]["base"]
            old_hints = [normalize_hint(h) for h in (item.get("hints") or []) if normalize_hint(h)]
            tail = build_tail(category, answer, old_hints)
            new_hints = base + tail
            if new_hints != old_hints[:7]:
                changed += 1
                touched[category].append(answer)
            new_item["hints"] = new_hints
        out.append(new_item)

    output_text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / "puzzles.priority_rewrite.v29.json"
    report = out_dir / "hints_priority_rewrite_v29_report.json"
    snapshot.write_text(output_text, encoding="utf-8")
    if apply:
        input_path.write_text(output_text, encoding="utf-8")

    report_data = {
        "input": str(input_path),
        "snapshot": str(snapshot),
        "apply": apply,
        "changed_items": changed,
        "touched": {k: sorted(set(v)) for k, v in touched.items()},
    }
    report.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": report_data, "report_path": str(report)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite priority categories hints v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run_rewrite(Path(args.input), Path(args.out_dir), args.apply)
    rpt = result["report"]
    print(f"changed_items={rpt['changed_items']} apply={rpt['apply']}")
    print(f"report={result['report_path']}")


if __name__ == "__main__":
    main()
