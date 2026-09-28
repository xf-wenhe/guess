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
CANONICAL_SUP_MIN_TAG_BUCKET_ROWS = (
    "same_category_mid@40-59:20,same_category_mid@60-79:12"
)
LEGACY_SUP_MIN_TAG_BUCKET_ROWS = (
    "same_category_mid@40-59:20,same_category_mid@60-79:12,"
    "hint_like_high@60-79:18,hint_like_high@80-100:18"
)
CANONICAL_SUP_BUCKET_BAND_HARD_NEG_REPEAT = "2"
LEGACY_SUP_BUCKET_BAND_HARD_NEG_REPEAT = "1"
CANONICAL_SUP_BUCKET_ONLY_TAGS = "same_category_but_far"
CANONICAL_SUP_MIDPOINT_BAND_LOW = "0.45"
CANONICAL_SUP_MIDPOINT_BAND_HIGH = "0.55"
LEGACY_SUP_MIDPOINT_BAND_LOW = "0.47"
LEGACY_SUP_MIDPOINT_BAND_HIGH = "0.53"
EXPECTED_CALIB_MIDPOINT_AUGMENT = {
    "NIGHTLY_CALIB_MIDPOINT_AUGMENT_RADIUS": "3.5",
    "NIGHTLY_CALIB_MIDPOINT_AUGMENT_STEPS": "2",
    "NIGHTLY_CALIB_MIDPOINT_AUGMENT_WEIGHT": "0.5",
}


def effective_sup_min_tag_bucket_rows(value: object) -> str:
    """Do not let a pre-canonicalization plist become the next report's expectation."""
    loaded = str(value or "").strip()
    if loaded == LEGACY_SUP_MIN_TAG_BUCKET_ROWS:
        return CANONICAL_SUP_MIN_TAG_BUCKET_ROWS
    return loaded


def effective_sup_bucket_band_hard_neg_repeat(value: object) -> str:
    """Mirror nightly_train_v26.sh when launchd still has the old repeat budget."""
    loaded = str(value or "").strip()
    if not loaded or loaded == LEGACY_SUP_BUCKET_BAND_HARD_NEG_REPEAT:
        return CANONICAL_SUP_BUCKET_BAND_HARD_NEG_REPEAT
    return loaded


def effective_sup_bucket_only_tags(value: object) -> str:
    """Mirror the nightly shell's bucket-only default when launchd omits it."""
    return str(value or "").strip() or CANONICAL_SUP_BUCKET_ONLY_TAGS


def effective_sup_midpoint_band(low: object, high: object) -> tuple[str, str]:
    """Mirror nightly_train_v26.sh when launchd still has either legacy bound."""
    loaded_low = str(low or "").strip()
    loaded_high = str(high or "").strip()
    if loaded_low == LEGACY_SUP_MIDPOINT_BAND_LOW or loaded_high == LEGACY_SUP_MIDPOINT_BAND_HIGH:
        return CANONICAL_SUP_MIDPOINT_BAND_LOW, CANONICAL_SUP_MIDPOINT_BAND_HIGH
    return loaded_low, loaded_high


def effective_calib_midpoint_augment(value: object, key: str) -> str:
    """Mirror nightly_train_v26.sh defaults when older plists omit the new keys."""
    loaded = str(value or "").strip()
    return loaded or EXPECTED_CALIB_MIDPOINT_AUGMENT[key]


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


def latest_partial_run_artifact(nightly_root: Path) -> Path | None:
    tmp_dir = nightly_root / "data" / "tmp"
    candidates = []
    for pattern in (
        "nightly_round_summary_*.txt",
        "nightly_build_stats_*.json",
        "nightly_train_stats_*.json",
    ):
        candidates.extend(tmp_dir.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def report_stamp(path: Path | None) -> str:
    if path is None:
        return ""
    match = re.search(r"(?:nightly_promotion|nightly_train_v26)_(\d{8}_\d{6})\.(?:md|log)$", path.name)
    if not match:
        match = re.search(
            r"(?:nightly_round_summary|nightly_build_stats|nightly_train_stats)_(\d{8}_\d{6})(?:_r\d+)?\.(?:txt|json)$",
            path.name,
        )
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
    expected_bucket_rows = CANONICAL_SUP_MIN_TAG_BUCKET_ROWS
    loaded_bucket_rows = str(env.get("NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS") or "").strip()
    if loaded_bucket_rows != expected_bucket_rows:
        warnings.append(
            "NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS is "
            f"{loaded_bucket_rows!r}, expected {expected_bucket_rows!r}"
        )
    effective_bucket_rows = effective_sup_min_tag_bucket_rows(loaded_bucket_rows)
    loaded_bucket_repeat = str(env.get("NIGHTLY_SUP_BUCKET_BAND_HARD_NEG_REPEAT") or "").strip()
    if loaded_bucket_repeat != CANONICAL_SUP_BUCKET_BAND_HARD_NEG_REPEAT:
        warnings.append(
            "NIGHTLY_SUP_BUCKET_BAND_HARD_NEG_REPEAT is "
            f"{loaded_bucket_repeat!r}, expected {CANONICAL_SUP_BUCKET_BAND_HARD_NEG_REPEAT!r}"
        )
    effective_bucket_repeat = effective_sup_bucket_band_hard_neg_repeat(loaded_bucket_repeat)
    loaded_bucket_only_tags = str(env.get("NIGHTLY_SUP_BUCKET_ONLY_TAGS") or "").strip()
    effective_bucket_only_tags = effective_sup_bucket_only_tags(loaded_bucket_only_tags)
    if env.get("NIGHTLY_SUP_COSENT_EXCLUDE_TAGS") != "antonym_mid":
        warnings.append(
            "NIGHTLY_SUP_COSENT_EXCLUDE_TAGS is "
            f"{env.get('NIGHTLY_SUP_COSENT_EXCLUDE_TAGS')!r}, expected 'antonym_mid'"
        )
    if env.get("NIGHTLY_SUP_MIDPOINT_TAGS") != "antonym_mid":
        warnings.append(
            "NIGHTLY_SUP_MIDPOINT_TAGS is "
            f"{env.get('NIGHTLY_SUP_MIDPOINT_TAGS')!r}, expected 'antonym_mid'"
        )
    if env.get("NIGHTLY_SUP_MIDPOINT_REPEAT_BOOST") != "2.0":
        warnings.append(
            "NIGHTLY_SUP_MIDPOINT_REPEAT_BOOST is "
            f"{env.get('NIGHTLY_SUP_MIDPOINT_REPEAT_BOOST')!r}, expected '2.0'"
        )
    loaded_midpoint_band_low = str(env.get("NIGHTLY_SUP_MIDPOINT_BAND_LOW") or "").strip()
    loaded_midpoint_band_high = str(env.get("NIGHTLY_SUP_MIDPOINT_BAND_HIGH") or "").strip()
    effective_midpoint_band_low, effective_midpoint_band_high = effective_sup_midpoint_band(
        loaded_midpoint_band_low,
        loaded_midpoint_band_high,
    )
    if loaded_midpoint_band_low != CANONICAL_SUP_MIDPOINT_BAND_LOW:
        warnings.append(
            "NIGHTLY_SUP_MIDPOINT_BAND_LOW is "
            f"{loaded_midpoint_band_low!r}, expected {CANONICAL_SUP_MIDPOINT_BAND_LOW!r}"
        )
    if loaded_midpoint_band_high != CANONICAL_SUP_MIDPOINT_BAND_HIGH:
        warnings.append(
            "NIGHTLY_SUP_MIDPOINT_BAND_HIGH is "
            f"{loaded_midpoint_band_high!r}, expected {CANONICAL_SUP_MIDPOINT_BAND_HIGH!r}"
        )
    if env.get("NIGHTLY_SUP_MIDPOINT_BAND_WEIGHT") != "4.0":
        warnings.append(
            "NIGHTLY_SUP_MIDPOINT_BAND_WEIGHT is "
            f"{env.get('NIGHTLY_SUP_MIDPOINT_BAND_WEIGHT')!r}, expected '4.0'"
        )
    if env.get("NIGHTLY_SUP_MIDPOINT_CENTER_WEIGHT") != "1.0":
        warnings.append(
            "NIGHTLY_SUP_MIDPOINT_CENTER_WEIGHT is "
            f"{env.get('NIGHTLY_SUP_MIDPOINT_CENTER_WEIGHT')!r}, expected '1.0'"
        )
    for key, expected in EXPECTED_CALIB_MIDPOINT_AUGMENT.items():
        if env.get(key) != expected:
            warnings.append(f"{key} is {env.get(key)!r}, expected {expected!r}")
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
    partial_run = latest_partial_run_artifact(nightly_root)
    now = datetime.now()
    last_schedule = last_scheduled_time(now, hour, minute)
    real_report_mtime = mtime(real_report)
    real_report_started_at = run_log_start_time(real_report)
    run_log_mtime = mtime(run_log)
    run_log_started_at = run_log_start_time(run_log)
    partial_run_started_at = run_log_start_time(partial_run)
    run_log_after_latest_schedule = (
        last_schedule is not None
        and run_log_started_at is not None
        and last_schedule <= run_log_started_at <= last_schedule + timedelta(hours=2)
    )
    partial_run_after_latest_schedule = (
        last_schedule is not None
        and partial_run_started_at is not None
        and last_schedule <= partial_run_started_at <= last_schedule + timedelta(hours=2)
    )
    missed_latest_schedule = (
        last_schedule is not None
        and plist_mtime is not None
        and plist_mtime < last_schedule.timestamp()
        and (real_report_started_at is None or real_report_started_at < last_schedule)
        and not run_log_after_latest_schedule
        and not partial_run_after_latest_schedule
    )

    if real_report is None:
        warnings.append("no real nightly report found")
    elif plist_mtime is not None and real_report.stat().st_mtime < plist_mtime:
        warnings.append("latest real report predates current launchd install; wait for next 23:00 run")
    if run_log_after_latest_schedule and (real_report_started_at is None or real_report_started_at < last_schedule):
        warnings.append("latest scheduled 23:00 run appears to have started but no newer real report exists yet")
    if partial_run_after_latest_schedule and not run_log_after_latest_schedule and (
        real_report_started_at is None or real_report_started_at < last_schedule
    ):
        warnings.append("latest scheduled 23:00 run produced partial nightly artifacts but no newer real report exists")
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
        "latest_partial_run_artifact": str(partial_run) if partial_run else "",
        "latest_partial_run_stamp": report_stamp(partial_run),
        "latest_partial_run_started_at": partial_run_started_at.isoformat(timespec="seconds") if partial_run_started_at else "",
        "partial_run_after_latest_schedule": partial_run_after_latest_schedule,
        "nightly_total_runs": env.get("NIGHTLY_TOTAL_RUNS"),
        "antonym_gate": env.get("NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT"),
        "sup_min_tag_rows": env.get("NIGHTLY_SUP_MIN_TAG_ROWS"),
        "sup_min_tag_bucket_rows": effective_bucket_rows,
        "sup_min_tag_bucket_rows_loaded": loaded_bucket_rows,
        "sup_bucket_band_hard_negative_repeat": effective_bucket_repeat,
        "sup_bucket_band_hard_negative_repeat_loaded": loaded_bucket_repeat,
        "sup_bucket_only_tags": effective_bucket_only_tags,
        "sup_bucket_only_tags_loaded": loaded_bucket_only_tags,
        "sup_min_angle_repeat_tag_buckets": env.get("NIGHTLY_SUP_MIN_ANGLE_REPEAT_TAG_BUCKETS"),
        "sup_cosent_exclude_tags": env.get("NIGHTLY_SUP_COSENT_EXCLUDE_TAGS"),
        "sup_cosine_exclude_tags": env.get("NIGHTLY_SUP_COSINE_EXCLUDE_TAGS"),
        "sup_midpoint_tags": env.get("NIGHTLY_SUP_MIDPOINT_TAGS"),
        "sup_midpoint_repeat_boost": env.get("NIGHTLY_SUP_MIDPOINT_REPEAT_BOOST"),
        "sup_midpoint_band_low": effective_midpoint_band_low,
        "sup_midpoint_band_high": effective_midpoint_band_high,
        "sup_midpoint_band_low_loaded": loaded_midpoint_band_low,
        "sup_midpoint_band_high_loaded": loaded_midpoint_band_high,
        "sup_midpoint_band_weight": env.get("NIGHTLY_SUP_MIDPOINT_BAND_WEIGHT"),
        "sup_midpoint_center_weight": env.get("NIGHTLY_SUP_MIDPOINT_CENTER_WEIGHT"),
        "sup_midpoint_objective_repeats": env.get("NIGHTLY_SUP_MIDPOINT_OBJECTIVE_REPEATS"),
        "calib_support_positive_target_low": env.get("NIGHTLY_CALIB_SUPPORT_POSITIVE_TARGET_LOW"),
        "calib_midpoint_augment_radius": effective_calib_midpoint_augment(
            env.get("NIGHTLY_CALIB_MIDPOINT_AUGMENT_RADIUS"),
            "NIGHTLY_CALIB_MIDPOINT_AUGMENT_RADIUS",
        ),
        "calib_midpoint_augment_steps": effective_calib_midpoint_augment(
            env.get("NIGHTLY_CALIB_MIDPOINT_AUGMENT_STEPS"),
            "NIGHTLY_CALIB_MIDPOINT_AUGMENT_STEPS",
        ),
        "calib_midpoint_augment_weight": effective_calib_midpoint_augment(
            env.get("NIGHTLY_CALIB_MIDPOINT_AUGMENT_WEIGHT"),
            "NIGHTLY_CALIB_MIDPOINT_AUGMENT_WEIGHT",
        ),
        "calib_midpoint_augment_radius_loaded": str(
            env.get("NIGHTLY_CALIB_MIDPOINT_AUGMENT_RADIUS") or ""
        ).strip(),
        "calib_midpoint_augment_steps_loaded": str(
            env.get("NIGHTLY_CALIB_MIDPOINT_AUGMENT_STEPS") or ""
        ).strip(),
        "calib_midpoint_augment_weight_loaded": str(
            env.get("NIGHTLY_CALIB_MIDPOINT_AUGMENT_WEIGHT") or ""
        ).strip(),
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
    print(f"latest_partial_run_artifact={payload['latest_partial_run_artifact']}")
    print(f"latest_partial_run_stamp={payload['latest_partial_run_stamp']}")
    print(f"latest_partial_run_started_at={payload['latest_partial_run_started_at']}")
    print(f"partial_run_after_latest_schedule={payload['partial_run_after_latest_schedule']}")
    print(f"nightly_total_runs={payload['nightly_total_runs']}")
    print(f"antonym_gate={payload['antonym_gate']}")
    print(f"sup_min_tag_rows={payload['sup_min_tag_rows']}")
    print(f"sup_bucket_only_tags={payload['sup_bucket_only_tags']}")
    print(f"sup_min_angle_repeat_tag_buckets={payload['sup_min_angle_repeat_tag_buckets']}")
    print(f"sup_cosent_exclude_tags={payload['sup_cosent_exclude_tags']}")
    print(f"sup_cosine_exclude_tags={payload['sup_cosine_exclude_tags']}")
    print(f"sup_midpoint_tags={payload['sup_midpoint_tags']}")
    print(f"sup_midpoint_repeat_boost={payload['sup_midpoint_repeat_boost']}")
    print(f"sup_midpoint_band_low={payload['sup_midpoint_band_low']}")
    print(f"sup_midpoint_band_high={payload['sup_midpoint_band_high']}")
    print(f"sup_midpoint_band_low_loaded={payload['sup_midpoint_band_low_loaded']}")
    print(f"sup_midpoint_band_high_loaded={payload['sup_midpoint_band_high_loaded']}")
    print(f"sup_midpoint_band_weight={payload['sup_midpoint_band_weight']}")
    print(f"sup_midpoint_center_weight={payload['sup_midpoint_center_weight']}")
    print(f"sup_midpoint_objective_repeats={payload['sup_midpoint_objective_repeats']}")
    print(f"calib_support_positive_target_low={payload['calib_support_positive_target_low']}")
    print(f"calib_midpoint_augment_radius={payload['calib_midpoint_augment_radius']}")
    print(f"calib_midpoint_augment_steps={payload['calib_midpoint_augment_steps']}")
    print(f"calib_midpoint_augment_weight={payload['calib_midpoint_augment_weight']}")
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
