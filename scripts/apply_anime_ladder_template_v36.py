from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from hint_quality_v29_common import detect_cross_domain, normalize_hint


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


def best_sequence(
    candidates: list[tuple[str, float]],
    answer: str,
    targets: list[float],
) -> tuple[list[str], list[float]]:
    n = len(candidates)
    k = 7
    inf = 1e18

    dp = [[inf] * n for _ in range(k)]
    prev = [[-1] * n for _ in range(k)]

    for i in range(n):
        name, score = candidates[i]
        penalty = 5.0 if name == answer else 0.0
        dp[0][i] = abs(score - targets[0]) + penalty

    for t in range(1, k):
        best_val = inf
        best_idx = -1
        for i in range(n):
            if dp[t - 1][i] < best_val:
                best_val = dp[t - 1][i]
                best_idx = i
            name, score = candidates[i]
            penalty = 0.0
            if name == answer and t < 6:
                penalty = 8.0
            cur = best_val + abs(score - targets[t]) + penalty
            dp[t][i] = cur
            prev[t][i] = best_idx

    end = min(range(n), key=lambda i: dp[k - 1][i])
    idxs = [end]
    for t in range(k - 1, 0, -1):
        idxs.append(prev[t][idxs[-1]])
    idxs.reverse()

    names = [candidates[i][0] for i in idxs]
    scores = [candidates[i][1] for i in idxs]

    used = set()
    out_names: list[str] = []
    out_scores: list[float] = []
    for i, name in enumerate(names):
        if name in used:
            continue
        used.add(name)
        out_names.append(name)
        out_scores.append(scores[i])

    if len(out_names) < 7:
        for name, sc in candidates:
            if name in used:
                continue
            used.add(name)
            out_names.append(name)
            out_scores.append(sc)
            if len(out_names) == 7:
                break

    return out_names[:7], out_scores[:7]


def run_apply(
    input_path: Path,
    pool_path: Path,
    model_path: str,
    calib_path: Path,
    out_dir: Path,
    apply: bool,
) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    pool_cfg = json.loads(pool_path.read_text(encoding="utf-8"))
    targets = [float(x) for x in pool_cfg.get("targets", [30, 40, 50, 60, 70, 80, 90])]
    tolerance = float(pool_cfg.get("tolerance", 10))
    levels = pool_cfg.get("levels", {})
    answer_templates = pool_cfg.get("answer_variants", ["{answer}"])

    base_pool = []
    for t in [30, 40, 50, 60, 70, 80, 90]:
        base_pool.extend(levels.get(str(t), []))
    base_pool = [normalize_hint(x) for x in base_pool if normalize_hint(x)]

    calib = json.loads(calib_path.read_text(encoding="utf-8"))
    x, y = calib["x_pred"], calib["y_calibrated"]

    anime_items = [it for it in data if it.get("category") == "动漫" and it.get("answer")]

    texts = []
    for it in anime_items:
        ans = str(it.get("answer", "")).strip()
        texts.append(ans)
        texts.extend([normalize_hint(h) for h in (it.get("hints") or [])[:7] if normalize_hint(h)])
        for tpl in answer_templates:
            texts.append(normalize_hint(str(tpl).replace("{answer}", ans)))
    texts.extend(base_pool)
    uniq = list(dict.fromkeys([t for t in texts if t]))

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    changed_items = 0
    within_count = 0
    details = []

    for it in data:
        if it.get("category") != "动漫" or not it.get("answer"):
            continue
        ans = str(it["answer"]).strip()
        ans_vec = emb[idx[ans]]

        cands = []
        cands.extend(base_pool)
        cands.extend([normalize_hint(h) for h in (it.get("hints") or [])[:7] if normalize_hint(h)])
        for tpl in answer_templates:
            cands.append(normalize_hint(str(tpl).replace("{answer}", ans)))

        seen = set()
        filtered = []
        for c in cands:
            if not c or c in seen:
                continue
            if detect_cross_domain("动漫", c):
                continue
            seen.add(c)
            filtered.append(c)

        score_map = {}
        for c in filtered:
            if c not in idx:
                continue
            raw = float(np.dot(ans_vec, emb[idx[c]]) * 100.0)
            score_map[c] = apply_calibration(raw, x, y)

        ranked = sorted(score_map.items(), key=lambda z: z[1])
        if len(ranked) < 7:
            continue

        new_hints, new_scores = best_sequence(ranked, ans, targets)
        if len(new_hints) < 7:
            continue

        old_hints = (it.get("hints") or [])[:7]
        if new_hints != old_hints:
            it["hints"] = new_hints
            changed_items += 1

        ok = len(new_scores) == 7 and all(abs(new_scores[i] - targets[i]) <= tolerance for i in range(7))
        if ok:
            within_count += 1

        details.append(
            {
                "answer": ans,
                "new_hints": new_hints,
                "new_scores": [round(v, 2) for v in new_scores],
                "within_tolerance": ok,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / "puzzles.anime_ladder_v36.json"
    report_path = out_dir / "anime_ladder_v36_report.json"
    detail_path = out_dir / "anime_ladder_v36_details.json"

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    snapshot.write_text(text, encoding="utf-8")
    if apply:
        input_path.write_text(text, encoding="utf-8")

    total = len(anime_items)
    report = {
        "input": str(input_path),
        "pool": str(pool_path),
        "apply": apply,
        "anime_total": total,
        "changed_items": changed_items,
        "targets": targets,
        "tolerance": tolerance,
        "within_tolerance_count": within_count,
        "within_tolerance_ratio": round(within_count / total, 4) if total else 0.0,
        "snapshot": str(snapshot),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "report": report,
        "report_path": str(report_path),
        "details_path": str(detail_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply anime ladder template v36")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--pool", default="data/anime_hint_ladder_pool_v36.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run_apply(
        input_path=Path(args.input),
        pool_path=Path(args.pool),
        model_path=args.model_path,
        calib_path=Path(args.calib_path),
        out_dir=Path(args.out_dir),
        apply=args.apply,
    )

    rpt = result["report"]
    print(
        f"anime_total={rpt['anime_total']} changed_items={rpt['changed_items']} "
        f"within={rpt['within_tolerance_count']} ratio={rpt['within_tolerance_ratio']}"
    )
    print(f"report={result['report_path']}")
    print(f"details={result['details_path']}")


if __name__ == "__main__":
    main()
