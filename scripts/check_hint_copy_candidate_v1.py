from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer


POLICY = json.loads(Path("data/final_hint_policy_v1.json").read_text(encoding="utf-8"))
UNIVERSAL = POLICY.get("universal_constraints", {})
META_TERMS = set(UNIVERSAL.get("forbidden_meta_terms", []))
MAX_CHARS_PER_HINT = int(UNIVERSAL.get("max_chars_per_hint", 999))
EARLY = UNIVERSAL.get("early_reveal_guard", {})
EARLY_ENABLED = bool(EARLY.get("enabled", False))
EARLY_SLOTS = [int(x) for x in (EARLY.get("slots") or [1, 2, 3])]
EARLY_CATEGORY_TERMS = {
    str(k): [str(v).strip() for v in vals]
    for k, vals in (EARLY.get("category_block_terms") or {}).items()
}
EARLY_ANSWER_TERMS = {
    str(k): [str(v).strip() for v in vals]
    for k, vals in (EARLY.get("answer_block_terms") or {}).items()
}
NATURAL_GUARD = UNIVERSAL.get("natural_language_guard", {})
NATURAL_ENABLED = bool(NATURAL_GUARD.get("enabled", False))
NATURAL_FORBIDDEN_FRAGMENTS = [str(x).strip() for x in (NATURAL_GUARD.get("forbidden_fragments") or [])]

DIVERSITY_GUARD = UNIVERSAL.get("answer_conditioned_diversity_guard", {})
DIVERSITY_ENABLED = bool(DIVERSITY_GUARD.get("enabled", False))
DIVERSITY_DEFAULT_MIN = int(DIVERSITY_GUARD.get("default_min_unique_dimensions", 0))
DIVERSITY_DIM_LEXICON = {
    str(k): [str(v).strip() for v in vals]
    for k, vals in (DIVERSITY_GUARD.get("dimension_lexicon") or {}).items()
}
DIVERSITY_OVERRIDES = DIVERSITY_GUARD.get("answer_overrides") or {}

CATEGORY_KNOWN_GUARD = UNIVERSAL.get("category_known_guard", {})
CATEGORY_KNOWN_ENABLED = bool(CATEGORY_KNOWN_GUARD.get("enabled", False))
CATEGORY_KNOWN_DEFAULT = CATEGORY_KNOWN_GUARD.get("default_rules") or {}
CATEGORY_KNOWN_OVERRIDES = CATEGORY_KNOWN_GUARD.get("category_overrides") or {}
GUESSABILITY_GUARD = UNIVERSAL.get("guessability_guard", {})
GUESSABILITY_ENABLED = bool(GUESSABILITY_GUARD.get("enabled", False))
GUESSABILITY_MIN = float(GUESSABILITY_GUARD.get("min_percent", 30))
GUESSABILITY_MAX = float(GUESSABILITY_GUARD.get("max_percent", 90))
GUESSABILITY_TARGET_CURVE = [float(x) for x in (GUESSABILITY_GUARD.get("target_curve") or [])]
GUESSABILITY_TOLERANCE = float(GUESSABILITY_GUARD.get("target_tolerance", 15))
GUESSABILITY_ENFORCE_TARGET_CURVE = bool(GUESSABILITY_GUARD.get("enforce_target_curve", False))
GUESSABILITY_ENFORCE_MONOTONIC = bool(GUESSABILITY_GUARD.get("enforce_monotonic", True))
GUESSABILITY_MONOTONIC_DROP_TOL = float(GUESSABILITY_GUARD.get("monotonic_drop_tolerance", 3))
GUESSABILITY_MODEL_PATH = str(GUESSABILITY_GUARD.get("model_path", ""))
GUESSABILITY_CALIB_PATH = str(GUESSABILITY_GUARD.get("calib_path", ""))

ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check one hint candidate item line-by-line")
    parser.add_argument("--category", default="")
    parser.add_argument("--answer", default="")
    parser.add_argument("--hints-json", default="")
    parser.add_argument("--lookup", default="", help="lookup key: category::answer from puzzles")
    parser.add_argument("--puzzles", default="assets/puzzles.json")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if any violation")
    return parser.parse_args()


def load_from_lookup(puzzles_path: Path, lookup: str) -> tuple[str, str, list[str]]:
    if "::" not in lookup:
        raise SystemExit("lookup must be category::answer")
    category, answer = lookup.split("::", 1)
    data = json.loads(puzzles_path.read_text(encoding="utf-8"))
    for item in data:
        c = str(item.get("category", "")).strip()
        a = str(item.get("answer", "")).strip()
        if c == category and a == answer:
            hints = [str(h).strip() for h in (item.get("hints") or [])]
            return c, a, hints
    raise SystemExit(f"item not found: {lookup}")


def has_char_overlap(answer: str, hint: str) -> bool:
    a = {ch for ch in answer if ch.strip()}
    h = {ch for ch in hint if ch.strip()}
    return bool(a & h)


def visible_char_count(text: str) -> int:
    return len("".join(ch for ch in text if ch.strip()))


def cosine_similarity(left, right) -> float:
    dot = float((left * right).sum())
    ln = float((left * left).sum()) ** 0.5
    rn = float((right * right).sum()) ** 0.5
    return 0.0 if ln == 0 or rn == 0 else dot / ln / rn


def apply_calibration(pred: float, x: list[float], y: list[float]) -> float:
    if pred <= x[0]:
        return y[0]
    if pred >= x[-1]:
        return y[-1]
    for i in range(len(x) - 1):
        left, right = x[i], x[i + 1]
        if left <= pred <= right:
            span = right - left
            if span == 0:
                return y[i]
            ratio = (pred - left) / span
            return y[i] + (y[i + 1] - y[i]) * ratio
    return pred


def load_calibration(path: Path) -> tuple[list[float], list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [float(v) for v in payload["x_pred"]], [float(v) for v in payload["y_calibrated"]]


def score_guessability(answer: str, hints: list[str]) -> list[float]:
    if not GUESSABILITY_ENABLED:
        return [0.0 for _ in hints]
    if not GUESSABILITY_MODEL_PATH or not GUESSABILITY_CALIB_PATH:
        raise RuntimeError("guessability_guard missing model_path or calib_path")
    model = SentenceTransformer(GUESSABILITY_MODEL_PATH, device="cpu", local_files_only=True)
    cal_x, cal_y = load_calibration(Path(GUESSABILITY_CALIB_PATH))

    # Batch encode for speed and deterministic per-hint checks.
    texts = [answer] + hints
    cache = {}
    for angle in ANGLES:
        prompts = [f"{angle}{text}" for text in texts]
        vecs = model.encode(prompts, normalize_embeddings=True)
        for text, vec in zip(texts, vecs):
            cache[(angle, text)] = vec

    scores: list[float] = []
    for hint in hints:
        per_angle = []
        for angle in ANGLES:
            a_vec = cache[(angle, answer)]
            h_vec = cache[(angle, hint)]
            per_angle.append(cosine_similarity(a_vec, h_vec))
        per_angle.sort()
        trimmed = per_angle[1:-1] if len(per_angle) >= 3 else per_angle
        raw = sum(trimmed) / len(trimmed) * 100.0
        cal = apply_calibration(raw, cal_x, cal_y)
        scores.append(cal)
    return scores


def hit_early_reveal(category: str, answer: str, slot: int, hint: str) -> list[str]:
    if not EARLY_ENABLED or slot not in EARLY_SLOTS:
        return []
    key = f"{category}::{answer}"
    terms = list(EARLY_CATEGORY_TERMS.get(category, [])) + list(EARLY_ANSWER_TERMS.get(key, []))
    return [term for term in terms if term and term in hint]


def hit_natural_forbidden(hint: str) -> list[str]:
    if not NATURAL_ENABLED:
        return []
    return [frag for frag in NATURAL_FORBIDDEN_FRAGMENTS if frag and frag in hint]


def classify_dimension(hint: str) -> str:
    for dim, terms in DIVERSITY_DIM_LEXICON.items():
        for term in terms:
            if term and term in hint:
                return dim
    return "unknown"


def required_min_unique_dimensions(category: str, answer: str) -> int:
    key = f"{category}::{answer}"
    override = DIVERSITY_OVERRIDES.get(key) or {}
    return int(override.get("min_unique_dimensions", DIVERSITY_DEFAULT_MIN))


def category_known_slot_max_percent(category: str, slot: int) -> float | None:
    if not CATEGORY_KNOWN_ENABLED:
        return None
    default_map = CATEGORY_KNOWN_DEFAULT.get("slot_max_percent") or {}
    cfg = CATEGORY_KNOWN_OVERRIDES.get(category) or {}
    slot_map = dict(default_map)
    slot_map.update(cfg.get("slot_max_percent") or {})
    raw = slot_map.get(str(slot))
    if raw is None:
        return None
    return float(raw)


def category_known_early_forbidden(category: str, slot: int, hint: str) -> list[str]:
    if not CATEGORY_KNOWN_ENABLED:
        return []
    default_frag = CATEGORY_KNOWN_DEFAULT.get("early_slot_forbidden_fragments") or {}
    default_slots = [int(x) for x in (default_frag.get("slots") or [])]
    default_terms = [str(x).strip() for x in (default_frag.get("terms") or [])]

    cfg = CATEGORY_KNOWN_OVERRIDES.get(category) or {}
    frag = cfg.get("early_slot_forbidden_fragments") or {}
    slots = [int(x) for x in (frag.get("slots") or default_slots)]
    if slot not in slots:
        return []
    terms = list(default_terms)
    terms.extend([str(x).strip() for x in (frag.get("terms") or [])])
    return [term for term in terms if term and term in hint]


def main() -> None:
    args = parse_args()
    if args.lookup:
        category, answer, hints = load_from_lookup(Path(args.puzzles), args.lookup)
    else:
        category = args.category.strip()
        answer = args.answer.strip()
        if not args.hints_json:
            raise SystemExit("provide --hints-json or --lookup")
        hints = [str(x).strip() for x in json.loads(args.hints_json)]

    seen = set()
    per_hint = []
    violation_count = 0
    guessability_scores = score_guessability(answer, hints) if GUESSABILITY_ENABLED else [0.0 for _ in hints]
    previous_score = None
    dimensions = []

    for index, hint in enumerate(hints, start=1):
        reasons = []
        if not hint:
            reasons.append("empty_hint")
        if visible_char_count(hint) > MAX_CHARS_PER_HINT:
            reasons.append(f"max_char_length_exceeded:{MAX_CHARS_PER_HINT}")
        if hint in seen:
            reasons.append("duplicate_hint")
        seen.add(hint)
        if has_char_overlap(answer, hint):
            reasons.append("answer_char_overlap")
        if hint in META_TERMS:
            reasons.append("forbidden_meta_term")
        natural_hits = hit_natural_forbidden(hint)
        if natural_hits:
            reasons.append("non_natural_fragment:" + ",".join(natural_hits))
        early_terms = hit_early_reveal(category, answer, index, hint)
        if early_terms:
            reasons.append("early_reveal_guard:" + ",".join(early_terms))

        dim = classify_dimension(hint)
        dimensions.append(dim)

        score = float(guessability_scores[index - 1])
        if GUESSABILITY_ENABLED:
            if score < GUESSABILITY_MIN or score > GUESSABILITY_MAX:
                reasons.append(f"guessability_out_of_range:{score:.2f}")
            slot_cap = category_known_slot_max_percent(category, index)
            if slot_cap is not None and score > slot_cap:
                reasons.append(f"category_known_slot_cap:{score:.2f}>{slot_cap:.0f}")
            if GUESSABILITY_ENFORCE_TARGET_CURVE and index <= len(GUESSABILITY_TARGET_CURVE):
                target = GUESSABILITY_TARGET_CURVE[index - 1]
                if abs(score - target) > GUESSABILITY_TOLERANCE:
                    reasons.append(f"guessability_off_target:{score:.2f}!={target:.0f}")
            if GUESSABILITY_ENFORCE_MONOTONIC and previous_score is not None:
                if score < previous_score - GUESSABILITY_MONOTONIC_DROP_TOL:
                    reasons.append(f"guessability_non_monotonic:{previous_score:.2f}->{score:.2f}")
            previous_score = score

        cat_known_hits = category_known_early_forbidden(category, index, hint)
        if cat_known_hits:
            reasons.append("category_known_forbidden:" + ",".join(cat_known_hits))

        if reasons:
            violation_count += 1
        per_hint.append({"slot": index, "hint": hint, "dimension": dim, "guessability": round(score, 2), "ok": not reasons, "reasons": reasons})

    diversity_violation = None
    unique_dims = sorted({d for d in dimensions if d != "unknown"})
    min_dims = required_min_unique_dimensions(category, answer)
    if DIVERSITY_ENABLED and len(unique_dims) < min_dims:
        diversity_violation = f"insufficient_dimension_diversity:{len(unique_dims)}<{min_dims}"
        violation_count += 1

    report = {
        "category": category,
        "answer": answer,
        "hint_count": len(hints),
        "all_pass": violation_count == 0,
        "violation_hint_count": violation_count,
        "guessability_guard_enabled": GUESSABILITY_ENABLED,
        "guessability_range": [GUESSABILITY_MIN, GUESSABILITY_MAX],
        "guessability_enforce_target_curve": GUESSABILITY_ENFORCE_TARGET_CURVE,
        "guessability_enforce_monotonic": GUESSABILITY_ENFORCE_MONOTONIC,
        "guessability_target_curve": GUESSABILITY_TARGET_CURVE,
        "natural_language_guard_enabled": NATURAL_ENABLED,
        "dimension_diversity_guard_enabled": DIVERSITY_ENABLED,
        "dimension_unique_count": len(unique_dims),
        "dimension_unique_values": unique_dims,
        "dimension_min_required": min_dims,
        "diversity_violation": diversity_violation,
        "per_hint": per_hint,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and violation_count > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
