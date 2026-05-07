from __future__ import annotations

import json
from pathlib import Path

from hint_quality_v29_common import CATEGORY_KEYWORDS, FALLBACK_HINTS

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

GENERIC_SLOT = {
    0: ["领域", "对象", "场景", "主题", "方向", "类别", "范式"],
    1: ["要素", "机制", "路径", "方式", "流程", "结构", "方法"],
    2: ["阶段", "变化", "过程", "关联", "影响", "趋势", "线索"],
    3: ["条件", "触发", "事件", "情境", "节点", "前置", "时机"],
    4: ["主体", "角色", "参与方", "执行方", "协作方", "对象方", "来源方"],
    5: ["地点", "区域", "空间", "位置", "方位", "现场", "范围"],
    6: ["结果", "状态", "终态", "反馈", "回合", "结局", "归位"],
}


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def candidate_pool(category: str, slot: int) -> list[str]:
    out: list[str] = []
    fb = FALLBACK_HINTS.get(category)
    if fb:
        out.extend(fb)
    kws = CATEGORY_KEYWORDS.get(category, [])
    out.extend([f"{k}语义" for k in kws])
    out.extend(GENERIC_SLOT.get(slot, []))
    out.extend([f"S{slot+1}提示", f"S{slot+1}线索", f"S{slot+1}锚点"])
    # keep order unique
    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def main() -> None:
    p = Path("assets/puzzles.json")
    data = json.loads(p.read_text(encoding="utf-8"))

    changed_items = 0
    replaced_hints = 0
    meta_replaced = 0

    for it in data:
        ans = str(it.get("answer", "")).strip()
        cat = str(it.get("category", "")).strip()
        hs = [str(h).strip() for h in (it.get("hints") or [])[:7]]
        if len(hs) != 7 or not ans:
            continue

        used = set(hs)
        local = False

        for i, h in enumerate(hs):
            need = (h in META_TERMS) or has_overlap(ans, h)
            if not need:
                continue

            repl = None
            for cand in candidate_pool(cat, i):
                if cand in used:
                    continue
                if cand in META_TERMS:
                    continue
                if has_overlap(ans, cand):
                    continue
                repl = cand
                break

            if repl is None:
                continue

            if h in META_TERMS:
                meta_replaced += 1
            used.discard(h)
            used.add(repl)
            hs[i] = repl
            replaced_hints += 1
            local = True

        if local:
            it["hints"] = hs
            changed_items += 1

    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed_items": changed_items,
        "replaced_hints": replaced_hints,
        "meta_replaced": meta_replaced,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
