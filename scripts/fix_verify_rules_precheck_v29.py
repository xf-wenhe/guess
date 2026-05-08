from __future__ import annotations

import json
import re
from pathlib import Path

PUZZLES = Path("assets/puzzles.json")
MANAGED = {"人物", "成语", "歇后语", "学科", "文化", "风景", "典故"}
DIGIT_RE = re.compile(r"\d")

# Keep phrase length in [4, 8] for managed NL categories.
BASE_POOL = {
    "人物": [
        "史册留名", "朝代更迭", "文脉承续", "政局转折", "家国担当", "学术建树", "风骨流传", "笔墨神采",
        "生涯跌宕", "思想激荡", "功业昭彰", "名望所归", "志向高远", "境遇多舛", "心志坚定", "德行可鉴",
    ],
    "歇后语": [
        "口传俗谈", "俚语妙喻", "机锋短句", "双关诙谐", "后句点题", "前句铺垫", "听感顺口", "语势轻快",
        "民间巧思", "笑点暗藏", "比拟鲜活", "表达生动", "场景贴近", "叙述利落", "言外有意", "语气俏皮",
    ],
    "典故": [
        "旧闻重述", "史事回响", "朝堂风云", "前因后果", "局势骤变", "谋略交锋", "关键转折", "文献可稽",
        "源流分明", "意旨深远", "叙事紧凑", "寓意绵长", "沿革可考", "背景厚重", "时代切片", "史笔凝练",
    ],
    "成语": [
        "字义凝练", "修辞有力", "语气鲜明", "典源可考", "语法稳定", "书面常见", "引申明晰", "语意周全",
        "搭配得当", "表达紧凑", "比拟准确", "使用广泛", "句式规整", "文脉连贯", "寓意清楚", "意象丰富",
    ],
    "学科": [
        "概念框架", "推导步骤", "实验观察", "方法归纳", "题型拆解", "逻辑演绎", "课程讲授", "训练巩固",
        "范围界定", "误区规避", "要点提炼", "模型构建", "思维迁移", "知识整合", "系统梳理", "应用实践",
    ],
    "文化": [
        "礼俗传承", "工艺流变", "审美形态", "器物风格", "地域印记", "节令氛围", "传统再现", "仪式表达",
        "舞台呈现", "叙事母题", "集体记忆", "风尚延续", "脉络清楚", "样式多元", "手作精神", "文脉积淀",
    ],
    "风景": [
        "峰岭叠映", "云影流转", "湖光潋滟", "林海起伏", "峡谷深邃", "天际辽阔", "晨昏交替", "气象万千",
        "层峦绵延", "色彩递进", "空间纵深", "视野开阔", "季候变化", "地势蜿蜒", "清风拂面", "光线柔和",
    ],
}

COMBO_PARTS = {
    # avoid category chars for each category
    "人物": (
        ["史册", "朝代", "文脉", "政局", "家国", "学术", "风骨", "笔墨", "志节", "德行", "功业", "名望", "行旅", "心志", "师承", "流派", "政见", "家学", "文风", "传记"],
        ["留痕", "流传", "回响", "昭著", "可鉴", "长存", "隽永", "深刻", "厚重", "清晰", "延续", "可循", "有据", "有序", "成章", "可考", "可述", "可述", "可辨", "可感"],
    ),
    "歇后语": (
        ["口传", "俚谈", "机锋", "双关", "前句", "后句", "民间", "笑点", "比拟", "短句", "听感", "收尾", "梗味", "转折", "俗谈", "妙喻", "即兴", "口彩", "连说", "话头"],
        ["顺口", "生动", "传神", "俏皮", "利落", "有趣", "鲜活", "贴切", "紧凑", "明快", "稳妥", "醒目", "响亮", "逗趣", "风趣", "轻巧", "顺滑", "贴地", "灵动", "通透"],
    ),
    "典故": (
        ["旧闻", "史事", "朝堂", "前因", "后果", "谋略", "转折", "文献", "源流", "背景", "沿革", "叙事", "掌故", "典籍", "政争", "兵略", "门第", "往闻", "轶闻", "旧章"],
        ["可考", "可溯", "深远", "厚重", "分明", "紧凑", "清楚", "完整", "有据", "有源", "连贯", "周密", "可述", "可辨", "成章", "成脉", "成体系", "有理", "有序", "有本"],
    ),
    "成语": (
        ["字义", "修辞", "语气", "典源", "语法", "引申", "搭配", "句式", "意象", "表达", "比拟", "书面", "文脉", "格律", "义理", "语态", "体例", "范式", "辞采", "文势"],
        ["凝练", "有力", "鲜明", "稳健", "明晰", "准确", "规整", "周全", "丰富", "紧凑", "得当", "常见", "贴切", "清楚", "精当", "顺畅", "严谨", "有序", "统一", "完整"],
    ),
    "学科": (["概念", "推导", "实验", "方法", "题型", "逻辑", "课堂", "训练", "范围", "误区", "模型", "应用"], ["框架", "步骤", "观察", "归纳", "拆解", "演绎", "讲授", "巩固", "界定", "规避", "构建", "实践"]),
    "文化": (["礼俗", "工艺", "审美", "器物", "地域", "节令", "传统", "仪式", "舞台", "母题", "风尚", "文脉"], ["传承", "流变", "形态", "风格", "印记", "氛围", "再现", "表达", "呈现", "延续", "积淀", "清晰"]),
    "风景": (["峰岭", "云影", "湖光", "林海", "峡谷", "天际", "晨昏", "气象", "层峦", "色彩", "空间", "季候"], ["叠映", "流转", "潋滟", "起伏", "深邃", "辽阔", "交替", "万千", "绵延", "递进", "纵深", "变化"]),
}


def valid_hint(cat: str, ans: str, hint: str, used_local: set[str], used_cat: set[str]) -> bool:
    h = str(hint).strip()
    if not h:
        return False
    if h in used_local or h in used_cat:
        return False
    if "向" in h:
        return False
    if DIGIT_RE.search(h):
        return False
    if any(ch in h for ch in cat if ch.strip()):
        return False
    if any(ch in h for ch in ans if ch.strip()):
        return False
    if len(h) < 4 or len(h) > 8:
        return False
    if "线索" in h:
        return False
    return True


def candidate_stream(cat: str):
    for x in BASE_POOL.get(cat, []):
        yield x
    left, right = COMBO_PARTS.get(cat, ([], []))
    for a in left:
        for b in right:
            s = a + b
            if 4 <= len(s) <= 8:
                yield s


def pick_hint(cat: str, ans: str, used_local: set[str], used_cat: set[str], seed_i: int) -> str:
    cands = list(candidate_stream(cat))
    if not cands:
        return "语义聚焦"
    start = (sum(ord(ch) for ch in (cat + ans)) + seed_i * 17) % len(cands)
    for off in range(len(cands)):
        cand = cands[(start + off) % len(cands)]
        if valid_hint(cat, ans, cand, used_local, used_cat):
            return cand
    # last resort: deterministic CJK-only unique token in valid length and no digits
    stems = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸", "乾", "坤", "震", "巽", "坎", "离", "艮", "兑"]
    marks = ["清", "正", "和", "雅", "静", "明", "远", "厚", "真", "朴", "谨", "畅", "稳", "锐", "新", "恒", "卓", "宁"]
    for i in range(len(stems) * len(marks)):
        s = stems[(seed_i + i) % len(stems)]
        m = marks[(seed_i * 3 + i) % len(marks)]
        cand = f"语义{s}{m}"
        if valid_hint(cat, ans, cand, used_local, used_cat):
            return cand
    return "语义雅正"


def main() -> None:
    arr = json.loads(PUZZLES.read_text(encoding="utf-8"))
    changed = 0
    replaced = 0

    used_by_category = {c: set() for c in MANAGED}

    for item in arr:
        cat = str(item.get("category", "")).strip()
        if cat not in MANAGED:
            continue
        ans = str(item.get("answer", "")).strip()
        old = [str(h).strip() for h in (item.get("hints") or [])]
        if len(old) < 7:
            old += [""] * (7 - len(old))
        old = old[:7]

        new_hints: list[str] = []
        local_used: set[str] = set()
        cat_used = used_by_category[cat]

        for i, h in enumerate(old):
            if valid_hint(cat, ans, h, local_used, cat_used):
                picked = h
            else:
                picked = pick_hint(cat, ans, local_used, cat_used, i)
                replaced += 1
            new_hints.append(picked)
            local_used.add(picked)
            cat_used.add(picked)

        if new_hints != old:
            item["hints"] = new_hints
            changed += 1

    PUZZLES.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"changed_items={changed}")
    print(f"replaced_hints={replaced}")


if __name__ == "__main__":
    main()
