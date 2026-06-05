#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = ROOT / ".nightly" / "reports"
DEFAULT_OUTPUT = ROOT / "data" / "nightly_worst_case_review_candidates.csv"

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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def choose_report(report: str | None, include_dry_run: bool) -> Path:
    if report:
        path = Path(report)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise SystemExit(f"report not found: {path}")
        return path

    for path in sorted(DEFAULT_REPORTS_DIR.glob("nightly_promotion_*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        text = read_text(path)
        if include_dry_run or "DRY_RUN" not in text:
            return path
    raise SystemExit(f"no nightly report found under {DEFAULT_REPORTS_DIR}")


def report_stamp(path: Path) -> str:
    match = re.search(r"nightly_promotion_(\d{8}_\d{6})\.md$", path.name)
    return match.group(1) if match else path.stem


def parse_markdown_tables(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in re.split(r"\n### ", text):
        if not section.startswith("候选最差样本"):
            continue
        headers: list[str] = []
        for line in section.splitlines():
            if not line.startswith("|") or "---" in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if not headers:
                headers = cells
                continue
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
    return rows


def as_int(value: str) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def severity(error: int) -> str:
    if error >= 45:
        return "critical"
    if error >= 30:
        return "high"
    if error >= 18:
        return "medium"
    return "low"


def is_antonym(tag: str, group: str) -> bool:
    return "antonym" in tag.lower() or "反义" in tag or group.lower() == "antonym"


def to_review_rows(cases: list[dict[str, str]], stamp: str, created_at: str, min_error: int, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    sorted_cases = sorted(cases, key=lambda row: as_int(row.get("error", "")) or -1, reverse=True)
    for row in sorted_cases:
        answer = (row.get("answer") or "").strip()
        user_input = (row.get("input") or row.get("user_input") or "").strip()
        target = as_int(row.get("target", ""))
        candidate = as_int(row.get("candidate", ""))
        err = as_int(row.get("error", ""))
        if not answer or not user_input or target is None or candidate is None or err is None:
            continue
        if err < min_error:
            continue
        key = (answer, user_input)
        if key in seen:
            continue
        seen.add(key)
        tag = (row.get("tag") or row.get("group") or "").strip()
        group = (row.get("group") or "").strip()
        corrected = 50 if is_antonym(tag, group) else target
        normalized_tag = "antonym_mid" if is_antonym(tag, group) else tag
        direction = "over_score" if candidate > corrected else "under_score"
        original_note = f"; original_target={target}" if corrected != target else ""
        out.append(
            {
                "case_id": str(len(out) + 1),
                "answer": answer,
                "user_input": user_input,
                "current_score": str(candidate),
                "corrected_score": str(corrected),
                "error_type": normalized_tag,
                "error_severity": severity(err),
                "why_wrong": f"nightly worst case {direction}; target={corrected}, candidate={candidate}, error={err}{original_note}",
                "natural_relation": group,
                "evidence": f"nightly_report {stamp}; group={group}; tag={tag}",
                "review_status": "pending",
                "reviewer": "",
                "source": "nightly_worst_case",
                "created_at": created_at,
            }
        )
        if limit > 0 and len(out) >= limit:
            break
    return out


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract pending review rows from nightly report worst-case tables."
    )
    parser.add_argument("--report", help="Specific nightly_promotion_*.md file. Defaults to latest non-dry-run report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-dry-run", action="store_true")
    parser.add_argument("--min-error", type=int, default=18)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--created-at", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    report = choose_report(args.report, args.include_dry_run)
    cases = parse_markdown_tables(read_text(report))
    rows = to_review_rows(cases, report_stamp(report), args.created_at, args.min_error, args.limit)
    write_csv(args.output, rows)
    print(f"report={report}")
    print(f"worst_cases={len(cases)} review_rows={len(rows)} output={args.output}")
    print("Next: review corrected_score/error_type, then set review_status=approved for rows to train.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
