from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from hint_quality_v29_common import detect_cross_domain


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

DEFAULT_POLICY_FILE = "data/final_hint_policy_v1.json"

CHINESE_ANIME = {
    "狐妖小红娘", "罗小黑战记", "刺客伍六七", "大鱼海棠", "白蛇缘起", "斗罗大陆", "斗破苍穹",
    "一人之下", "全职高手", "镇魂街", "不良人", "星游记", "灵笼", "喜羊羊", "熊出没",
    "秦时明月", "虹猫蓝兔", "画江湖",
}


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


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


def is_mostly_chinese(text: str) -> bool:
    if not text:
        return False
    for ch in text:
        if not ('\u4e00' <= ch <= '\u9fff'):
            return False
    return True


def build_name_like(mapping: dict) -> set[str]:
    generic_markers = [
        "组织", "世界", "兵团", "学院", "学园", "计划", "高专", "王", "队", "团", "界", "城",
        "法", "术", "机动", "武魂", "魂环", "剑", "刀", "球", "赛", "改编", "国漫", "武侠",
        "番剧", "动画", "系列", "故事", "角色", "成长", "冲突", "设定", "电竞", "远航", "草帽",
        "忍者", "九尾", "巫女", "战国", "日轮", "柱级",
    ]
    out: set[str] = set()
    for hints in mapping.values():
        for raw in hints:
            t = str(raw).strip()
            if not t:
                continue
            if not is_mostly_chinese(t):
                continue
            if len(t) < 2 or len(t) > 4:
                continue
            if any(m in t for m in generic_markers):
                continue
            out.add(t)
    return out


def is_valid_hint(answer: str, hint: str) -> bool:
    if not hint:
        return False
    if hint in META_TERMS:
        return False
    if has_overlap(answer, hint):
        return False
    if detect_cross_domain("动漫", hint):
        return False
    return True


def choose_non_duplicate(cands: list[str], used: set[str], answer: str) -> str | None:
    for c in cands:
        t = str(c).strip()
        if not t or t in used:
            continue
        if not is_valid_hint(answer, t):
            continue
        return t
    return None


def rotate_by_answer(answer: str, cands: list[str]) -> list[str]:
    if not cands:
        return []
    k = sum(ord(ch) for ch in answer) % len(cands)
    return cands[k:] + cands[:k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Refill anime hints with rule2 style, keep Conan anchor")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--policy-file", default=DEFAULT_POLICY_FILE)
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy_file).read_text(encoding="utf-8"))
    calib = json.loads(Path(args.calib_path).read_text(encoding="utf-8"))
    x = calib["x_pred"]
    y = calib["y_calibrated"]

    anime_template = policy.get("generic_slot_templates", {}).get("anime_rule2", {})
    LOW_GENERIC_JP = [str(x).strip() for x in anime_template.get("low_generic_jp", ["日本", "动画作品"]) if str(x).strip()]
    LOW_GENERIC_CN = [str(x).strip() for x in anime_template.get("low_generic_cn", ["国漫", "动画作品"]) if str(x).strip()]
    MID_GENERIC = [str(x).strip() for x in anime_template.get("mid_generic", ["剧情推进", "角色关系", "世界设定", "群像叙事", "冒险主线", "成长变化"]) if str(x).strip()]
    FALLBACK = [str(x).strip() for x in anime_template.get("fallback", ["动画作品", "剧情推进", "角色关系", "世界设定", "成长变化", "冒险主线", "群像叙事"]) if str(x).strip()]
    TONE_SEED_POOL = [
        str(x).strip()
        for x in anime_template.get(
            "tone_seed_pool",
            ["同学伙伴", "学业烦恼", "家庭日常", "校园日常", "邻里生活", "日常困境", "上学路", "家庭趣事"],
        )
        if str(x).strip()
    ]
    GENERIC_BLOCKLIST = set(
        str(x).strip()
        for x in anime_template.get(
            "generic_blocklist",
            ["动画作品", "剧情推进", "角色关系", "世界设定", "群像叙事", "冒险主线", "成长变化", "番剧作品", "虚构故事", "长篇连载", "日常线索", "调查线索", "生活插曲"],
        )
        if str(x).strip()
    )
    TONE_LITERAL_BLOCKLIST = set(
        str(x).strip()
        for x in anime_template.get(
            "tone_literal_blocklist",
            ["博士", "变声器", "麻醉针", "米花町", "抽屉", "借物解困", "藤子不二雄"],
        )
        if str(x).strip()
    )
    EARLY_SLOT_KEEP = set(
        str(x).strip()
        for x in anime_template.get(
            "early_slot_keep",
            ["日本", "国漫"],
        )
        if str(x).strip()
    )
    special_cases = policy.get("special_cases", {})

    anime_items = [it for it in data if it.get("category") == "动漫" and it.get("answer")]
    answers = [str(it.get("answer", "")).strip() for it in anime_items]

    uniq_texts: list[str] = []
    for a in answers:
        uniq_texts.append(a)
    for hints in mapping.values():
        for h in hints[:7]:
            hs = str(h).strip()
            if hs:
                uniq_texts.append(hs)
    uniq = list(dict.fromkeys(uniq_texts))

    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    name_like = build_name_like(mapping)

    changed = 0
    missing_map: list[str] = []

    for item in anime_items:
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue

        special_key = f"动漫::{answer}"
        special_case = special_cases.get(special_key, {})
        special_hints = [str(x).strip() for x in special_case.get("hints", []) if str(x).strip()][:7]
        if special_case.get("locked") and len(special_hints) == 7:
            current_hints = [str(x).strip() for x in (item.get("hints") or [])]
            if current_hints != special_hints:
                item["hints"] = special_hints[:]
                changed += 1
            continue

        base = [str(x).strip() for x in mapping.get(answer, [])[:7] if str(x).strip()]
        if not base:
            missing_map.append(answer)
            base = []

        valid_base = []
        for h in base:
            if h in GENERIC_BLOCKLIST:
                continue
            if h in TONE_LITERAL_BLOCKLIST:
                continue
            if is_valid_hint(answer, h) and h not in valid_base:
                valid_base.append(h)

        if answer not in idx:
            continue

        a_vec = emb[idx[answer]]
        scored: list[tuple[float, str]] = []
        for h in valid_base:
            if h in idx:
                s = float(np.dot(a_vec, emb[idx[h]]) * 100.0)
                s = apply_calibration(s, x, y)
                scored.append((s, h))

        scored.sort(key=lambda z: z[0])
        ordered = [h for _, h in scored]
        mid_pool = [h for s, h in scored if 28.0 <= s <= 68.0]
        strong_desc = [h for _, h in sorted(scored, key=lambda z: z[0], reverse=True)]

        low = LOW_GENERIC_CN[:] if answer in CHINESE_ANIME else LOW_GENERIC_JP[:]
        used: set[str] = set()
        new_hints: list[str] = []

        # slot1-2: weak context
        for h in low:
            v = choose_non_duplicate([h], used, answer)
            if v is None:
                continue
            used.add(v)
            new_hints.append(v)

        tone_seed_rotated = rotate_by_answer(answer, TONE_SEED_POOL)

        # slot3-4: use Conan/Doraemon-like daily tone first, then mapped weak-mid anchors.
        for _ in range(2):
            v = choose_non_duplicate(tone_seed_rotated + mid_pool + ordered, used, answer)
            if v is None:
                break
            used.add(v)
            new_hints.append(v)

        # slot5: bridge from mid to strong anchors.
        if len(new_hints) < 5:
            v = choose_non_duplicate(mid_pool + ordered, used, answer)
            if v is not None:
                used.add(v)
                new_hints.append(v)

        # slot6-7: strongest mapped anchors placed at the tail.
        for _ in range(2):
            if len(new_hints) >= 7:
                break
            v = choose_non_duplicate(strong_desc, used, answer)
            if v is None:
                break
            used.add(v)
            new_hints.append(v)

        # Fill to 7 with remaining mapped and tone seeds, avoiding generic meta words.
        fillers = ordered + mid_pool + tone_seed_rotated + [h for h in MID_GENERIC if h not in GENERIC_BLOCKLIST]
        while len(new_hints) < 7:
            v = choose_non_duplicate(fillers, used, answer)
            if v is None:
                break
            if v in TONE_LITERAL_BLOCKLIST:
                continue
            used.add(v)
            new_hints.append(v)

        # Ensure exactly 7 with safe fallbacks (still filtered by generic blocklist).
        while len(new_hints) < 7:
            v = choose_non_duplicate([h for h in FALLBACK if h not in GENERIC_BLOCKLIST], used, answer)
            if v is None:
                break
            if v in TONE_LITERAL_BLOCKLIST:
                continue
            used.add(v)
            new_hints.append(v)

        new_hints = new_hints[:7]

        # Move name-like tokens to late slots when possible.
        for i in range(min(4, len(new_hints))):
            if new_hints[i] in EARLY_SLOT_KEEP:
                continue
            if new_hints[i] not in name_like:
                continue
            swap_idx = None
            for j in [4, 5, 6]:
                if j < len(new_hints) and new_hints[j] not in name_like and new_hints[j] not in EARLY_SLOT_KEEP:
                    swap_idx = j
                    break
            if swap_idx is not None:
                new_hints[i], new_hints[swap_idx] = new_hints[swap_idx], new_hints[i]

        if (item.get("hints") or [])[:7] != new_hints:
            item["hints"] = new_hints
            changed += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "category": "动漫",
                "changed_items": changed,
                "missing_map": sorted(set(missing_map)),
                "special_case_keys": sorted(special_cases.keys()),
                "policy_file": args.policy_file,
                "apply": bool(args.apply),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
