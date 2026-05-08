from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from hint_quality_v29_common import (
    HintIssue,
    detect_cross_domain,
    is_meta_hint,
    monotonic_violations,
    normalize_hint,
    semantic_progress_score,
    top_counter,
)


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


def build_embed_score_map(
    data: list[dict],
    model_path: str,
    calib_path: Path | None,
) -> dict[tuple[str, str], float]:
    texts: list[str] = []
    for item in data:
        answer = str(item.get("answer", "")).strip()
        if answer:
            texts.append(answer)
        for h in (item.get("hints") or []):
            hint = normalize_hint(h)
            if hint:
                texts.append(hint)

    uniq_texts = list(dict.fromkeys(texts))
    if not uniq_texts:
        return {}

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq_texts, normalize_embeddings=True, batch_size=256)
    text_to_idx = {t: i for i, t in enumerate(uniq_texts)}

    cal_x: list[float] | None = None
    cal_y: list[float] | None = None
    if calib_path and calib_path.exists():
        calib = json.loads(calib_path.read_text(encoding="utf-8"))
        cal_x = calib.get("x_pred")
        cal_y = calib.get("y_calibrated")
        if not isinstance(cal_x, list) or not isinstance(cal_y, list) or len(cal_x) < 2 or len(cal_y) < 2:
            cal_x = None
            cal_y = None

    score_map: dict[tuple[str, str], float] = {}
    for item in data:
        answer = str(item.get("answer", "")).strip()
        if not answer or answer not in text_to_idx:
            continue
        a_vec = emb[text_to_idx[answer]]
        for h in (item.get("hints") or []):
            hint = normalize_hint(h)
            if not hint or hint not in text_to_idx:
                continue
            h_vec = emb[text_to_idx[hint]]
            raw = float(np.dot(a_vec, h_vec) * 100.0)
            if cal_x and cal_y:
                raw = apply_calibration(raw, cal_x, cal_y)
            score_map[(answer, hint)] = raw

    return score_map


def run_audit(
    input_path: Path,
    out_dir: Path,
    model_path: str | None,
    calib_path: Path | None,
) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    issues: list[HintIssue] = []
    banned_counter: Counter[str] = Counter()
    cross_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    mono_counter = 0

    monotonic_mode = "heuristic"
    embed_scores: dict[tuple[str, str], float] = {}
    if model_path:
        embed_scores = build_embed_score_map(data, model_path, calib_path)
        monotonic_mode = "embedding_calibrated" if calib_path and calib_path.exists() else "embedding_raw"

    for idx, item in enumerate(data):
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        hints = [normalize_hint(h) for h in (item.get("hints") or []) if normalize_hint(h)]
        category_counter[category] += 1

        for h_idx, hint in enumerate(hints):
            bad, reason = is_meta_hint(hint)
            if bad:
                banned_counter[hint] += 1
                issues.append(
                    HintIssue(idx, category, answer, h_idx, hint, "banned_hint", reason)
                )

            cross_hits = detect_cross_domain(category, hint)
            for domain, token in cross_hits:
                key = f"{domain}:{token}"
                cross_counter[key] += 1
                issues.append(
                    HintIssue(
                        idx,
                        category,
                        answer,
                        h_idx,
                        hint,
                        "cross_domain",
                        f"token={token},domain={domain}",
                    )
                )

        if len(hints) >= 2:
            if embed_scores:
                scores = [
                    embed_scores.get((answer, h), semantic_progress_score(answer, category, h))
                    for h in hints[:7]
                ]
            else:
                scores = [semantic_progress_score(answer, category, h) for h in hints[:7]]
            violations = monotonic_violations(scores)
            if violations:
                mono_counter += 1
                issues.append(
                    HintIssue(
                        idx,
                        category,
                        answer,
                        -1,
                        "|".join(hints[:7]),
                        "monotonic_violation",
                        f"mode={monotonic_mode};scores={','.join(f'{s:.2f}' for s in scores)}",
                    )
                )

    summary = {
        "input": str(input_path),
        "items": len(data),
        "monotonic_mode": monotonic_mode,
        "model_path": model_path or "",
        "calib_path": str(calib_path) if calib_path else "",
        "categories": top_counter(category_counter, n=50),
        "banned_hits": int(sum(banned_counter.values())),
        "cross_domain_hits": int(sum(cross_counter.values())),
        "monotonic_items": mono_counter,
        "top_banned_terms": top_counter(banned_counter, n=50),
        "top_cross_domain_tokens": top_counter(cross_counter, n=50),
    }

    details = [
        {
            "index": i.index,
            "category": i.category,
            "answer": i.answer,
            "hint_index": i.hint_index,
            "hint": i.hint,
            "issue_type": i.issue_type,
            "detail": i.detail,
        }
        for i in issues
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "hints_audit_v29_summary.json"
    details_path = out_dir / "hints_audit_v29_details.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    details_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "summary_path": str(summary_path),
        "details_path": str(details_path),
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit puzzle hints quality v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--model-path", default="")
    parser.add_argument("--calib-path", default="")
    args = parser.parse_args()

    model_path = args.model_path.strip() or None
    calib_path = Path(args.calib_path) if args.calib_path.strip() else None

    result = run_audit(Path(args.input), Path(args.out_dir), model_path, calib_path)
    summary = result["summary"]
    print(
        "items={items} banned_hits={banned_hits} cross_domain_hits={cross_domain_hits} monotonic_items={monotonic_items} mode={monotonic_mode}".format(
            **summary
        )
    )
    print(f"summary={result['summary_path']}")
    print(f"details={result['details_path']}")


if __name__ == "__main__":
    main()
