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


def choose_for_slot(
    answer: str,
    ans_vec: np.ndarray,
    candidates: list[str],
    target: float,
    used: set[str],
    emb_map: dict[str, np.ndarray],
    x: list[float],
    y: list[float],
    min_score: float,
) -> tuple[str, float]:
    scored = []
    for c in candidates:
        if c in used:
            continue
        if has_overlap(answer, c):
            continue
        vec = emb_map.get(c)
        if vec is None:
            continue
        raw = float(np.dot(ans_vec, vec) * 100.0)
        s = apply_calibration(raw, x, y)
        scored.append((c, s, abs(s - target)))

    if not scored:
        return "", min_score

    feasible = [t for t in scored if t[1] + 1e-6 >= min_score]
    base = feasible if feasible else scored
    base.sort(key=lambda x: (x[2], -x[1]))
    c, s, _ = base[0]
    return c, s


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply game ladder template v1")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--pool", default="data/game_hint_ladder_pool_v1.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    pool = json.loads(Path(args.pool).read_text(encoding="utf-8"))
    calib = json.loads(Path(args.calib_path).read_text(encoding="utf-8"))

    category = str(pool.get("category", "游戏"))
    targets = [float(t) for t in pool.get("targets", [30, 40, 50, 60, 70, 80, 90])]
    levels = pool.get("levels", {})

    subset = [it for it in data if it.get("category") == category and it.get("answer")]

    all_text = []
    for it in subset:
        all_text.append(str(it.get("answer", "")).strip())
    for k in ["30", "40", "50", "60", "70", "80", "90"]:
        all_text.extend([str(x).strip() for x in levels.get(k, [])])

    uniq = list(dict.fromkeys([t for t in all_text if t]))
    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    emb_map = {t: emb[i] for i, t in enumerate(uniq)}

    x, y = calib["x_pred"], calib["y_calibrated"]

    changed = 0
    details = []
    for it in subset:
        ans = str(it.get("answer", "")).strip()
        ans_vec = emb_map.get(ans)
        if ans_vec is None:
            continue

        used = set()
        new_hints = []
        scores = []
        prev = -1e9
        for i, target in enumerate(targets):
            key = str(int(target))
            cands = [str(x).strip() for x in levels.get(key, [])]
            picked, score = choose_for_slot(
                answer=ans,
                ans_vec=ans_vec,
                candidates=cands,
                target=target,
                used=used,
                emb_map=emb_map,
                x=x,
                y=y,
                min_score=prev,
            )
            if not picked:
                picked = f"槽位{i+1}提示"
                score = prev
            used.add(picked)
            new_hints.append(picked)
            scores.append(round(score, 2))
            prev = max(prev, score)

        if (it.get("hints") or [])[:7] != new_hints:
            it["hints"] = new_hints
            changed += 1

        details.append({
            "answer": ans,
            "hints": new_hints,
            "scores": scores,
        })

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "game_ladder_v1_report.json"
    details_path = out_dir / "game_ladder_v1_details.json"
    report = {
        "category": category,
        "total": len(subset),
        "changed_items": changed,
        "targets": targets,
        "apply": bool(args.apply),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    details_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False))
    print(f"report={report_path}")
    print(f"details={details_path}")


if __name__ == "__main__":
    main()
