from __future__ import annotations

import argparse
import json
import math
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


def softmax(scores: np.ndarray, temperature: float) -> np.ndarray:
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    z = scores / temperature
    z = z - np.max(z)
    e = np.exp(z)
    return e / np.sum(e)


def run_score(
    input_path: Path,
    category: str,
    model_path: str,
    out_dir: Path,
    calib_path: Path | None,
    temperature: float,
) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    subset = [
        it
        for it in data
        if str(it.get("category", "")).strip() == category
        and str(it.get("answer", "")).strip()
        and isinstance(it.get("hints"), list)
        and len(it.get("hints")) >= 7
    ]

    answers = [str(it.get("answer", "")).strip() for it in subset]
    hints_by_answer = {
        str(it.get("answer", "")).strip(): [str(h).strip() for h in it.get("hints", [])[:7]]
        for it in subset
    }

    guess_queries = {
        a: " ".join([category, *hints_by_answer[a]])
        for a in answers
    }

    per_hint_queries = {}
    for a in answers:
        for idx, h in enumerate(hints_by_answer[a], start=1):
            per_hint_queries[(a, idx)] = " ".join([category, h])

    texts = list(dict.fromkeys([
        *answers,
        *[h for hs in hints_by_answer.values() for h in hs],
        *guess_queries.values(),
        *per_hint_queries.values(),
    ]))

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(texts, normalize_embeddings=True, batch_size=256)
    idx_map = {t: i for i, t in enumerate(texts)}

    cal_x: list[float] | None = None
    cal_y: list[float] | None = None
    if calib_path and calib_path.exists():
        calib = json.loads(calib_path.read_text(encoding="utf-8"))
        x = calib.get("x_pred")
        y = calib.get("y_calibrated")
        if isinstance(x, list) and isinstance(y, list) and len(x) >= 2 and len(y) >= 2:
            cal_x = x
            cal_y = y

    ans_mat = np.stack([emb[idx_map[a]] for a in answers], axis=0)

    details = []
    top1_correct = 0
    for a in answers:
        a_vec = emb[idx_map[a]]
        q_vec = emb[idx_map[guess_queries[a]]]
        sims = ans_mat @ q_vec
        probs = softmax(sims, temperature=temperature)
        rank = np.argsort(-sims)
        pred = answers[int(rank[0])]
        if pred == a:
            top1_correct += 1

        hint_rows = []
        for i, h in enumerate(hints_by_answer[a], start=1):
            h_vec = emb[idx_map[h]]
            raw = float(np.dot(a_vec, h_vec) * 100.0)
            cal = apply_calibration(raw, cal_x, cal_y) if cal_x and cal_y else raw

            qh_vec = emb[idx_map[per_hint_queries[(a, i)]]]
            raw_ch = float(np.dot(a_vec, qh_vec) * 100.0)
            cal_ch = apply_calibration(raw_ch, cal_x, cal_y) if cal_x and cal_y else raw_ch

            hint_rows.append(
                {
                    "slot": i,
                    "hint": h,
                    "semantic_raw_percent": round(raw, 4),
                    "semantic_calibrated_percent": round(cal, 4),
                    "category_hint_raw_percent": round(raw_ch, 4),
                    "category_hint_calibrated_percent": round(cal_ch, 4),
                }
            )

        details.append(
            {
                "category": category,
                "answer": a,
                "guess_query": guess_queries[a],
                "pred_top1": pred,
                "pred_top3": [answers[int(i)] for i in rank[:3]],
                "true_answer_probability_percent": round(float(probs[answers.index(a)]) * 100.0, 4),
                "top1_similarity": round(float(sims[rank[0]]) * 100.0, 4),
                "hint_scores": hint_rows,
            }
        )

    report = {
        "input": str(input_path),
        "category": category,
        "total": len(answers),
        "top1_correct": top1_correct,
        "top1_ratio": round(top1_correct / len(answers), 4) if answers else 0.0,
        "model_path": model_path,
        "calib_path": str(calib_path) if calib_path else "",
        "temperature": temperature,
        "note": "true_answer_probability_percent is softmax over same-category answer set using query=category+all_7_hints",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    rp = out_dir / "category_semantic_guess_v1_report.json"
    dp = out_dir / "category_semantic_guess_v1_details.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dp.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"report": report, "report_path": str(rp), "details_path": str(dp)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score per-hint semantics and per-answer guess probability in a category")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--category", required=True)
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--temperature", type=float, default=0.08)
    args = parser.parse_args()

    calib_path = Path(args.calib_path) if args.calib_path.strip() else None
    out = run_score(
        input_path=Path(args.input),
        category=args.category,
        model_path=args.model_path,
        out_dir=Path(args.out_dir),
        calib_path=calib_path,
        temperature=args.temperature,
    )
    r = out["report"]
    print(f"category={r['category']} total={r['total']} top1_correct={r['top1_correct']} top1_ratio={r['top1_ratio']}")
    print(f"report={out['report_path']}")
    print(f"details={out['details_path']}")


if __name__ == "__main__":
    main()