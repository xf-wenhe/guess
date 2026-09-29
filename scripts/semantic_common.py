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


def apply_global_calibration(pred: float, calibration: dict[str, object]) -> float:
    """Apply the deployable global curve without using a known relation label."""
    x = calibration.get("x_pred")
    y = calibration.get("y_calibrated")
    if not isinstance(x, list) or not isinstance(y, list):
        raise ValueError("calibration must contain x_pred and y_calibrated lists")
    return apply_calibration(
        float(pred),
        [float(item) for item in x],
        [float(item) for item in y],
    )


def apply_relation_calibration(
    pred: float,
    calibration: dict[str, object],
    relation: str | None = None,
) -> float:
    """Apply an optional relation-specific calibration profile.

    The default curve remains global. A profile may provide its own curve and
    an output band, which is applied only when the caller identifies that
    relation; this prevents a midpoint antonym rule from remapping unrelated
    same-category or hard-negative rows at the same raw score.
    """
    active = calibration
    if relation:
        profiles = calibration.get("relation_calibrations")
        if isinstance(profiles, dict):
            profile = profiles.get(relation)
            if isinstance(profile, dict):
                active = profile

    value = apply_global_calibration(pred, active)

    target_low = active.get("target_low")
    target_high = active.get("target_high")
    if target_low is None and target_high is None:
        return value
    if target_low is None or target_high is None:
        raise ValueError("calibration profile target_low and target_high must be paired")
    target_low = float(target_low)
    target_high = float(target_high)
    if not np.isfinite(target_low) or not np.isfinite(target_high) or target_low > target_high:
        raise ValueError("calibration profile target band is invalid")
    return max(target_low, min(target_high, value))


def load_calibration(path: Path) -> tuple[list[float], list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [float(v) for v in payload["x_pred"]], [float(v) for v in payload["y_calibrated"]]


def build_calibration(
    pred: list[float],
    target: list[float],
    weights: list[float] | None = None,
) -> dict[str, list[float]]:
    method = os.getenv("SEM_CALIBRATION_METHOD", "isotonic").strip().lower()
    if method in {"legacy", "bucket_mean", "quantile_mean"}:
        return build_quantile_mean_calibration(pred, target, weights)
    if method != "isotonic":
        raise ValueError(f"unsupported SEM_CALIBRATION_METHOD={method!r}")
    return build_isotonic_calibration(pred, target, weights)


def constrain_calibration_interval(
    calibration: dict[str, object],
    lower: float,
    upper: float,
    target_low: float,
    target_high: float,
) -> dict[str, object]:
    """Keep a raw-score interval inside a relation-specific target band.

    Midpoint calibration rows are sparse, so weighted isotonic regression can
    still rise above the target band between two knots. Insert the observed
    midpoint neighborhood boundaries and clip only that interval. The
    cumulative maximum preserves the monotonic contract required by the
    interpolating calibrator; it does not inspect holdout rows.
    """
    x = [float(value) for value in calibration.get("x_pred", [])]
    y = [float(value) for value in calibration.get("y_calibrated", [])]
    if not x or len(x) != len(y):
        raise ValueError("calibration must contain equally sized non-empty x_pred/y_calibrated")
    if any(not np.isfinite(value) for value in (*x, *y)):
        raise ValueError("calibration curve must contain only finite values")

    lower = float(lower)
    upper = float(upper)
    target_low = float(target_low)
    target_high = float(target_high)
    if not all(np.isfinite(value) for value in (lower, upper, target_low, target_high)):
        raise ValueError("calibration interval bounds must be finite")
    if lower > upper:
        raise ValueError("calibration interval lower bound must not exceed upper bound")
    if target_low > target_high:
        raise ValueError("calibration target lower bound must not exceed upper bound")

    # Predictions are defined on the semantic 0-100 domain. Clamping the
    # inserted knots prevents an extrapolation-only boundary from changing
    # scores outside that domain.
    lower = max(0.0, min(100.0, lower))
    upper = max(0.0, min(100.0, upper))
    target_low = max(0.0, min(100.0, target_low))
    target_high = max(0.0, min(100.0, target_high))

    if any(left > right for left, right in zip(x, x[1:])):
        raise ValueError("calibration x_pred must be sorted")

    knots = sorted(set((*x, lower, upper)))
    raw_values = [apply_calibration(value, x, y) for value in knots]
    bounded_values: list[float] = []
    for knot, value in zip(knots, raw_values):
        if knot < lower:
            bounded_values.append(min(value, target_high))
        elif knot <= upper:
            bounded_values.append(max(target_low, min(target_high, value)))
        else:
            bounded_values.append(max(value, target_low))

    # The input is normally isotonic already. This final projection also
    # keeps the helper safe for legacy quantile-mean curves with ties or small
    # local inversions, while the interval values remain within the band.
    monotonic_values: list[float] = []
    for value in bounded_values:
        value = max(0.0, min(100.0, float(value)))
        if monotonic_values:
            value = max(value, monotonic_values[-1])
        monotonic_values.append(value)

    result = dict(calibration)
    result["x_pred"] = knots
    result["y_calibrated"] = monotonic_values
    return result


def augment_masked_calibration_samples(
    pred: list[float],
    target: list[float],
    weights: list[float] | None = None,
    sample_mask: list[bool] | None = None,
    *,
    radius: float = 0.0,
    steps: int = 0,
    weight_multiplier: float = 0.0,
) -> tuple[list[float], list[float], list[float]]:
    pred_out = [float(value) for value in pred]
    target_out = [float(value) for value in target]
    if weights is None:
        weight_out = [1.0 for _ in pred_out]
    else:
        weight_out = [max(1e-6, float(value)) for value in weights]

    if (
        sample_mask is None
        or radius <= 0.0
        or steps <= 0
        or weight_multiplier <= 0.0
    ):
        return pred_out, target_out, weight_out
    if len(sample_mask) != len(pred_out):
        raise ValueError("sample_mask length must match pred length")

    for pred_value, target_value, sample_weight, is_selected in zip(
        pred_out[:len(sample_mask)],
        target_out[:len(sample_mask)],
        weight_out[:len(sample_mask)],
        sample_mask,
    ):
        if not is_selected:
            continue
        for step in range(1, steps + 1):
            offset = radius * float(step) / float(steps)
            augmented_weight = max(1e-6, sample_weight * weight_multiplier / float(step))
            pred_out.append(max(0.0, pred_value - offset))
            target_out.append(target_value)
            weight_out.append(augmented_weight)
            pred_out.append(min(100.0, pred_value + offset))
            target_out.append(target_value)
            weight_out.append(augmented_weight)
    return pred_out, target_out, weight_out


def augment_midpoint_calibration_samples(
    pred: list[float],
    target: list[float],
    weights: list[float] | None = None,
    midpoint_mask: list[bool] | None = None,
    *,
    radius: float = 0.0,
    steps: int = 0,
    weight_multiplier: float = 0.0,
) -> tuple[list[float], list[float], list[float]]:
    return augment_masked_calibration_samples(
        pred,
        target,
        weights,
        midpoint_mask,
        radius=radius,
        steps=steps,
        weight_multiplier=weight_multiplier,
    )


def build_quantile_mean_calibration(
    pred: list[float],
    target: list[float],
    weights: list[float] | None = None,
) -> dict[str, list[float]]:
    pred_arr = np.array(pred, dtype=np.float32)
    target_arr = np.array(target, dtype=np.float32)
    if weights is None:
        weight_arr = np.ones(len(pred_arr), dtype=np.float32)
    else:
        weight_arr = np.clip(np.array(weights, dtype=np.float32), 1e-6, None)
    order = np.argsort(pred_arr)
    pred_arr = pred_arr[order]
    target_arr = target_arr[order]
    weight_arr = weight_arr[order]

    x: list[float] = []
    y: list[float] = []
    n = len(pred_arr)
    n_bins = min(20, max(5, n // 2))
    for i in range(n_bins):
        left = int(i * n / n_bins)
        right = int((i + 1) * n / n_bins)
        if right <= left:
            continue
        x.append(float(np.average(pred_arr[left:right], weights=weight_arr[left:right])))
        y.append(float(np.average(target_arr[left:right], weights=weight_arr[left:right])))
    if not x:
        x = [0.0, 100.0]
        y = [0.0, 100.0]
    return {"x_pred": x, "y_calibrated": y, "method": "quantile_mean"}


def build_isotonic_calibration(
    pred: list[float],
    target: list[float],
    weights: list[float] | None = None,
) -> dict[str, list[float]]:
    pred_arr = np.array(pred, dtype=np.float64)
    target_arr = np.clip(np.array(target, dtype=np.float64), 0.0, 100.0)
    if weights is None:
        weight_arr = np.ones(len(pred_arr), dtype=np.float64)
    else:
        weight_arr = np.clip(np.array(weights, dtype=np.float64), 1e-6, None)
    if len(pred_arr) == 0:
        return {"x_pred": [0.0, 100.0], "y_calibrated": [0.0, 100.0], "method": "isotonic"}

    order = np.argsort(pred_arr, kind="mergesort")
    pred_arr = pred_arr[order]
    target_arr = target_arr[order]
    weight_arr = weight_arr[order]

    # Pool adjacent violators algorithm. It gives the monotonic least-squares
    # calibration curve without depending on sklearn at runtime.
    blocks: list[dict[str, float]] = []
    for x_value, y_value, sample_weight in zip(pred_arr, target_arr, weight_arr):
        blocks.append({
            "x_sum": float(x_value) * float(sample_weight),
            "y_sum": float(y_value) * float(sample_weight),
            "weight": float(sample_weight),
            "x_min": float(x_value),
            "x_max": float(x_value),
        })
        while len(blocks) >= 2:
            left = blocks[-2]
            right = blocks[-1]
            left_mean = left["y_sum"] / left["weight"]
            right_mean = right["y_sum"] / right["weight"]
            if left_mean <= right_mean:
                break
            merged = {
                "x_sum": left["x_sum"] + right["x_sum"],
                "y_sum": left["y_sum"] + right["y_sum"],
                "weight": left["weight"] + right["weight"],
                "x_min": left["x_min"],
                "x_max": right["x_max"],
            }
            blocks[-2:] = [merged]

    x: list[float] = []
    y: list[float] = []
    for block in blocks:
        mean_y = float(np.clip(block["y_sum"] / block["weight"], 0.0, 100.0))
        x_left = float(block["x_min"])
        x_right = float(block["x_max"])
        if x and x_left <= x[-1]:
            x_left = x[-1] + 1e-6
        x.append(x_left)
        y.append(mean_y)
        if x_right > x_left:
            x.append(x_right)
            y.append(mean_y)

    if not x:
        x = [0.0, 100.0]
        y = [0.0, 100.0]
    elif len(x) == 1:
        only_x = x[0]
        only_y = y[0]
        x = [max(0.0, only_x - 1e-6), min(100.0, only_x + 1e-6)]
        y = [only_y, only_y]

    return {"x_pred": x, "y_calibrated": y, "method": "isotonic"}


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
