from __future__ import annotations

import argparse
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

GENERIC = [
    "番剧作品",
    "虚构故事",
    "系列作品",
    "角色互动",
    "情节推进",
    "成长变化",
    "设定要素",
]

NAME_LIKE = {
    "鸣人", "佐助", "路飞", "索隆", "一护", "悟空", "戈薇", "柯南", "樱木", "小丸子", "小新", "大雄",
    "亚古兽", "星矢", "月野兔", "武藤", "浦饭", "银时", "纳兹", "桐人", "埼玉", "金木", "小杰", "夏尔",
    "艾伦", "炭治郎", "虎杖", "日向", "龙马", "夏目", "面码", "千寻", "琪琪", "泷", "阳菜", "铃芽",
    "苏苏", "小黑", "伍六七", "椿", "小白", "唐三", "萧炎", "叶修", "曹焱兵", "马克", "喜羊羊", "光头强",
}


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix anime guessability v40")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--details", default="tmp/anime_ladder_v40_guessability_reordered/anime_guessability_v1_details.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    strong_map = json.loads(Path(args.map).read_text(encoding="utf-8"))
    details = json.loads(Path(args.details).read_text(encoding="utf-8"))

    fail_answers = {d.get("answer") for d in details if not bool(d.get("pass"))}

    changed = 0
    for it in data:
        if it.get("category") != "动漫":
            continue
        ans = str(it.get("answer", "")).strip()
        if not ans or ans == "名侦探柯南" or ans not in fail_answers:
            continue

        strong = [str(x).strip() for x in strong_map.get(ans, []) if str(x).strip()]
        if not strong:
            continue

        seed = sum(ord(ch) for ch in ans)
        g1 = GENERIC[seed % len(GENERIC)]
        g2 = GENERIC[(seed + 2) % len(GENERIC)]
        g3 = GENERIC[(seed + 4) % len(GENERIC)]

        used = {g1, g2, g3}
        out = [g1, g2, g3]
        name_count = 0

        for h in strong:
            if len(out) == 7:
                break
            if h in used:
                continue
            if h in META_TERMS:
                continue
            if has_overlap(ans, h):
                continue
            if h in NAME_LIKE and name_count >= 1:
                continue
            out.append(h)
            used.add(h)
            if h in NAME_LIKE:
                name_count += 1

        if len(out) < 7:
            for g in GENERIC:
                if len(out) == 7:
                    break
                if g in used:
                    continue
                out.append(g)
                used.add(g)

        if len(out) == 7 and (it.get("hints") or [])[:7] != out:
            it["hints"] = out
            changed += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"changed_items": changed, "failed_answers": len(fail_answers), "apply": bool(args.apply)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
