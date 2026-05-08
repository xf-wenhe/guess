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


def main() -> None:
    parser = argparse.ArgumentParser(description="Reorder anime hints only by calibrated embedding score")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--policy-file", default="data/final_hint_policy_v1.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    calib = json.loads(Path(args.calib_path).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy_file).read_text(encoding="utf-8"))
    x = calib["x_pred"]
    y = calib["y_calibrated"]

    locked_answers: set[str] = set()
    for key, cfg in (policy.get("special_cases") or {}).items():
        if not str(key).startswith("动漫::"):
            continue
        if not bool((cfg or {}).get("locked")):
            continue
        _, _, ans = str(key).partition("::")
        ans = ans.strip()
        if ans:
            locked_answers.add(ans)

    texts: list[str] = []
    for item in data:
        if item.get("category") != "动漫":
            continue
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue
        texts.append(answer)
        for h in (item.get("hints") or [])[:7]:
            hs = str(h).strip()
            if hs:
                texts.append(hs)

    uniq = list(dict.fromkeys(texts))
    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    changed = 0
    touched = 0
    skipped_locked = 0

    for item in data:
        if item.get("category") != "动漫":
            continue

        answer = str(item.get("answer", "")).strip()
        hints = [str(h).strip() for h in (item.get("hints") or [])[:7]]
        if not answer or len(hints) < 2:
            continue

        if answer in locked_answers:
            skipped_locked += 1
            continue

        if answer not in idx:
            continue

        touched += 1
        a_vec = emb[idx[answer]]
        scored: list[tuple[float, str]] = []
        for h in hints:
            if h not in idx:
                continue
            score = float(np.dot(a_vec, emb[idx[h]]) * 100.0)
            score = apply_calibration(score, x, y)
            scored.append((score, h))

        if len(scored) < 2:
            continue

        old_hints = [h for _, h in scored]
        scored.sort(key=lambda z: z[0])
        new_hints = [h for _, h in scored]
        if old_hints != new_hints:
            item["hints"] = new_hints
            changed += 1

    output_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / "puzzles.anime_reordered_only_v1.json"
    report_path = out_dir / "anime_reorder_only_v1_report.json"
    snapshot.write_text(output_text, encoding="utf-8")

    if args.apply:
        input_path.write_text(output_text, encoding="utf-8")

    report = {
        "input": str(input_path),
        "snapshot": str(snapshot),
        "apply": bool(args.apply),
        "category": "动漫",
        "changed_items": changed,
        "touched_items": touched,
        "skipped_locked": skipped_locked,
        "locked_answers": sorted(locked_answers),
        "model_path": args.model_path,
        "calib_path": args.calib_path,
        "policy_file": args.policy_file,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False))
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
