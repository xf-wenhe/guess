from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np

ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]


def resolve_device() -> str:
    override = os.getenv("SEM_DEVICE", "").strip().lower()
    if override:
        return override

    try:
        import torch
    except Exception:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def cosine_similarity(left, right) -> float:
    dot = float((left * right).sum())
    left_norm = float((left * left).sum()) ** 0.5
    right_norm = float((right * right).sum()) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / left_norm / right_norm


def apply_calibration(pred: float, x: list[float], y: list[float]) -> float:
    if pred <= x[0]:
        return float(y[0])
    if pred >= x[-1]:
        return float(y[-1])
    for i in range(len(x) - 1):
        left = float(x[i])
        right = float(x[i + 1])
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return float(y[i])
            t = (pred - left) / span
            return float(y[i] + (y[i + 1] - y[i]) * t)
    return pred


def load_calibration(path: Path) -> tuple[list[float], list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [float(v) for v in payload["x_pred"]], [float(v) for v in payload["y_calibrated"]]


def build_calibration(pred: list[float], target: list[float]) -> dict[str, list[float]]:
    pred_arr = np.array(pred, dtype=np.float32)
    target_arr = np.array(target, dtype=np.float32)
    order = np.argsort(pred_arr)
    pred_arr = pred_arr[order]
    target_arr = target_arr[order]

    x: list[float] = []
    y: list[float] = []
    n = len(pred_arr)
    n_bins = min(20, max(5, n // 2))
    for i in range(n_bins):
        left = int(i * n / n_bins)
        right = int((i + 1) * n / n_bins)
        if right <= left:
            continue
        x.append(float(np.mean(pred_arr[left:right])))
        y.append(float(np.mean(target_arr[left:right])))
    if not x:
        x = [0.0, 100.0]
        y = [0.0, 100.0]
    return {"x_pred": x, "y_calibrated": y}


def semantic_multi_angle(model, left: str, right: str) -> float:
    scores = []
    for angle in ANGLES:
        left_vec = model.encode([f"{angle}{left}"], normalize_embeddings=True)[0]
        right_vec = model.encode([f"{angle}{right}"], normalize_embeddings=True)[0]
        scores.append(cosine_similarity(left_vec, right_vec))
    scores.sort()
    trimmed = scores[1:-1] if len(scores) >= 3 else scores
    return sum(trimmed) / len(trimmed) * 100.0


def semantic_multi_angle_from_cache(
    cache: dict[tuple[str, str], object],
    left: str,
    right: str,
) -> float:
    scores = []
    for angle in ANGLES:
        scores.append(cosine_similarity(cache[(angle, left)], cache[(angle, right)]))
    scores.sort()
    trimmed = scores[1:-1] if len(scores) >= 3 else scores
    return sum(trimmed) / len(trimmed) * 100.0


def build_embedding_cache(model, rows: Iterable[tuple[str, str, float]], batch_size: int):
    unique_texts = sorted({text for pair in rows for text in pair[:2]})
    cache = {}
    for angle in ANGLES:
        encoded = model.encode(
            [f"{angle}{text}" for text in unique_texts],
            normalize_embeddings=True,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        for text, vec in zip(unique_texts, encoded):
            cache[(angle, text)] = vec
    return cache


def predict_scored_rows(rows: list[tuple[str, str, float]], cache) -> list[float]:
    return [semantic_multi_angle_from_cache(cache, left, right) for left, right, _ in rows]


def read_scored_rows(path: Path) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            answer = (row.get("answer") or "").strip()
            user_input = (row.get("user_input") or "").strip()
            raw_score = (row.get("score_0_100") or "").strip()
            if not answer or not user_input or not raw_score:
                continue
            try:
                score = float(raw_score)
            except ValueError:
                continue
            rows.append((answer, user_input, score))
    return rows


def score_bucket(score: float) -> str:
    if score < 20:
        return "0-20"
    if score < 40:
        return "20-40"
    if score < 60:
        return "40-60"
    if score < 80:
        return "60-80"
    return "80-100"


def metric(pred: list[float], target: list[float]) -> tuple[float, float]:
    n = len(pred)
    if n == 0:
        return 0.0, 0.0
    mae = float(np.mean(np.abs(np.array(pred) - np.array(target))))
    hit = sum(1 for p, t in zip(pred, target) if score_bucket(p) == score_bucket(t))
    return mae, hit / n * 100.0
