from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from hint_quality_v29_common import detect_cross_domain


GENERIC_TERMS = {"日常线索", "调查线索", "生活插曲"}
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


def has_overlap(answer: str, hint: str) -> bool:
    return bool({ch for ch in answer if ch.strip()} & {ch for ch in hint if ch.strip()})


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
    return all("\u4e00" <= ch <= "\u9fff" for ch in text)


def build_name_like(mapping: dict[str, list[str]]) -> set[str]:
    generic_markers = [
        "组织", "世界", "兵团", "学院", "学园", "计划", "高专", "王", "队", "团", "界", "城",
        "法", "术", "机动", "武魂", "魂环", "剑", "刀", "球", "赛", "改编", "国漫", "武侠",
        "番剧", "动画", "系列", "故事", "角色", "成长", "冲突", "设定", "电竞", "远航", "草帽",
        "忍者", "九尾", "巫女", "战国", "日轮", "柱级",
    ]
    out: set[str] = set()
    for hints in mapping.values():
        for raw in hints:
            hint = str(raw).strip()
            if not hint or not is_mostly_chinese(hint):
                continue
            if len(hint) < 2 or len(hint) > 4:
                continue
            if any(marker in hint for marker in generic_markers):
                continue
            out.add(hint)
    return out


def is_valid_hint(answer: str, hint: str, blocked_terms: set[str]) -> bool:
    if not hint or hint in blocked_terms or hint in META_TERMS:
        return False
    if has_overlap(answer, hint):
        return False
    if detect_cross_domain("动漫", hint):
        return False
    return True


def rank_candidates(
    answer: str,
    candidates: list[str],
    embeddings: np.ndarray,
    index_by_text: dict[str, int],
    x_pred: list[float],
    y_calibrated: list[float],
) -> list[tuple[float, str]]:
    answer_vec = embeddings[index_by_text[answer]]
    scored: list[tuple[float, str]] = []
    for hint in candidates:
        if hint not in index_by_text:
            continue
        score = float(np.dot(answer_vec, embeddings[index_by_text[hint]]) * 100.0)
        scored.append((apply_calibration(score, x_pred, y_calibrated), hint))
    scored.sort(key=lambda item: item[0])
    return scored


def pick_replacement(
    slot_index: int,
    used: set[str],
    ranked_candidates: list[tuple[float, str]],
    tone_pool: list[str],
    answer: str,
    target_curve: list[float],
    name_like_tokens: set[str],
    early_slot_keep: set[str],
    blocked_terms: set[str],
) -> str | None:
    target = float(target_curve[min(slot_index, len(target_curve) - 1)])
    scored_choices: list[tuple[float, str]] = []
    for score, hint in ranked_candidates:
        if hint in used:
            continue
        if not is_valid_hint(answer, hint, blocked_terms):
            continue
        if slot_index < 5 and hint in name_like_tokens and hint not in early_slot_keep:
            continue
        penalty = abs(score - target)
        if slot_index < 2 and score > 60:
            penalty += 12
        elif slot_index < 4 and score > 72:
            penalty += 8
        elif slot_index >= 5 and score < 55:
            penalty += 6
        scored_choices.append((penalty, hint))

    if scored_choices:
        scored_choices.sort(key=lambda item: (item[0], item[1]))
        return scored_choices[0][1]

    for hint in tone_pool:
        if hint in used:
            continue
        if slot_index < 5 and hint in name_like_tokens and hint not in early_slot_keep:
            continue
        if is_valid_hint(answer, hint, blocked_terms):
            return hint
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace generic anime daily clue terms with answer-specific hints")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--policy-file", default=DEFAULT_POLICY_FILE)
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--protect-passed-details", help="Path to anime guessability details JSON; passed answers in it will be left unchanged")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy_file).read_text(encoding="utf-8"))
    calib = json.loads(Path(args.calib_path).read_text(encoding="utf-8"))

    anime_template = policy.get("generic_slot_templates", {}).get("anime_rule2", {})
    blocked_terms = {
        str(value).strip()
        for value in anime_template.get("generic_blocklist", list(GENERIC_TERMS))
        if str(value).strip() in GENERIC_TERMS
    }
    tone_seed_pool = [
        str(value).strip()
        for value in anime_template.get("tone_seed_pool", ["同学伙伴", "学业烦恼", "家庭日常", "校园日常", "邻里生活", "日常困境", "上学路", "家庭趣事"])
        if str(value).strip()
    ]
    early_slot_keep = {
        str(value).strip()
        for value in anime_template.get("early_slot_keep", ["日本", "国漫"])
        if str(value).strip()
    }
    target_curve = [float(value) for value in policy.get("universal_constraints", {}).get("default_target_curve", [30, 40, 50, 60, 70, 80, 90])]

    anime_items = [item for item in data if item.get("category") == "动漫" and item.get("answer")]
    all_texts: list[str] = []
    for item in anime_items:
        all_texts.append(str(item.get("answer", "")).strip())
        all_texts.extend(str(h).strip() for h in (item.get("hints") or [])[:7] if str(h).strip())
    for hints in mapping.values():
        all_texts.extend(str(h).strip() for h in hints if str(h).strip())
    all_texts.extend(tone_seed_pool)
    unique_texts = list(dict.fromkeys(all_texts))

    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    embeddings = model.encode(unique_texts, normalize_embeddings=True, batch_size=256)
    index_by_text = {text: index for index, text in enumerate(unique_texts)}
    name_like_tokens = build_name_like(mapping)
    protected_answers: set[str] = set()
    if args.protect_passed_details:
        details = json.loads(Path(args.protect_passed_details).read_text(encoding="utf-8"))
        protected_answers = {
            str(item.get("answer", "")).strip()
            for item in details
            if item.get("pass") and str(item.get("answer", "")).strip()
        }

    changed_items = 0
    unresolved: list[str] = []
    replaced_slots = 0
    skipped_protected: list[str] = []

    for item in anime_items:
        answer = str(item.get("answer", "")).strip()
        if answer in protected_answers:
            skipped_protected.append(answer)
            continue
        hints = [str(h).strip() for h in (item.get("hints") or [])[:7]]
        generic_positions = [index for index, hint in enumerate(hints) if hint in blocked_terms]
        if not generic_positions:
            continue

        used = {hint for hint in hints if hint and hint not in blocked_terms}
        answer_candidates = []
        for raw in mapping.get(answer, []):
            hint = str(raw).strip()
            if not hint or hint in used or hint in answer_candidates:
                continue
            if not is_valid_hint(answer, hint, blocked_terms):
                continue
            answer_candidates.append(hint)
        ranked_candidates = rank_candidates(answer, answer_candidates, embeddings, index_by_text, calib["x_pred"], calib["y_calibrated"])

        updated = hints[:]
        for slot_index in generic_positions:
            replacement = pick_replacement(
                slot_index=slot_index,
                used=used,
                ranked_candidates=ranked_candidates,
                tone_pool=tone_seed_pool,
                answer=answer,
                target_curve=target_curve,
                name_like_tokens=name_like_tokens,
                early_slot_keep=early_slot_keep,
                blocked_terms=blocked_terms,
            )
            if replacement is None:
                unresolved.append(answer)
                continue
            updated[slot_index] = replacement
            used.add(replacement)
            replaced_slots += 1

        if any(hint in blocked_terms for hint in updated):
            unresolved.append(answer)
            continue

        if updated != hints:
            item["hints"] = updated
            changed_items += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "category": "动漫",
                "changed_items": changed_items,
                "replaced_slots": replaced_slots,
                "skipped_protected_answers": sorted(set(skipped_protected)),
                "unresolved_answers": sorted(set(unresolved)),
                "apply": bool(args.apply),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()