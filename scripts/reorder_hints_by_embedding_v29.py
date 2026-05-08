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


def run_reorder(input_path: Path, out_dir: Path, model_path: str, calib_path: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    calib = json.loads(calib_path.read_text(encoding="utf-8"))
    x = calib["x_pred"]
    y = calib["y_calibrated"]

    texts = []
    for item in data:
        answer = str(item.get("answer", "")).strip()
        if answer:
            texts.append(answer)
        for h in (item.get("hints") or []):
            hs = str(h).strip()
            if hs:
                texts.append(hs)
    uniq = list(dict.fromkeys(texts))

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    changed = 0
    for item in data:
        answer = str(item.get("answer", "")).strip()
        hints = [str(h).strip() for h in (item.get("hints") or []) if str(h).strip()]
        if not answer or len(hints) < 2 or answer not in idx:
            continue
        a_vec = emb[idx[answer]]

        scored = []
        for h in hints[:7]:
            if h not in idx:
                continue
            score = float(np.dot(a_vec, emb[idx[h]]) * 100.0)
            score = apply_calibration(score, x, y)
            scored.append((score, h))

        if len(scored) < 2:
            continue

        old = [h for _, h in scored]
        scored.sort(key=lambda z: z[0])
        new_hints = [h for _, h in scored]
        if old != new_hints:
            changed += 1
            item["hints"] = new_hints

    output_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "puzzles.hints_reordered.v29.json"
    report_path = out_dir / "hints_reorder_v29_report.json"

    snapshot_path.write_text(output_text, encoding="utf-8")
    if apply:
        input_path.write_text(output_text, encoding="utf-8")

    report = {
        "input": str(input_path),
        "snapshot": str(snapshot_path),
        "apply": apply,
        "changed_items": changed,
        "model_path": model_path,
        "calib_path": str(calib_path),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "report": report,
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reorder hints by calibrated embedding score v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--apply", action="store_true", help="overwrite input file")
    args = parser.parse_args()

    result = run_reorder(
        Path(args.input),
        Path(args.out_dir),
        args.model_path,
        Path(args.calib_path),
        args.apply,
    )
    report = result["report"]
    print(
        "changed_items={changed_items} apply={apply} model={model_path}".format(
            **report
        )
    )
    print(f"report={result['report_path']}")


if __name__ == "__main__":
    main()
