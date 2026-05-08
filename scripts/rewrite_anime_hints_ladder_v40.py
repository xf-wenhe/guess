from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


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


def has_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def is_name_like(hint: str, name_like_tokens: set[str]) -> bool:
    return hint in name_like_tokens


def pick_sequence(
    answer: str,
    targets: list[float],
    candidates: list[tuple[str, float]],
    name_like_tokens: set[str],
    max_name_tokens_per_item: int,
    forbid_name_tokens_before_slot: int,
) -> list[str]:
    used: set[str] = set()
    out: list[str] = []
    prev = -1e9
    name_count = 0

    for slot_i, tgt in enumerate(targets, start=1):
        feasible: list[tuple[float, float, str]] = []
        backup: list[tuple[float, float, str]] = []

        for hint, score in candidates:
            if hint in used:
                continue
            name_like = is_name_like(hint, name_like_tokens)
            if name_like and slot_i < forbid_name_tokens_before_slot:
                continue
            if name_like and name_count >= max_name_tokens_per_item:
                continue

            dist = abs(score - tgt)
            item = (dist, -score, hint)
            backup.append(item)
            if score + 1e-6 >= prev:
                feasible.append(item)

        pool = feasible if feasible else backup
        if not pool:
            out.append(f"动漫线索{slot_i}")
            continue

        pool.sort()
        picked = pool[0][2]
        used.add(picked)
        out.append(picked)

        score_map = {h: s for h, s in candidates}
        prev = max(prev, score_map.get(picked, prev))
        if is_name_like(picked, name_like_tokens):
            name_count += 1

    return out[:7]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite anime hints with semantic ladder v40")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--rules", default="data/anime_ladder_rules_v40.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    calib = json.loads(Path(args.calib_path).read_text(encoding="utf-8"))

    category = str(rules.get("category", "动漫"))
    targets = [float(x) for x in rules.get("targets", [30, 40, 50, 60, 70, 80, 90])]
    max_name_tokens_per_item = int(rules.get("max_name_tokens_per_item", 1))
    forbid_name_tokens_before_slot = int(rules.get("forbid_name_tokens_before_slot", 6))
    forbidden_meta_terms = {str(x).strip() for x in rules.get("forbidden_meta_terms", []) if str(x).strip()}
    name_like_tokens = {str(x).strip() for x in rules.get("name_like_tokens", []) if str(x).strip()}
    generic_low = [str(x).strip() for x in rules.get("generic_low", []) if str(x).strip()]
    generic_mid = [str(x).strip() for x in rules.get("generic_mid", []) if str(x).strip()]
    anchor_keep_answer = str(rules.get("anchor_keep_answer", "名侦探柯南")).strip()
    anchor_keep_hints = [str(x).strip() for x in rules.get("anchor_keep_hints", [])[:7]]

    subset = [it for it in data if it.get("category") == category and it.get("answer")]

    texts: list[str] = []
    for it in subset:
        ans = str(it.get("answer", "")).strip()
        if ans:
            texts.append(ans)
        texts.extend([str(h).strip() for h in (it.get("hints") or [])[:7] if str(h).strip()])
    texts.extend(generic_low)
    texts.extend(generic_mid)
    uniq = list(dict.fromkeys(texts))

    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    x = calib["x_pred"]
    y = calib["y_calibrated"]

    changed = 0
    for it in subset:
        ans = str(it.get("answer", "")).strip()
        old_hints = [str(h).strip() for h in (it.get("hints") or [])[:7]]

        if ans == anchor_keep_answer and len(anchor_keep_hints) == 7:
            new_hints = anchor_keep_hints[:]
            if new_hints != old_hints:
                it["hints"] = new_hints
                changed += 1
            continue

        ans_vec = emb[idx[ans]]

        candidate_raw = generic_low + generic_mid + old_hints
        seen: set[str] = set()
        filtered: list[str] = []
        for h in candidate_raw:
            hs = str(h).strip()
            if not hs:
                continue
            if hs in seen:
                continue
            if hs in forbidden_meta_terms:
                continue
            if has_overlap(ans, hs):
                continue
            seen.add(hs)
            filtered.append(hs)

        scored: list[tuple[str, float]] = []
        for h in filtered:
            if h not in idx:
                continue
            raw = float(np.dot(ans_vec, emb[idx[h]]) * 100.0)
            score = apply_calibration(raw, x, y)
            scored.append((h, score))

        scored.sort(key=lambda z: z[1])
        if len(scored) < 7:
            new_hints = old_hints
        else:
            new_hints = pick_sequence(
                answer=ans,
                targets=targets,
                candidates=scored,
                name_like_tokens=name_like_tokens,
                max_name_tokens_per_item=max_name_tokens_per_item,
                forbid_name_tokens_before_slot=forbid_name_tokens_before_slot,
            )

        if len(new_hints) == 7 and new_hints != old_hints:
            it["hints"] = new_hints
            changed += 1

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"category": category, "total": len(subset), "changed_items": changed, "apply": bool(args.apply)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
