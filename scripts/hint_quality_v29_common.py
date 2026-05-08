from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

TARGETS = [30, 40, 50, 60, 70, 80, 90]

# These tokens are style/meta words and should not be used as semantic hints.
BANNED_EXACT = {
    "结构清晰",
    "逻辑完整",
    "表达精准",
    "细节到位",
    "节奏稳定",
    "信息明确",
    "语义明确",
    "特征明显",
    "层次分明",
    "语义聚焦",
    "场景具体",
    "脉络完整",
    "上下文关联",
}

BANNED_SUBSTRINGS = {
    "语境",
    "特征",
}

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "游戏": ["玩家", "操作", "对局", "关卡", "角色", "装备", "奖励", "匹配", "胜负", "副本", "技能"],
    "美食": ["食材", "口感", "烹饪", "香味", "甜", "咸", "辣", "主食", "小吃", "饮品"],
    "动漫": ["角色", "剧情", "连载", "番剧", "设定", "战斗", "冒险", "漫画"],
    "节日": ["节气", "民俗", "庆祝", "仪式", "习俗", "团聚", "时令"],
    "宇宙": ["天体", "轨道", "引力", "观测", "光谱", "星系", "宇宙"],
    "工作": ["岗位", "汇报", "项目", "协作", "流程", "绩效", "任务"],
    "学习": ["课程", "知识", "练习", "考试", "复习", "作业", "理解"],
    "旅游": ["出行", "目的地", "景点", "路线", "行程", "住宿", "游玩"],
    "生活": ["日常", "家庭", "清洁", "收纳", "习惯", "健康", "居家"],
    "风景": ["自然", "山川", "湖海", "地貌", "景观", "气候", "植被"],
    "神话": ["传说", "神祇", "法器", "异兽", "天界", "神力", "典籍"],
    "动作": ["姿态", "移动", "发力", "节奏", "步骤", "执行", "身体"],
    "成语": ["典故", "寓意", "比喻", "四字", "固定", "语义", "表达"],
}

DOMAIN_LEXICON: Dict[str, List[str]] = {
    "游戏": ["副本", "打野", "排位", "抽卡", "走位", "连击", "掉落", "开黑", "公会", "对局"],
    "美食": ["烹饪", "炖煮", "烧烤", "油炸", "口感", "咀嚼", "奶香", "辣味", "甜品", "出餐"],
    "动漫": ["番剧", "连载", "角色", "主线", "设定", "漫画", "声优", "名场面"],
    "节日": ["祭祀", "团圆", "节气", "民俗", "庆典", "习俗", "祈福", "时令"],
    "宇宙": ["轨道", "红移", "引力", "星系", "天体", "望远镜", "光谱", "潮汐"],
    "工作": ["汇报", "薪级", "交接", "绩效", "工单", "会议", "审批", "流程"],
    "学习": ["课堂", "复习", "试题", "记忆", "推导", "笔记", "考试", "习题"],
}

FALLBACK_HINTS: Dict[str, List[str]] = {
    "游戏": ["互动娱乐", "虚拟场景", "玩家操作", "任务推进", "角色成长", "策略协作", "胜负目标"],
    "美食": ["饮食文化", "食材处理", "烹饪步骤", "风味层次", "常见吃法", "口感表现", "餐桌场景"],
    "动漫": ["虚构作品", "角色关系", "故事推进", "世界设定", "关键冲突", "经典桥段", "粉丝认知"],
    "节日": ["传统时间", "节庆背景", "民俗活动", "仪式流程", "群体参与", "家庭团聚", "文化象征"],
    "宇宙": ["天文对象", "观测手段", "运动规律", "空间尺度", "物理机制", "科学解释", "研究证据"],
}


@dataclass
class HintIssue:
    index: int
    category: str
    answer: str
    hint_index: int
    hint: str
    issue_type: str
    detail: str


def normalize_hint(text: str) -> str:
    return str(text).strip().replace("\u3000", " ")


def is_meta_hint(text: str) -> Tuple[bool, str]:
    if text in BANNED_EXACT:
        return True, "banned_exact"
    for sub in BANNED_SUBSTRINGS:
        if sub in text:
            return True, f"banned_substring:{sub}"
    return False, ""


def strip_template_suffix(text: str) -> str:
    out = text
    if out.endswith("语境") and len(out) > 2:
        out = out[:-2]
    if out.endswith("特征") and len(out) > 2:
        out = out[:-2]
    return out.strip()


def semantic_progress_score(answer: str, category: str, hint: str) -> float:
    # Lightweight heuristic score for monotonic checks without external model dependency.
    a_chars = set(answer)
    h_chars = set(hint)
    overlap = len(a_chars.intersection(h_chars))

    cat_hit = 0
    for token in CATEGORY_KEYWORDS.get(category, []):
        if token in hint:
            cat_hit += 1

    length_score = min(len(hint), 8) / 8.0
    return overlap * 2.0 + cat_hit * 1.5 + length_score


def detect_cross_domain(category: str, hint: str) -> List[Tuple[str, str]]:
    hits: List[Tuple[str, str]] = []
    for domain, words in DOMAIN_LEXICON.items():
        if domain == category:
            continue
        for word in words:
            if word in hint:
                hits.append((domain, word))
                break
    return hits


def dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def top_counter(counter: Counter, n: int = 30) -> List[Tuple[str, int]]:
    return sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:n]


def monotonic_violations(scores: Sequence[float]) -> List[Tuple[int, float, float]]:
    violations: List[Tuple[int, float, float]] = []
    for i in range(len(scores) - 1):
        if scores[i + 1] + 1e-6 < scores[i]:
            violations.append((i, scores[i], scores[i + 1]))
    return violations
