#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUTS = [
    ROOT / "data" / "score_trace_review_candidates.csv",
    ROOT / "data" / "nightly_worst_case_review_candidates.csv",
]
ALLOWED_STATUSES = {"", "pending", "approved", "merged", "rejected", "ignored"}
TRAINING_STATUSES = {"approved", "merged"}
ALLOWED_SOURCES = {
    "",
    "score_trace",
    "nightly_worst_case",
    "nightly_bucket_confusion",
}
ALLOWED_SEVERITIES = {"", "low", "medium", "high", "critical"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate semantic review candidate CSVs before they can feed training.")
    parser.add_argument("inputs", nargs="*", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict-pending",
        action="store_true",
        help="Treat invalid pending/rejected/ignored rows as failures too.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def as_score(value: str) -> int | None:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 100:
        return score
    return None


def is_antonym(row: dict[str, str]) -> bool:
    text = " ".join(
        [
            row.get("error_type", ""),
            row.get("relation_tag", ""),
            row.get("natural_relation", ""),
            row.get("why_wrong", ""),
        ]
    ).lower()
    return "antonym" in text or "反义" in text


def row_problems(row: dict[str, str]) -> list[str]:
    problems: list[str] = []
    answer = (row.get("answer") or "").strip()
    user_input = (row.get("user_input") or "").strip()
    status = (row.get("review_status") or "").strip().lower()
    source = (row.get("source") or "").strip()
    severity = (row.get("error_severity") or "").strip().lower()
    corrected = as_score(row.get("corrected_score", ""))
    current = as_score(row.get("current_score", ""))

    if not answer:
        problems.append("missing answer")
    if not user_input:
        problems.append("missing user_input")
    if status not in ALLOWED_STATUSES:
        problems.append(f"invalid review_status={status!r}")
    if source not in ALLOWED_SOURCES:
        problems.append(f"invalid source={source!r}")
    if severity not in ALLOWED_SEVERITIES:
        problems.append(f"invalid error_severity={severity!r}")
    if corrected is None:
        problems.append("corrected_score must be 0-100")
    if (row.get("current_score") or "").strip() and current is None:
        problems.append("current_score must be 0-100 when present")
    if is_antonym(row):
        if corrected != 50:
            problems.append("antonym rows must have corrected_score=50")
        error_type = (row.get("error_type") or row.get("relation_tag") or "").strip()
        if error_type and error_type != "antonym_mid":
            problems.append("antonym rows must use error_type/relation_tag=antonym_mid")
    return problems


def validate(paths: list[Path], strict_pending: bool) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    duplicates: dict[tuple[str, str], list[str]] = {}
    total_rows = 0
    training_rows = 0

    for path in paths:
        rows = read_rows(path)
        total_rows += len(rows)
        for index, row in enumerate(rows, start=2):
            status = (row.get("review_status") or "").strip().lower()
            if status in TRAINING_STATUSES:
                training_rows += 1
            key = ((row.get("answer") or "").strip(), (row.get("user_input") or "").strip())
            if key[0] and key[1]:
                duplicates.setdefault(key, []).append(f"{path}:{index}")
            problems = row_problems(row)
            if problems and (strict_pending or status in TRAINING_STATUSES):
                issues.append(
                    {
                        "path": str(path),
                        "line": index,
                        "status": status,
                        "answer": row.get("answer", ""),
                        "user_input": row.get("user_input", ""),
                        "problems": problems,
                    }
                )

    duplicate_issues = [
        {"answer": key[0], "user_input": key[1], "locations": locations}
        for key, locations in sorted(duplicates.items())
        if len(locations) > 1
    ]
    if duplicate_issues:
        for item in duplicate_issues:
            issues.append(
                {
                    "path": "(multiple)",
                    "line": 0,
                    "status": "duplicate",
                    "answer": item["answer"],
                    "user_input": item["user_input"],
                    "problems": [f"duplicate pair at {', '.join(item['locations'])}"],
                }
            )

    return {
        "ok": not issues,
        "inputs": [str(path) for path in paths],
        "total_rows": total_rows,
        "training_rows": training_rows,
        "issues": issues,
        "issue_count": len(issues),
    }


def print_human(payload: dict[str, object]) -> None:
    print(f"ok={payload['ok']}")
    print(f"total_rows={payload['total_rows']}")
    print(f"training_rows={payload['training_rows']}")
    print(f"issue_count={payload['issue_count']}")
    if payload["issues"]:
        print("issues:")
        for issue in payload["issues"]:
            print(
                "- "
                f"{issue['path']}:{issue['line']} "
                f"{issue['answer']}->{issue['user_input']} "
                f"{'; '.join(issue['problems'])}"
            )


def main() -> int:
    args = parse_args()
    paths = [path if path.is_absolute() else ROOT / path for path in args.inputs]
    payload = validate(paths, args.strict_pending)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
