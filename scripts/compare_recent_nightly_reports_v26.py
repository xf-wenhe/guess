#!/usr/bin/env python3
"""Compare recent semantic nightly reports without mutating artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import analyze_nightly_report_v26 as report_analyzer


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NIGHTLY_ROOT = ROOT / ".nightly"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nightly-root", default=str(DEFAULT_NIGHTLY_ROOT))
    parser.add_argument("--limit", type=int, default=7, help="Maximum reports to compare.")
    parser.add_argument("--include-dry-run", action="store_true", help="Include dry-run reports.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser.parse_args()


def normalize_root(path: str) -> Path:
    root = Path(path)
    if not root.is_absolute():
        root = ROOT / root
    return root


def choose_reports(nightly_root: Path, limit: int, include_dry_run: bool) -> list[Path]:
    reports: list[Path] = []
    for path in report_analyzer.iter_reports(nightly_root):
        text = report_analyzer.read_text(path)
        if not include_dry_run and "DRY_RUN" in text:
            continue
        reports.append(path)
        if len(reports) >= limit:
            break
    return reports


def best_round_number(summary: dict[str, Any]) -> str:
    best = summary.get("best_round")
    if isinstance(best, dict):
        return str(best.get("轮次") or best.get("round") or "")
    return ""


def sampling_for_round(summary: dict[str, Any], round_number: str) -> dict[str, str]:
    rows = summary.get("train_sampling")
    if not isinstance(rows, list):
        return {}
    if round_number:
        for item in rows:
            if isinstance(item, dict) and item.get("round") == round_number:
                return item
    for item in reversed(rows):
        if isinstance(item, dict):
            return item
    return {}


def compact_row(summary: dict[str, Any]) -> dict[str, Any]:
    best = summary.get("best_round") if isinstance(summary.get("best_round"), dict) else {}
    config = summary.get("config") if isinstance(summary.get("config"), dict) else {}
    antonym = summary.get("antonym_group") if isinstance(summary.get("antonym_group"), dict) else {}
    round_number = best_round_number(summary)
    sampling = sampling_for_round(summary, round_number)
    failed_gates = summary.get("failed_gates")
    if not isinstance(failed_gates, list):
        failed_gates = []

    return {
        "stamp": summary.get("stamp"),
        "report": summary.get("report"),
        "log": summary.get("log"),
        "result": summary.get("result"),
        "dry_run": summary.get("dry_run"),
        "three_rounds_ok": summary.get("three_rounds_ok"),
        "total_rounds_configured": summary.get("total_rounds_configured"),
        "rounds_observed": summary.get("rounds_observed"),
        "requested_device": summary.get("requested_device"),
        "actual_device_inferred": summary.get("actual_device_inferred"),
        "used_gpu_or_mps": summary.get("used_gpu_or_mps"),
        "cpu_fallback_seen": summary.get("cpu_fallback_seen"),
        "train_profile": config.get("train_profile"),
        "sup_rows": config.get("sup_rows"),
        "sup_loss_mode": config.get("sup_loss_mode"),
        "sup_min_tag_rows": config.get("sup_min_tag_rows"),
        "sup_cosent_exclude_tags": config.get("sup_cosent_exclude_tags"),
        "best_round": round_number,
        "best_stage": best.get("stage"),
        "best_cand_mae": best.get("cand_mae"),
        "best_cand_acc": best.get("cand_acc"),
        "best_accepted": best.get("accepted"),
        "failed_gates": failed_gates,
        "antonym_base_mae": antonym.get("base_mae"),
        "antonym_cand_mae": antonym.get("cand_mae"),
        "antonym_base_acc": antonym.get("base_acc"),
        "antonym_cand_acc": antonym.get("cand_acc"),
        "antonym_extra": antonym.get("extra"),
        "antonym_mid_rows": sampling.get("antonym_mid_rows"),
        "antonym_mid_examples_after_repeat": sampling.get("antonym_mid_examples_after_repeat"),
        "cosent_exclude_tags": sampling.get("cosent_exclude_tags"),
        "cosent_excluded_examples_after_repeat": sampling.get("cosent_excluded_examples_after_repeat"),
        "min_tag_rows": sampling.get("min_tag_rows"),
    }


def build_comparison(nightly_root: Path, limit: int, include_dry_run: bool) -> dict[str, Any]:
    reports = choose_reports(nightly_root, limit, include_dry_run)
    rows = [
        compact_row(report_analyzer.build_summary(path, nightly_root, include_dry_run))
        for path in reports
    ]
    return {
        "nightly_root": str(nightly_root),
        "limit": limit,
        "include_dry_run": include_dry_run,
        "report_count": len(rows),
        "reports": rows,
    }


def print_human(comparison: dict[str, Any]) -> None:
    print(f"nightly_root: {comparison['nightly_root']}")
    print(f"reports: {comparison['report_count']} (limit={comparison['limit']}, include_dry_run={comparison['include_dry_run']})")
    for row in comparison["reports"]:
        print(
            "\n"
            f"{row['stamp']} "
            f"rounds={row['rounds_observed']}/{row['total_rounds_configured']} "
            f"three_rounds_ok={row['three_rounds_ok']} "
            f"device={row['actual_device_inferred']} "
            f"gpu_or_mps={row['used_gpu_or_mps']} "
            f"fallback={row['cpu_fallback_seen']}"
        )
        print(
            "  best: "
            f"round={row['best_round']} stage={row['best_stage']} "
            f"mae={row['best_cand_mae']} acc={row['best_cand_acc']} "
            f"accepted={row['best_accepted']}"
        )
        print(
            "  config: "
            f"profile={row['train_profile']} rows={row['sup_rows']} "
            f"loss={row['sup_loss_mode']} min_tags={row['sup_min_tag_rows']} "
            f"cosent_exclude={row['sup_cosent_exclude_tags']}"
        )
        print(
            "  antonym: "
            f"mae={row['antonym_base_mae']}->{row['antonym_cand_mae']} "
            f"acc={row['antonym_base_acc']}->{row['antonym_cand_acc']} "
            f"extra={row['antonym_extra'] or '-'}"
        )
        print(
            "  sampling: "
            f"antonym_rows={row['antonym_mid_rows'] or '-'} "
            f"antonym_examples={row['antonym_mid_examples_after_repeat'] or '-'} "
            f"cosent_excluded={row['cosent_excluded_examples_after_repeat'] or '-'} "
            f"cosent_exclude_tags={row['cosent_exclude_tags'] or '-'}"
        )
        if row["failed_gates"]:
            print("  failed_gates: " + ", ".join(str(item) for item in row["failed_gates"]))


def main() -> int:
    args = parse_args()
    nightly_root = normalize_root(args.nightly_root)
    comparison = build_comparison(nightly_root, args.limit, args.include_dry_run)
    if args.json:
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
    else:
        print_human(comparison)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
