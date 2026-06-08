#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import analyze_nightly_report_v26
import check_nightly_launchd_v26
import extract_nightly_worst_case_review_candidates as worst_cases
import semantic_training_todo_status
import validate_review_candidates


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEW_OUT = ROOT / "data" / "nightly_worst_case_review_candidates.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-command next-morning triage for semantic nightly training."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--now", help="Override current local time, e.g. 2026-06-08T09:00:00.")
    parser.add_argument("--write-review-csv", action="store_true")
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW_OUT)
    parser.add_argument("--min-error", type=int, default=18)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--markdown-output", type=Path, help="Optional Markdown summary path to write.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as file:
        return sum(1 for _ in csv.DictReader(file))


def count_field(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = (row.get(field) or "(missing)").strip() or "(missing)"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def review_summary_from_rows(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "rows": len(rows),
        "source_counts": count_field(rows, "source"),
        "status_counts": count_field(rows, "review_status"),
        "severity_counts": count_field(rows, "error_severity"),
    }


def review_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"rows": 0, "source_counts": {}, "status_counts": {}, "severity_counts": {}}
    with path.open("r", encoding="utf-8", newline="") as file:
        return review_summary_from_rows(list(csv.DictReader(file)))


def choose_todo_path(root: Path) -> Path:
    root_todo = root / "docs" / "SEMANTIC_TRAINING_TODO.md"
    if root_todo.exists():
        return root_todo
    return semantic_training_todo_status.DEFAULT_TODO


def review_validation_paths(root: Path, review_output: Path) -> list[Path]:
    paths = [root / "data" / "score_trace_review_candidates.csv", review_output]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def build_triage(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.resolve()
    nightly_root = root / ".nightly"
    if args.now:
        # Reuse the health check's deterministic clock hook via CLI-style monkeypatch.
        real_datetime = check_nightly_launchd_v26.datetime

        class FixedDateTime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                parsed = datetime.fromisoformat(args.now)
                if tz is not None:
                    return parsed.replace(tzinfo=tz)
                return parsed

        check_nightly_launchd_v26.datetime = FixedDateTime

    health = check_nightly_launchd_v26.check(root, args.home)
    report_path = analyze_nightly_report_v26.choose_report(nightly_root, explicit=None, include_dry_run=False)
    analysis = analyze_nightly_report_v26.build_summary(report_path, nightly_root, include_dry_run=False)

    review_rows = 0
    review_stats: dict[str, object] = {"rows": 0, "source_counts": {}, "status_counts": {}, "severity_counts": {}}
    review_output = str(args.review_output)
    if args.write_review_csv:
        report_text = worst_cases.read_text(report_path)
        cases = worst_cases.parse_markdown_tables(report_text)
        confusions = worst_cases.parse_bucket_confusion_tables(report_text)
        rows = worst_cases.to_review_rows(
            cases,
            worst_cases.report_stamp(report_path),
            (args.now or datetime.now().isoformat()).split("T", 1)[0],
            args.min_error,
            args.limit,
        )
        remaining = max(args.limit - len(rows), 0) if args.limit > 0 else 0
        existing = {(row["answer"], row["user_input"]) for row in rows}
        if args.limit <= 0 or remaining > 0:
            rows.extend(
                worst_cases.to_bucket_review_rows(
                    confusions,
                    worst_cases.report_stamp(report_path),
                    (args.now or datetime.now().isoformat()).split("T", 1)[0],
                    remaining,
                    existing,
                )
            )
        for index, row in enumerate(rows, start=1):
            row["case_id"] = str(index)
        worst_cases.write_csv(args.review_output, rows)
        review_rows = len(rows)
        review_stats = review_summary_from_rows(rows)
    else:
        review_rows = count_csv_rows(args.review_output)
        review_stats = review_summary(args.review_output)

    review_validation = validate_review_candidates.validate(
        review_validation_paths(root, args.review_output),
        strict_pending=False,
    )

    todo = semantic_training_todo_status.parse_todo(choose_todo_path(root))
    todo_summary = {
        "todo": todo.get("todo"),
        "last_updated": todo.get("last_updated"),
        "done": todo.get("done"),
        "total": todo.get("total"),
        "pending": todo.get("pending"),
        "percent_done": todo.get("percent_done"),
        "pending_items": todo.get("pending_items", [])[:10],
    }

    status = "ok"
    exit_code = 0
    if not health.get("ok"):
        status = "launchd_unhealthy"
        exit_code = 2
    elif health.get("run_log_after_latest_schedule"):
        status = "nightly_started_waiting_for_report"
    elif health.get("missed_latest_schedule"):
        status = "missed_schedule"
        exit_code = 3
    elif not analysis.get("three_rounds_ok"):
        status = "waiting_for_next_real_three_round_report"

    return {
        "status": status,
        "exit_code": exit_code,
        "health": health,
        "analysis": {
            "report": analysis.get("report"),
            "dry_run": analysis.get("dry_run"),
            "result": analysis.get("result"),
            "three_rounds_ok": analysis.get("three_rounds_ok"),
            "requested_device": analysis.get("requested_device"),
            "actual_device_inferred": analysis.get("actual_device_inferred"),
            "used_gpu_or_mps": analysis.get("used_gpu_or_mps"),
            "cpu_fallback_seen": analysis.get("cpu_fallback_seen"),
            "best_round": analysis.get("best_round"),
            "failed_gates": analysis.get("failed_gates"),
            "group_regressions": analysis.get("group_regressions"),
            "bucket_confusions": analysis.get("bucket_confusions"),
            "antonym_group": analysis.get("antonym_group"),
        },
        "todo": todo_summary,
        "review_output": review_output,
        "review_rows": review_rows,
        "review_summary": review_stats,
        "review_source_counts": review_stats.get("source_counts", {}),
        "review_validation": review_validation,
        "review_csv_written": args.write_review_csv,
    }


def print_human(payload: dict[str, object]) -> None:
    health = payload["health"]
    analysis = payload["analysis"]
    todo = payload["todo"]
    print(f"status={payload['status']}")
    print(f"launchd_ok={health['ok']}")
    print(f"missed_latest_schedule={health['missed_latest_schedule']}")
    print(f"wrapper_loaded={health['wrapper_loaded']}")
    print(f"nightly_total_runs={health['nightly_total_runs']}")
    print(f"latest_run_log={health['latest_run_log']}")
    print(f"run_log_after_latest_schedule={health['run_log_after_latest_schedule']}")
    print(f"latest_real_report={health['latest_real_report']}")
    print(f"report={analysis['report']}")
    print(f"three_rounds_ok={analysis['three_rounds_ok']}")
    print(
        "device="
        f"requested:{analysis['requested_device']} "
        f"actual:{analysis['actual_device_inferred']} "
        f"gpu_or_mps:{analysis['used_gpu_or_mps']} "
        f"cpu_fallback:{analysis['cpu_fallback_seen']}"
    )
    print(f"result={analysis['result']}")
    if analysis["best_round"]:
        print(f"best_round={analysis['best_round']}")
    if analysis["failed_gates"]:
        print("failed_gates=" + ",".join(analysis["failed_gates"]))
    if analysis["group_regressions"]:
        names = [item.get("group", "") for item in analysis["group_regressions"][:8]]
        print("regressed_groups=" + ",".join(names))
    if analysis["bucket_confusions"]:
        print("bucket_confusions:")
        for item in analysis["bucket_confusions"][:5]:
            print(
                "- "
                f"{item.get('target_bucket')}->{item.get('predicted_bucket')} "
                f"base={item.get('base_count')} cand={item.get('cand_count')} "
                f"avg_error={item.get('cand_avg_error')} "
                f"tags={item.get('top_tags')} groups={item.get('top_groups')} "
                f"examples={item.get('examples')}"
            )
    if analysis["antonym_group"]:
        print(f"antonym_group={analysis['antonym_group']}")
    else:
        print("antonym_group=(missing)")
    print(f"review_output={payload['review_output']}")
    print(f"review_rows={payload['review_rows']}")
    print(f"review_source_counts={payload['review_source_counts']}")
    print(f"review_status_counts={payload['review_summary']['status_counts']}")
    print(f"review_severity_counts={payload['review_summary']['severity_counts']}")
    print(f"review_validation_ok={payload['review_validation']['ok']}")
    print(f"review_validation_issues={payload['review_validation']['issue_count']}")
    print(f"todo_progress={todo['done']}/{todo['total']} ({todo['percent_done']}%)")
    print(f"todo_pending={todo['pending']}")
    if todo["pending_items"]:
        print("todo_next:")
        for item in todo["pending_items"][:5]:
            print(f"- [{item['section']}] {item['text']}")
    if health["warnings"]:
        print("warnings:")
        for item in health["warnings"]:
            print(f"- {item}")
    if health["problems"]:
        print("problems:")
        for item in health["problems"]:
            print(f"- {item}")


def markdown_lines(payload: dict[str, object]) -> list[str]:
    health = payload["health"]
    analysis = payload["analysis"]
    todo = payload["todo"]
    lines = [
        "# Nightly Next-Morning Triage",
        "",
        f"- status: `{payload['status']}`",
        f"- launchd_ok: `{health['ok']}`",
        f"- missed_latest_schedule: `{health['missed_latest_schedule']}`",
        f"- latest_run_log: `{health['latest_run_log']}`",
        f"- run_log_after_latest_schedule: `{health['run_log_after_latest_schedule']}`",
        f"- wrapper_loaded: `{health['wrapper_loaded']}`",
        f"- nightly_total_runs: `{health['nightly_total_runs']}`",
        f"- latest_real_report: `{health['latest_real_report']}`",
        f"- report: `{analysis['report']}`",
        f"- three_rounds_ok: `{analysis['three_rounds_ok']}`",
        f"- result: `{analysis['result']}`",
        f"- todo_progress: `{todo['done']}/{todo['total']} ({todo['percent_done']}%)`",
        f"- todo_pending: `{todo['pending']}`",
        "",
        "## Device",
        "",
        f"- requested: `{analysis['requested_device']}`",
        f"- actual_inferred: `{analysis['actual_device_inferred']}`",
        f"- gpu_or_mps: `{analysis['used_gpu_or_mps']}`",
        f"- cpu_fallback: `{analysis['cpu_fallback_seen']}`",
        "",
        "## Gates",
        "",
    ]
    failed = analysis.get("failed_gates") or []
    if failed:
        lines.extend(f"- `{item}`" for item in failed)
    else:
        lines.append("- no failed gates detected")

    lines.extend(["", "## Regressed Groups", ""])
    groups = analysis.get("group_regressions") or []
    if groups:
        for item in groups:
            reasons = ", ".join(item.get("reasons", []))
            lines.append(f"- `{item.get('group', '')}`: {reasons}")
    else:
        lines.append("- none")

    lines.extend(["", "## Bucket Confusions", ""])
    confusions = analysis.get("bucket_confusions") or []
    if confusions:
        for item in confusions[:10]:
            lines.append(
                "- "
                f"`{item.get('target_bucket', '')}->{item.get('predicted_bucket', '')}`: "
                f"base `{item.get('base_count', '')}`, cand `{item.get('cand_count', '')}`, "
                f"avg_error `{item.get('cand_avg_error', '')}`, "
                f"tags `{item.get('top_tags', '')}`, groups `{item.get('top_groups', '')}`, "
                f"examples `{item.get('examples', '')}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Antonym", ""])
    antonym = analysis.get("antonym_group")
    if antonym:
        lines.append(f"- `{antonym}`")
    else:
        lines.append("- antonym group missing")

    lines.extend(["", "## Goal TODO", ""])
    pending_items = todo.get("pending_items") or []
    if pending_items:
        for item in pending_items[:10]:
            lines.append(f"- `{item.get('section', '')}`: {item.get('text', '')}")
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Review Queue",
        "",
        f"- output: `{payload['review_output']}`",
        f"- rows: `{payload['review_rows']}`",
        f"- source_counts: `{payload['review_source_counts']}`",
        f"- status_counts: `{payload['review_summary']['status_counts']}`",
        f"- severity_counts: `{payload['review_summary']['severity_counts']}`",
        f"- validation_ok: `{payload['review_validation']['ok']}`",
        f"- validation_issues: `{payload['review_validation']['issue_count']}`",
        f"- written_now: `{payload['review_csv_written']}`",
        "",
        "## Warnings",
        "",
    ])
    warnings = health.get("warnings") or []
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")

    problems = health.get("problems") or []
    if problems:
        lines.extend(["", "## Problems", ""])
        lines.extend(f"- {item}" for item in problems)
    fatal = health.get("fatal_stderr_lines") or []
    if fatal:
        lines.extend(["", "## Fatal Stderr Lines", ""])
        lines.extend(f"- `{item}`" for item in fatal)
    return lines


def write_markdown(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(markdown_lines(payload)) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    payload = build_triage(args)
    if args.markdown_output:
        write_markdown(args.markdown_output, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
