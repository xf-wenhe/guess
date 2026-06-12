#!/usr/bin/env python3
"""Summarize the latest semantic nightly report without mutating artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NIGHTLY_ROOT = ROOT / ".nightly"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nightly-root", default=str(DEFAULT_NIGHTLY_ROOT))
    parser.add_argument("--report", help="Specific nightly_promotion_*.md report to analyze.")
    parser.add_argument("--include-dry-run", action="store_true", help="Allow selecting dry-run reports.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def report_stamp(path: Path) -> str:
    match = re.search(r"nightly_promotion_(\d{8}_\d{6})\.md$", path.name)
    return match.group(1) if match else ""


def iter_reports(nightly_root: Path) -> Iterable[Path]:
    reports_dir = nightly_root / "reports"
    return sorted(reports_dir.glob("nightly_promotion_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def choose_report(nightly_root: Path, explicit: str | None, include_dry_run: bool) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise SystemExit(f"report not found: {path}")
        return path

    for path in iter_reports(nightly_root):
        text = read_text(path)
        if include_dry_run or "DRY_RUN" not in text:
            return path
    raise SystemExit(f"no nightly report found under {nightly_root / 'reports'}")


def find_log(nightly_root: Path, stamp: str) -> Path | None:
    if not stamp:
        return None
    path = nightly_root / "data" / "tmp" / f"nightly_train_v26_{stamp}.log"
    return path if path.exists() else None


def parse_key_value_table(text: str, title: str) -> dict[str, str]:
    marker = f"## {title}"
    start = text.find(marker)
    if start < 0:
        return {}
    section = text[start:].split("\n## ", 1)[0]
    data: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2 or cells[0] in {"item", "gate"}:
            continue
        data[cells[0]] = cells[1]
    return data


def parse_rounds(text: str) -> list[dict[str, str]]:
    marker = "## 各轮结果"
    start = text.find(marker)
    if start < 0:
        return []
    section = text[start:].split("\n## ", 1)[0]
    rounds: list[dict[str, str]] = []
    headers: list[str] = []
    for line in section.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not headers:
            headers = cells
            continue
        if len(cells) == len(headers):
            rounds.append(dict(zip(headers, cells)))
    return rounds


def parse_group_sections(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in re.split(r"\n## ", text):
        if not section.startswith(("拒绝诊断", "分组指标")):
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


def parse_bucket_confusion_sections(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in re.split(r"\n### ", text):
        if not section.startswith("校准桶错分 Top"):
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


def parse_train_sampling_sections(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in re.split(r"\n## ", text):
        if not section.startswith("实际训练抽样 Round "):
            continue
        title = section.splitlines()[0].strip()
        round_match = re.search(r"Round\s+(\d+)", title)
        row: dict[str, str] = {"round": round_match.group(1) if round_match else ""}
        for line in section.splitlines():
            if not line.startswith("|") or "---" in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 2 or cells[0] in {"item", "tag"}:
                continue
            row[cells[0]] = cells[1]
        rows.append(row)
    return rows


def parse_result(text: str) -> str:
    match = re.search(r"\*\*结果\*\*:\s*([^\n]+)", text)
    return match.group(1).strip() if match else "unknown"


def parse_total_rounds(text: str) -> int | None:
    match = re.search(r"\*\*总轮次\*\*:\s*(\d+)", text)
    return int(match.group(1)) if match else None


def parse_log_devices(log_text: str) -> dict[str, object]:
    candidates: list[str] = []
    requested = "unknown"
    for pattern in (
        r"\bdevice=([A-Za-z0-9_:-]+)",
        r"\bSEM_DEVICE=([A-Za-z0-9_:-]+)",
        r"\bTRAIN_DEVICE=([A-Za-z0-9_:-]+)",
        r"using device[:=]\s*([A-Za-z0-9_:-]+)",
    ):
        for match in re.finditer(pattern, log_text, re.IGNORECASE):
            value = match.group(1).lower()
            candidates.append(value)
            if "TRAIN_DEVICE" in match.group(0):
                requested = value

    fallback = "retry with SEM_DEVICE=cpu" in log_text or "ACCELERATE_USE_CPU=true" in log_text
    actual = "unknown"
    for value in candidates:
        if value in {"cuda", "mps", "cpu"}:
            actual = value
    lower = log_text.lower()
    if actual == "unknown":
        if re.search(r"\bcuda\b", lower):
            actual = "cuda"
        elif re.search(r"\bmps\b|\bmetal\b", lower):
            actual = "mps"
        elif re.search(r"\bcpu\b", lower):
            actual = "cpu"
    return {
        "device_mentions": candidates[-20:],
        "requested_device_inferred": requested,
        "actual_device_inferred": actual,
        "used_gpu_or_mps": actual in {"cuda", "mps"},
        "cpu_fallback_seen": fallback,
    }


def parse_log_failures(log_text: str) -> list[str]:
    lines: list[str] = []
    for line in log_text.splitlines():
        lower = line.lower()
        if any(token in lower for token in ("error", "failed", "traceback", "timeout", "rejected", "no accepted")):
            lines.append(line.strip())
    return lines[-20:]


def as_float(value: str | None) -> float | None:
    if value is None or value in {"", "-"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_gate_status(log_text: str) -> dict[str, object]:
    names = (
        "mae_ok",
        "acc_ok",
        "raw_mae_no_degrade",
        "raw_acc_no_degrade",
        "cal_mae_no_degrade",
        "cal_acc_no_degrade",
        "no_degrade_all",
        "strict_improve",
        "hard_negative_ok",
        "synonym_recall_ok",
        "antonym_mid_recall_ok",
        "antonym_strict_mid_recall_ok",
        "regression_ok",
        "accepted",
    )
    status: dict[str, bool] = {}
    pattern = re.compile(rf"^({'|'.join(names)})=(True|False|true|false)$", re.MULTILINE)
    for match in pattern.finditer(log_text):
        status[match.group(1)] = match.group(2).lower() == "true"

    primary = (
        "mae_ok",
        "acc_ok",
        "raw_mae_no_degrade",
        "raw_acc_no_degrade",
        "cal_mae_no_degrade",
        "cal_acc_no_degrade",
        "no_degrade_all",
        "strict_improve",
        "hard_negative_ok",
        "synonym_recall_ok",
        "antonym_mid_recall_ok",
        "antonym_strict_mid_recall_ok",
        "regression_ok",
    )
    failed = [name for name in primary if status.get(name) is False]
    return {"gate_status": status, "failed_gates": failed}


def parse_group_regressions(groups: list[dict[str, str]]) -> list[dict[str, object]]:
    regressions: list[dict[str, object]] = []
    for row in groups:
        base_mae = as_float(row.get("base_mae"))
        cand_mae = as_float(row.get("cand_mae"))
        base_acc = as_float(row.get("base_acc"))
        cand_acc = as_float(row.get("cand_acc"))
        reasons: list[str] = []
        if base_mae is not None and cand_mae is not None and cand_mae > base_mae:
            reasons.append(f"mae +{cand_mae - base_mae:.4f}")
        if base_acc is not None and cand_acc is not None and cand_acc < base_acc:
            reasons.append(f"acc {cand_acc - base_acc:.2f}")
        if reasons:
            regressions.append({"group": row.get("group", ""), "reasons": reasons, "row": row})
    return regressions


def build_summary(report: Path, nightly_root: Path, include_dry_run: bool) -> dict[str, object]:
    text = read_text(report)
    stamp = report_stamp(report)
    log_path = find_log(nightly_root, stamp)
    log_text = read_text(log_path) if log_path else ""
    device_text = "\n".join(part for part in (log_text, text) if part)
    config = parse_key_value_table(text, "运行配置")
    gates = parse_key_value_table(text, "晋升门控")
    rounds = parse_rounds(text)
    groups = parse_group_sections(text)
    bucket_confusions = parse_bucket_confusion_sections(text)
    train_sampling = parse_train_sampling_sections(text)
    result = parse_result(text)
    dry_run = "DRY_RUN" in text or config.get("dry_run") == "1"

    best_round = None
    best_mae = None
    for item in rounds:
        mae = as_float(item.get("cand_mae"))
        if mae is None:
            continue
        if best_mae is None or mae < best_mae:
            best_mae = mae
            best_round = item

    device = parse_log_devices(device_text)
    gate_status = parse_gate_status(log_text)
    failures = parse_log_failures(log_text)
    total_rounds = parse_total_rounds(text)
    observed_rounds = len(rounds)

    return {
        "report": str(report),
        "log": str(log_path) if log_path else None,
        "stamp": stamp,
        "dry_run": dry_run,
        "result": result,
        "total_rounds_configured": total_rounds,
        "rounds_observed": observed_rounds,
        "three_rounds_ok": total_rounds == 3 and observed_rounds == 3,
        "requested_device": config.get("requested_device") or device.get("requested_device_inferred", "unknown"),
        **device,
        **gate_status,
        "config": config,
        "gates": gates,
        "rounds": rounds,
        "best_round": best_round,
        "groups": groups,
        "train_sampling": train_sampling,
        "group_regressions": parse_group_regressions(groups),
        "bucket_confusions": bucket_confusions,
        "antonym_group": next((row for row in groups if row.get("group") == "antonym"), None),
        "recent_failure_lines": failures,
        "selected_with_include_dry_run": include_dry_run,
    }


def print_human(summary: dict[str, object]) -> None:
    print(f"报告: {summary['report']}")
    print(f"日志: {summary['log'] or '(missing)'}")
    print(f"结果: {summary['result']}")
    print(f"dry_run: {summary['dry_run']}")
    print(f"轮次: configured={summary['total_rounds_configured']} observed={summary['rounds_observed']} three_rounds_ok={summary['three_rounds_ok']}")
    print(
        "设备: "
        f"requested={summary['requested_device']} "
        f"actual_inferred={summary['actual_device_inferred']} "
        f"gpu_or_mps={summary['used_gpu_or_mps']} "
        f"cpu_fallback={summary['cpu_fallback_seen']}"
    )

    best = summary.get("best_round")
    if isinstance(best, dict):
        print(
            "最佳轮次: "
            f"round={best.get('轮次')} stage={best.get('stage')} "
            f"cand_mae={best.get('cand_mae')} cand_acc={best.get('cand_acc')} "
            f"accepted={best.get('accepted')}"
        )
    else:
        print("最佳轮次: (no numeric candidate metrics)")

    gates = summary.get("gates") or {}
    if isinstance(gates, dict) and gates:
        print(
            "门控: "
            f"mae>={gates.get('min_cal_mae_improvement')} "
            f"acc>={gates.get('min_cal_bucket_acc_improvement')} "
            f"antonym_mid>={gates.get('min_antonym_mid_recall_improvement')} "
            f"regression={gates.get('regression_gate')}"
        )

    failed_gates = summary.get("failed_gates") or []
    if failed_gates:
        print("失败门控: " + ", ".join(str(item) for item in failed_gates))
    elif summary.get("gate_status"):
        print("失败门控: 未发现失败门控")

    group_regressions = summary.get("group_regressions") or []
    if group_regressions:
        print("退化分组:")
        for item in group_regressions[:8]:
            print(f"- {item.get('group')}: {', '.join(item.get('reasons', []))}")

    bucket_confusions = summary.get("bucket_confusions") or []
    if bucket_confusions:
        print("桶错分 Top:")
        for item in bucket_confusions[:8]:
            print(
                "- "
                f"{item.get('target_bucket')} -> {item.get('predicted_bucket')}: "
                f"cand_count={item.get('cand_count')} "
                f"avg_error={item.get('cand_avg_error')} "
                f"tags={item.get('top_tags')} "
                f"groups={item.get('top_groups')} "
                f"examples={item.get('examples')}"
            )

    train_sampling = summary.get("train_sampling") or []
    if train_sampling:
        print("实际训练抽样:")
        for item in train_sampling[:8]:
            print(
                "- "
                f"round={item.get('round')} "
                f"antonym_mid_rows={item.get('antonym_mid_rows', '-')} "
                f"antonym_mid_examples={item.get('antonym_mid_examples_after_repeat', '-')} "
                f"min_tag_rows={item.get('min_tag_rows', '-')}"
            )

    antonym = summary.get("antonym_group")
    if isinstance(antonym, dict):
        print(f"反义词组: {antonym}")
    else:
        print("反义词组: report 中未找到 antonym 分组")

    failures = summary.get("recent_failure_lines") or []
    if failures:
        print("最近失败/拒绝线索:")
        for line in failures[-8:]:
            print(f"- {line}")


def main() -> int:
    args = parse_args()
    nightly_root = Path(args.nightly_root)
    if not nightly_root.is_absolute():
        nightly_root = ROOT / nightly_root
    report = choose_report(nightly_root, args.report, args.include_dry_run)
    summary = build_summary(report, nightly_root, args.include_dry_run)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
