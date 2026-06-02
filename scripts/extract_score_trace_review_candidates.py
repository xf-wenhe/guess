#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable


FIELDNAMES = [
    "case_id",
    "answer",
    "user_input",
    "current_score",
    "corrected_score",
    "error_type",
    "error_severity",
    "why_wrong",
    "natural_relation",
    "evidence",
    "review_status",
    "reviewer",
    "source",
    "created_at",
]

TRACE_RE = re.compile(r"\[score_trace\]\s*(\{.*\})")


def parse_trace_lines(paths: Iterable[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as file:
            for line_no, line in enumerate(file, start=1):
                match = TRACE_RE.search(line)
                if not match:
                    continue
                try:
                    payload = json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
                event = str(payload.get("event") or "")
                if event not in {"semantic_mix", "manual_override", "fallback_lexical"}:
                    continue
                answer = str(payload.get("answer") or "").strip()
                guess = str(payload.get("guess") or "").strip()
                if not answer or not guess or answer == guess:
                    continue
                try:
                    score = int(round(float(payload.get("final"))))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "answer": answer,
                        "user_input": guess,
                        "current_score": str(max(0, min(100, score))),
                        "event": event,
                        "notes": payload.get("notes") or [],
                        "trace_source": f"{path}:{line_no}",
                    }
                )
    return rows


def classify(score: int) -> tuple[str, str, str, str]:
    if score >= 75:
        return (
            "possible_false_positive_high_score",
            "high" if score < 88 else "critical",
            "模型给出高分；请人工确认是否真是同义/强相关，否则填写 corrected_score",
            "unknown_until_review",
        )
    if score <= 25:
        return (
            "possible_false_negative_low_score",
            "medium",
            "模型给出低分；请人工确认是否漏判同义/别名/强相关",
            "unknown_until_review",
        )
    return (
        "borderline_review",
        "low",
        "中间分样本；优先审核同类易混淆或玩家反馈争议对",
        "unknown_until_review",
    )


def dedupe_rank(rows: list[dict], limit: int) -> list[dict]:
    best_by_pair: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["answer"], row["user_input"])
        score = int(row["current_score"])
        priority = abs(score - 50)
        previous = best_by_pair.get(key)
        if previous is None or priority > int(previous["_priority"]):
            row["_priority"] = str(priority)
            best_by_pair[key] = row
    ranked = sorted(
        best_by_pair.values(),
        key=lambda row: (int(row["_priority"]), int(row["current_score"])),
        reverse=True,
    )
    if limit > 0:
        ranked = ranked[:limit]
    return ranked


def to_review_rows(rows: list[dict], created_at: str) -> list[dict]:
    out = []
    for idx, row in enumerate(rows, start=1):
        score = int(row["current_score"])
        error_type, severity, why_wrong, relation = classify(score)
        out.append(
            {
                "case_id": str(idx),
                "answer": row["answer"],
                "user_input": row["user_input"],
                "current_score": row["current_score"],
                "corrected_score": "",
                "error_type": error_type,
                "error_severity": severity,
                "why_wrong": why_wrong,
                "natural_relation": relation,
                "evidence": f"score_trace {row['event']} notes={row['notes']} at {row['trace_source']}",
                "review_status": "pending",
                "reviewer": "",
                "source": "score_trace",
                "created_at": created_at,
            }
        )
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract review candidates from Flutter SCORE_TRACE logs."
    )
    parser.add_argument("logs", nargs="+", type=Path, help="Log files containing [score_trace] JSON lines.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/score_trace_review_candidates.csv"),
        help="CSV review file to write. Approved rows are consumed by nightly data building.",
    )
    parser.add_argument("--limit", type=int, default=200, help="Maximum rows to write; <=0 writes all.")
    parser.add_argument(
        "--created-at",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="created_at value for generated rows.",
    )
    args = parser.parse_args()

    traces = parse_trace_lines(args.logs)
    candidates = dedupe_rank(traces, args.limit)
    review_rows = to_review_rows(candidates, args.created_at)
    write_csv(args.output, review_rows)
    print(f"trace_rows={len(traces)} candidates={len(review_rows)} output={args.output}")
    print("Next: review corrected_score/review_status, then rerun nightly training.")


if __name__ == "__main__":
    main()
