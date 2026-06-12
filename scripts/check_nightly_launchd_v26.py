#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import plistlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
AGENT_ID = "com.guess.nightly-train-v26"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the local launchd nightly training installation.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--now", help="Override current local time, e.g. 2026-06-08T09:00:00.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def latest_report(nightly_root: Path, include_dry_run: bool) -> Path | None:
    reports = sorted((nightly_root / "reports").glob("nightly_promotion_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for report in reports:
        text = read_text(report)
        if include_dry_run or "DRY_RUN" not in text:
            return report
    return None


def latest_run_log(nightly_root: Path, include_dry_run: bool = False) -> Path | None:
    logs = sorted((nightly_root / "data" / "tmp").glob("nightly_train_v26_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        text = read_text(log)
        if include_dry_run or ("DRY_RUN" not in text and "dry-run" not in text):
            return log
    return None


def report_stamp(path: Path | None) -> str:
    if path is None:
        return ""
    match = re.search(r"(?:nightly_promotion|nightly_train_v26)_(\d{8}_\d{6})\.(?:md|log)$", path.name)
    return match.group(1) if match else path.stem


def mtime(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    return path.stat().st_mtime


def parse_now(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now()


def last_scheduled_time(now: datetime, hour: int | None, minute: int | None) -> datetime | None:
    if hour is None or minute is None:
        return None
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate


def run_log_start_time(path: Path | None) -> datetime | None:
    stamp = report_stamp(path)
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def has_stale_external_wrapper_error(stderr_log: Path, plist_mtime: float | None) -> bool:
    if not stderr_log.exists():
        return False
    text = read_text(stderr_log)
    if ".nightly/nightly_launcher.sh: Operation not permitted" not in text:
        return False
    if plist_mtime is None:
        return True
    return stderr_log.stat().st_mtime >= plist_mtime


def fatal_stderr_lines_since_install(stderr_log: Path, plist_mtime: float | None) -> list[str]:
    if plist_mtime is None or not stderr_log.exists() or stderr_log.stat().st_mtime < plist_mtime:
        return []
    fatal_tokens = (
        "operation not permitted",
        "permission denied",
        "no such file or directory",
        "command not found",
        "traceback",
        "metal",
        "runtimeerror",
        "failed",
        "error:",
    )
    lines = []
    for line in read_text(stderr_log).splitlines():
        lower = line.lower()
        if re.search(r"^grep: .+nightly_train_v26_\d{8}_\d{6}\.log: no such file or directory$", lower):
            continue
        if any(token in lower for token in fatal_tokens):
            lines.append(line.strip())
    return lines[-20:]


def check(root: Path, home: Path) -> dict[str, object]:
    root = root.resolve()
    plist_path = home / "Library" / "LaunchAgents" / f"{AGENT_ID}.plist"
    expected_wrapper = home / ".guess_nightly" / "nightly_launcher.sh"
    expected_script = root / "scripts" / "nightly_train_v26.sh"
    nightly_root = root / ".nightly"
    stderr_log = home / ".guess_nightly" / "logs" / "launchd_nightly_v26.err.log"
    stdout_log = home / ".guess_nightly" / "logs" / "launchd_nightly_v26.out.log"

    problems: list[str] = []
    warnings: list[str] = []
    plist: dict = {}
    if not plist_path.exists():
        problems.append(f"missing plist: {plist_path}")
    else:
        with plist_path.open("rb") as file:
            plist = plistlib.load(file)

    args = plist.get("ProgramArguments") or []
    wrapper_arg = Path(args[1]).expanduser() if len(args) >= 2 else None
    env = plist.get("EnvironmentVariables") or {}
    calendar = plist.get("StartCalendarInterval") or {}

    if wrapper_arg != expected_wrapper:
        problems.append(f"plist wrapper mismatch: {wrapper_arg} != {expected_wrapper}")
    if env.get("NIGHTLY_TOTAL_RUNS") != "3":
        problems.append(f"NIGHTLY_TOTAL_RUNS is {env.get('NIGHTLY_TOTAL_RUNS')!r}, expected '3'")
    if env.get("NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT") != "0.0":
        problems.append("missing antonym mid-recall gate env")
    if env.get("NIGHTLY_SUP_MIN_TAG_ROWS") != "antonym_mid:45":
        warnings.append(
            f"NIGHTLY_SUP_MIN_TAG_ROWS is {env.get('NIGHTLY_SUP_MIN_TAG_ROWS')!r}, expected 'antonym_mid:45'"
        )
    hour = calendar.get("Hour")
    minute = calendar.get("Minute")
    if hour != 23 or minute != 0:
        problems.append(f"schedule mismatch: {calendar}")

    wrapper_text = ""
    if not expected_wrapper.exists():
        problems.append(f"missing wrapper: {expected_wrapper}")
    else:
        wrapper_text = read_text(expected_wrapper)
        if str(expected_script) not in wrapper_text:
            problems.append("wrapper does not exec current repo nightly_train_v26.sh")
        stale_copy = str(home / ".guess_nightly" / "nightly_train_v26.sh")
        if stale_copy in wrapper_text:
            problems.append("wrapper points at stale copied nightly_train_v26.sh")
        if str(root) not in wrapper_text:
            problems.append("wrapper does not cd into current repo root")

    plist_mtime = mtime(plist_path)
    if has_stale_external_wrapper_error(stderr_log, plist_mtime):
        problems.append("latest launchd stderr still shows .nightly wrapper Operation not permitted after plist install")
    elif stderr_log.exists() and ".nightly/nightly_launcher.sh: Operation not permitted" in read_text(stderr_log):
        warnings.append("historical .nightly wrapper Operation-not-permitted error exists before latest install")
    fatal_stderr = fatal_stderr_lines_since_install(stderr_log, plist_mtime)
    if fatal_stderr:
        problems.append("launchd stderr has fatal-looking lines after current install")

    real_report = latest_report(nightly_root, include_dry_run=False)
    dry_report = latest_report(nightly_root, include_dry_run=True)
    run_log = latest_run_log(nightly_root, include_dry_run=False)
    now = datetime.now()
    last_schedule = last_scheduled_time(now, hour, minute)
    real_report_mtime = mtime(real_report)
    real_report_started_at = run_log_start_time(real_report)
    run_log_mtime = mtime(run_log)
    run_log_started_at = run_log_start_time(run_log)
    run_log_after_latest_schedule = (
        last_schedule is not None
        and run_log_started_at is not None
        and last_schedule <= run_log_started_at <= last_schedule + timedelta(hours=2)
    )
    missed_latest_schedule = (
        last_schedule is not None
        and plist_mtime is not None
        and plist_mtime < last_schedule.timestamp()
        and (real_report_started_at is None or real_report_started_at < last_schedule)
        and not run_log_after_latest_schedule
    )

    if real_report is None:
        warnings.append("no real nightly report found")
    elif plist_mtime is not None and real_report.stat().st_mtime < plist_mtime:
        warnings.append("latest real report predates current launchd install; wait for next 23:00 run")
    if run_log_after_latest_schedule and (real_report_started_at is None or real_report_started_at < last_schedule):
        warnings.append("latest scheduled 23:00 run appears to have started but no newer real report exists yet")
    if missed_latest_schedule:
        warnings.append("latest scheduled 23:00 run has passed but no newer real report was produced")

    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "plist": str(plist_path),
        "wrapper": str(expected_wrapper),
        "wrapper_loaded": str(wrapper_arg) if wrapper_arg else "",
        "schedule": {"hour": calendar.get("Hour"), "minute": calendar.get("Minute")},
        "last_scheduled_time": last_schedule.isoformat(timespec="seconds") if last_schedule else "",
        "missed_latest_schedule": missed_latest_schedule,
        "latest_run_log": str(run_log) if run_log else "",
        "latest_run_log_stamp": report_stamp(run_log),
        "latest_run_log_started_at": run_log_started_at.isoformat(timespec="seconds") if run_log_started_at else "",
        "run_log_after_latest_schedule": run_log_after_latest_schedule,
        "nightly_total_runs": env.get("NIGHTLY_TOTAL_RUNS"),
        "antonym_gate": env.get("NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT"),
        "sup_min_tag_rows": env.get("NIGHTLY_SUP_MIN_TAG_ROWS"),
        "stderr_log": str(stderr_log),
        "fatal_stderr_lines": fatal_stderr,
        "stdout_log": str(stdout_log),
        "latest_real_report": str(real_report) if real_report else "",
        "latest_real_stamp": report_stamp(real_report),
        "latest_real_started_at": real_report_started_at.isoformat(timespec="seconds") if real_report_started_at else "",
        "latest_report_including_dry_run": str(dry_report) if dry_report else "",
        "latest_report_including_dry_run_stamp": report_stamp(dry_report),
    }


def print_human(payload: dict[str, object]) -> None:
    print(f"ok={payload['ok']}")
    print(f"plist={payload['plist']}")
    print(f"wrapper_loaded={payload['wrapper_loaded']}")
    print(f"wrapper_expected={payload['wrapper']}")
    print(f"schedule={payload['schedule']}")
    print(f"last_scheduled_time={payload['last_scheduled_time']}")
    print(f"missed_latest_schedule={payload['missed_latest_schedule']}")
    print(f"latest_run_log={payload['latest_run_log']}")
    print(f"latest_run_log_stamp={payload['latest_run_log_stamp']}")
    print(f"latest_run_log_started_at={payload['latest_run_log_started_at']}")
    print(f"run_log_after_latest_schedule={payload['run_log_after_latest_schedule']}")
    print(f"nightly_total_runs={payload['nightly_total_runs']}")
    print(f"antonym_gate={payload['antonym_gate']}")
    print(f"sup_min_tag_rows={payload['sup_min_tag_rows']}")
    print(f"latest_real_report={payload['latest_real_report']}")
    print(f"latest_real_stamp={payload['latest_real_stamp']}")
    if payload["problems"]:
        print("problems:")
        for item in payload["problems"]:
            print(f"- {item}")
    if payload["fatal_stderr_lines"]:
        print("fatal_stderr_lines:")
        for item in payload["fatal_stderr_lines"]:
            print(f"- {item}")
    if payload["warnings"]:
        print("warnings:")
        for item in payload["warnings"]:
            print(f"- {item}")


def main() -> int:
    args = parse_args()
    if args.now:
        # Keep the public check() helper simple while making CLI tests deterministic.
        global datetime
        real_datetime = datetime

        class FixedDateTime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                parsed = parse_now(args.now)
                if tz is not None:
                    return parsed.replace(tzinfo=tz)
                return parsed

        datetime = FixedDateTime
    payload = check(args.root, args.home)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
