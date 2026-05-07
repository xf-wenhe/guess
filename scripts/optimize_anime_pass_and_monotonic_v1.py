from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


NOISY_TOKENS = {
    "家庭日常",
    "同学伙伴",
    "校园日常",
    "学业烦恼",
    "邻里生活",
    "日常困境",
    "日常线索",
    "调查线索",
    "生活插曲",
    "国漫",
}


def load_failed_answers(details_path: Path) -> set[str]:
    details = json.loads(details_path.read_text(encoding="utf-8"))
    return {
        str(x.get("answer", "")).strip()
        for x in details
        if not bool(x.get("pass")) and str(x.get("answer", "")).strip()
    }


def load_monotonic_answers(audit_details_path: Path) -> set[str]:
    payload = json.loads(audit_details_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("issues", payload.get("details", []))
    else:
        rows = []

    out: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("issue_type") != "monotonic_violation":
            continue
        if r.get("category") != "动漫":
            continue
        a = str(r.get("answer", "")).strip()
        if a:
            out.add(a)
    return out


def is_non_decreasing(vals: list[float]) -> bool:
    return all(vals[i] <= vals[i + 1] + 1e-9 for i in range(len(vals) - 1))


def bubble_monotonic(hints: list[str], sims: list[float]) -> tuple[list[str], int]:
    out_h = hints[:]
    out_s = sims[:]
    swaps = 0
    n = len(out_h)
    for _ in range(n):
        moved = False
        for i in range(n - 1):
            if out_s[i] > out_s[i + 1] + 1e-9:
                out_s[i], out_s[i + 1] = out_s[i + 1], out_s[i]
                out_h[i], out_h[i + 1] = out_h[i + 1], out_h[i]
                swaps += 1
                moved = True
        if not moved:
            break
    return out_h, swaps


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize anime pass rate and monotonic quality (targeted)")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--guess-details", default="tmp/xuanheng_r2_baseline_guess/anime_guessability_v1_details.json")
    parser.add_argument("--audit-details", default="tmp/xuanheng_r2_baseline_audit/hints_audit_v29_details.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--improve-threshold", type=float, default=0.02)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", default="tmp/optimize_anime_pass_and_monotonic_v1_preview.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    failed_answers = load_failed_answers(Path(args.guess_details))
    monotonic_answers = load_monotonic_answers(Path(args.audit_details))

    anime_items = [
        it
        for it in data
        if it.get("category") == "动漫"
        and isinstance(it.get("hints"), list)
        and len(it.get("hints")) >= 7
    ]

    texts: list[str] = []
    for it in anime_items:
        answer = str(it.get("answer", "")).strip()
        texts.append(answer)
        texts.extend([str(h).strip() for h in (it.get("hints") or [])[:7]])
        texts.extend([str(h).strip() for h in mapping.get(answer, [])[:7]])
    uniq = list(dict.fromkeys([x for x in texts if x]))

    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    failed_changed = 0
    failed_slots_replaced = 0
    monotonic_changed = 0
    monotonic_swaps = 0

    for it in anime_items:
        answer = str(it.get("answer", "")).strip()
        hints = [str(h).strip() for h in (it.get("hints") or [])[:7]]
        if len(hints) != 7 or answer not in idx:
            continue

        av = emb[idx[answer]]

        # Step 1: failed-only anchor enhancement and noisy replacement.
        if answer in failed_answers:
            base = [str(x).strip() for x in mapping.get(answer, [])[:7] if str(x).strip()]
            out = hints[:]
            local_replaced = 0

            # Replace explicit noisy tokens with answer-specific anchors.
            for i, h in enumerate(out):
                if h not in NOISY_TOKENS:
                    continue
                for cand in base:
                    if cand not in out:
                        out[i] = cand
                        local_replaced += 1
                        break

            # Replace the weakest hint once if an unused anchor gives clear gain.
            sims = [float(np.dot(av, emb[idx[h]])) if h in idx else -1.0 for h in out]
            low_i = int(np.argmin(np.array(sims)))
            low_sim = sims[low_i]
            best_cand = None
            best_gain = 0.0
            for cand in base:
                if cand in out or cand not in idx:
                    continue
                cand_sim = float(np.dot(av, emb[idx[cand]]))
                gain = cand_sim - low_sim
                if gain > best_gain:
                    best_gain = gain
                    best_cand = cand
            if best_cand and best_gain >= args.improve_threshold:
                out[low_i] = best_cand
                local_replaced += 1

            if out != hints:
                it["hints"] = out
                hints = out
                failed_changed += 1
                failed_slots_replaced += local_replaced

        # Step 2: monotonic-only minimal swap reorder.
        if answer in monotonic_answers:
            sims = [float(np.dot(av, emb[idx[h]])) if h in idx else -1.0 for h in hints]
            if not is_non_decreasing(sims):
                reordered, swaps = bubble_monotonic(hints, sims)
                if reordered != hints:
                    it["hints"] = reordered
                    monotonic_changed += 1
                    monotonic_swaps += swaps

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "input": str(input_path),
        "failed_answers": len(failed_answers),
        "monotonic_answers": len(monotonic_answers),
        "failed_changed_items": failed_changed,
        "failed_slots_replaced": failed_slots_replaced,
        "monotonic_changed_items": monotonic_changed,
        "monotonic_swaps": monotonic_swaps,
        "apply": bool(args.apply),
        "preview": str(out_path),
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
