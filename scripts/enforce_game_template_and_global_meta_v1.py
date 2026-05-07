from __future__ import annotations

import json
from pathlib import Path

META_TERMS = {
    "标志性冲突",
    "代表性设定",
    "核心母题",
    "高光桥段",
    "知名剧情节点",
    "粉丝高共识",
    "答案锁定线索",
    "唯一锚点",
    "终局指向",
    "强辨识设定",
}

GAME_TEMPLATE = [
    "异象",
    "技能",
    "重新开始",
    "死亡后",
    "牧师",
    "墓地",
    "状态重置",
]

GENERIC_BY_SLOT = {
    0: ["领域", "对象", "场景", "主题", "范畴", "方向", "范式"],
    1: ["要素", "能力", "机制", "路径", "形式", "模式", "方法"],
    2: ["过程", "变化", "阶段", "线索", "关联", "趋势", "影响"],
    3: ["条件", "情境", "触发", "事件", "前置", "时机", "节点"],
    4: ["角色", "主体", "参与者", "执行者", "对象方", "协作方", "来源方"],
    5: ["位置", "区域", "地点", "空间", "方位", "现场", "范围"],
    6: ["结果", "状态", "反馈", "回合", "结局", "终态", "归位"],
}


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


p = Path("assets/puzzles.json")
arr = json.loads(p.read_text(encoding="utf-8"))

changed_items = 0
meta_replaced = 0

game_items = 0
for it in arr:
    if it.get("category") == "游戏":
        game_items += 1
        if it.get("hints") != GAME_TEMPLATE:
            it["hints"] = GAME_TEMPLATE[:]
            changed_items += 1

for it in arr:
    ans = str(it.get("answer", "")).strip()
    hs = [str(h).strip() for h in (it.get("hints") or [])]
    if len(hs) != 7:
        continue

    used = set(hs)
    local = False
    for i, h in enumerate(hs):
        if h not in META_TERMS:
            continue
        replacement = None
        for cand in GENERIC_BY_SLOT.get(i, []):
            if cand in used:
                continue
            if has_overlap(ans, cand):
                continue
            replacement = cand
            break
        if replacement is None:
            replacement = f"槽位{i+1}提示"
        used.discard(h)
        used.add(replacement)
        hs[i] = replacement
        meta_replaced += 1
        local = True

    if local:
        it["hints"] = hs
        changed_items += 1

p.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({
    "game_items": game_items,
    "changed_items": changed_items,
    "meta_replaced": meta_replaced
}, ensure_ascii=False))
