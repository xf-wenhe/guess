from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]

FIELDNAMES = [
    "id",
    "answer",
    "user_input",
    "answer_category",
    "input_category_guess",
    "relation_tag",
    "expected_range",
    "score_0_100",
    "reason",
    "reviewer",
]


def cosine_similarity(left, right):
    dot = float((left * right).sum())
    left_norm = float((left * left).sum()) ** 0.5
    right_norm = float((right * right).sum()) ** 0.5
    return 0.0 if left_norm == 0 or right_norm == 0 else dot / left_norm / right_norm


def load_calibration(path: Path) -> tuple[list[float], list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    x = [float(value) for value in payload["x_pred"]]
    y = [float(value) for value in payload["y_calibrated"]]
    return x, y


def apply_calibration(pred: float, x: list[float], y: list[float]) -> float:
    if pred <= x[0]:
        return y[0]
    if pred >= x[-1]:
        return y[-1]
    for index in range(len(x) - 1):
        left = x[index]
        right = x[index + 1]
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return y[index]
            ratio = (pred - left) / span
            return y[index] + (y[index + 1] - y[index]) * ratio
    return pred


def semantic_multi_angle(model: SentenceTransformer, answer: str, guess: str) -> float:
    scores = []
    for angle in ANGLES:
        answer_vec = model.encode([f"{angle}{answer}"], normalize_embeddings=True)[0]
        guess_vec = model.encode([f"{angle}{guess}"], normalize_embeddings=True)[0]
        scores.append(cosine_similarity(answer_vec, guess_vec))
    scores.sort()
    trimmed = scores[1:-1] if len(scores) >= 3 else scores
    return sum(trimmed) / len(trimmed) * 100.0


def build_embedding_cache(model: SentenceTransformer, pairs: list[tuple[str, str]]) -> dict[str, object]:
    cache: dict[str, object] = {}
    texts = sorted({text for pair in pairs for text in pair})
    for angle in ANGLES:
        prompts = [f"{angle}{text}" for text in texts]
        vectors = model.encode(prompts, normalize_embeddings=True)
        for text, vector in zip(texts, vectors):
            cache[f"{angle}{text}"] = vector
    return cache


def semantic_multi_angle_cached(answer: str, guess: str, cache: dict[str, object]) -> float:
    scores = []
    for angle in ANGLES:
        answer_vec = cache[f"{angle}{answer}"]
        guess_vec = cache[f"{angle}{guess}"]
        scores.append(cosine_similarity(answer_vec, guess_vec))
    scores.sort()
    trimmed = scores[1:-1] if len(scores) >= 3 else scores
    return sum(trimmed) / len(trimmed) * 100.0


def char_overlap(answer: str, guess: str) -> int:
    return len(set(answer) & set(guess))


def containment(answer: str, guess: str) -> bool:
    return answer in guess or guess in answer


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES + ["qc_status", "qc_reason", "qc_calibrated_score", "qc_shared_chars"])
        writer.writeheader()
        writer.writerows(rows)


def write_training_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def dedup_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for row in rows:
        key = ((row.get("answer") or "").strip(), (row.get("user_input") or "").strip())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        clean_row = {field: (row.get(field) or "").strip() for field in FIELDNAMES}
        result.append(clean_row)
    for index, row in enumerate(result, start=1):
        row["id"] = str(index)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Review hard negatives and merge clean rows into training candidates")
    parser.add_argument("--input", default="data/hard_negatives_from_guessability_v1.csv")
    parser.add_argument("--base", default="data/semantic_scoring_user_input_template.csv")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--calib-path", default="data/semantic_calibration_v27_semreal_anchor.json")
    parser.add_argument("--reviewed-out", default="data/hard_negatives_from_guessability_v1_reviewed.csv")
    parser.add_argument("--merged-out", default="data/semantic_scoring_user_input_template_plus_hard_negatives_v1.csv")
    parser.add_argument("--max-calibrated-keep", type=float, default=28.0)
    parser.add_argument("--min-calibrated-reject", type=float, default=36.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    base_path = Path(args.base)
    calib_path = Path(args.calib_path)
    rows = load_csv(input_path)
    base_rows = load_csv(base_path) if base_path.exists() else []
    calib_x, calib_y = load_calibration(calib_path)
    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)

    pair_texts = [((row.get("answer") or "").strip(), (row.get("user_input") or "").strip()) for row in rows]
    embedding_cache = build_embedding_cache(model, pair_texts)

    reviewed_rows: list[dict[str, str]] = []
    kept_rows: list[dict[str, str]] = []

    for row in rows:
        answer = (row.get("answer") or "").strip()
        guess = (row.get("user_input") or "").strip()
        shared_chars = char_overlap(answer, guess)
        raw_score = semantic_multi_angle_cached(answer, guess, embedding_cache)
        calibrated_score = apply_calibration(raw_score, calib_x, calib_y)

        qc_status = "keep"
        qc_reason = "passed_conservative_qc"
        if containment(answer, guess):
            qc_status = "reject"
            qc_reason = "title_containment"
        elif shared_chars >= 2:
            qc_status = "reject"
            qc_reason = "shared_chars_ge_2"
        elif calibrated_score >= args.min_calibrated_reject:
            qc_status = "reject"
            qc_reason = "calibrated_score_high"
        elif calibrated_score > args.max_calibrated_keep:
            qc_status = "reject"
            qc_reason = "calibrated_score_borderline"

        reviewed = {field: (row.get(field) or "").strip() for field in FIELDNAMES}
        reviewed["qc_status"] = qc_status
        reviewed["qc_reason"] = qc_reason
        reviewed["qc_calibrated_score"] = f"{calibrated_score:.2f}"
        reviewed["qc_shared_chars"] = str(shared_chars)
        reviewed_rows.append(reviewed)

        if qc_status == "keep":
            kept_rows.append(reviewed)

    reviewed_out = Path(args.reviewed_out)
    merged_out = Path(args.merged_out)
    write_csv(reviewed_out, reviewed_rows)

    merged_rows = dedup_rows(base_rows + kept_rows)
    write_training_csv(merged_out, merged_rows)

    summary = {
        "input_rows": len(rows),
        "kept_rows": len(kept_rows),
        "rejected_rows": len(rows) - len(kept_rows),
        "reviewed_out": str(reviewed_out),
        "merged_out": str(merged_out),
        "merged_total_rows": len(merged_rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
