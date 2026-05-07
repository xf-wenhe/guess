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


def has_adjacent_lexical_collision(hints: list[str]) -> bool:
    for i in range(len(hints) - 1):
        a = hints[i].strip()
        b = hints[i + 1].strip()
        if not a or not b:
            continue
        if a == b:
            return True
        if a in b or b in a:
            return True
    return False


def run_validation(
    input_path: Path,
    rules_path: Path,
    model_path: str,
    calib_path: Path,
    out_dir: Path,
) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    calib = json.loads(calib_path.read_text(encoding="utf-8"))

    category = str(rules.get("category", "动漫"))
    targets = [float(x) for x in rules.get("targets", [30, 40, 50, 60, 70, 80, 90])]
    tolerance = float(rules.get("tolerance", 10))
    checks = rules.get("checks", {})
    enforce_target_band = bool(checks.get("enforce_target_band", True))

    x, y = calib["x_pred"], calib["y_calibrated"]

    subset = [it for it in data if it.get("category") == category and it.get("answer")]

    texts = []
    for it in subset:
        ans = str(it.get("answer", "")).strip()
        texts.append(ans)
        texts.extend([str(h).strip() for h in (it.get("hints") or [])[:7]])
    uniq = list(dict.fromkeys([t for t in texts if t]))

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    details = []
    pass_count = 0

    for it in subset:
        ans = str(it.get("answer", "")).strip()
        hints = [str(h).strip() for h in (it.get("hints") or [])[:7]]

        if len(hints) != 7 or ans not in idx:
            details.append(
                {
                    "answer": ans,
                    "pass": False,
                    "reason": "shape_or_embedding_missing",
                    "hints": hints,
                }
            )
            continue

        ans_vec = emb[idx[ans]]
        scores = []
        for h in hints:
            if h not in idx:
                scores.append(-1.0)
                continue
            raw = float(np.dot(ans_vec, emb[idx[h]]) * 100.0)
            scores.append(apply_calibration(raw, x, y))

        checks_result = {
            "targets_within_tolerance": all(abs(scores[i] - targets[i]) <= tolerance for i in range(7)),
            "monotonic_non_decreasing": all(scores[i + 1] + 1e-6 >= scores[i] for i in range(6)),
            "slot1_max": scores[0] <= float(checks.get("slot1_max", 45)),
            "slot2_max": scores[1] <= float(checks.get("slot2_max", 55)),
            "slot7_min": scores[6] >= float(checks.get("slot7_min", 80)),
            "adjacent_lexical_diversity": not has_adjacent_lexical_collision(hints),
            "exact_duplicate_forbidden": len(set(hints)) == len(hints),
        }

        enabled = {
            k: bool(checks.get(k, True))
            for k in [
                "monotonic_non_decreasing",
                "adjacent_lexical_diversity",
                "exact_duplicate_forbidden",
            ]
        }

        final_pass = checks_result["slot1_max"] and checks_result["slot2_max"] and checks_result["slot7_min"]
        if enforce_target_band:
            final_pass = final_pass and checks_result["targets_within_tolerance"]
        for k, on in enabled.items():
            if on:
                final_pass = final_pass and checks_result[k]

        if final_pass:
            pass_count += 1

        details.append(
            {
                "answer": ans,
                "hints": hints,
                "scores": [round(s, 2) for s in scores],
                "checks": checks_result,
                "pass": final_pass,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "input": str(input_path),
        "category": category,
        "total": len(subset),
        "passed": pass_count,
        "pass_ratio": round(pass_count / len(subset), 4) if subset else 0.0,
        "rules": str(rules_path),
        "enforce_target_band": enforce_target_band,
        "model_path": model_path,
        "calib_path": str(calib_path),
    }
    report_path = out_dir / "anime_ladder_acceptance_v37_report.json"
    details_path = out_dir / "anime_ladder_acceptance_v37_details.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    details_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "report": report,
        "report_path": str(report_path),
        "details_path": str(details_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate anime ladder acceptance rules v37")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--rules", default="data/anime_ladder_acceptance_rules_v37.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--out-dir", default="tmp")
    args = parser.parse_args()

    result = run_validation(
        input_path=Path(args.input),
        rules_path=Path(args.rules),
        model_path=args.model_path,
        calib_path=Path(args.calib_path),
        out_dir=Path(args.out_dir),
    )
    r = result["report"]
    print(f"category={r['category']} total={r['total']} passed={r['passed']} ratio={r['pass_ratio']}")
    print(f"report={result['report_path']}")
    print(f"details={result['details_path']}")


if __name__ == "__main__":
    main()
