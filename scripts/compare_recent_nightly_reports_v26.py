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
        "sup_min_tag_bucket_rows": config.get("sup_min_tag_bucket_rows"),
        "calibration_eval_mode": config.get("calibration_eval_mode"),
        "base_guard_score_mode": config.get("base_guard_score_mode"),
        "calib_support_positive_target_low": config.get("calib_support_positive_target_low"),
        "calib_midpoint_augment_radius": config.get("calib_midpoint_augment_radius"),
        "calib_midpoint_augment_steps": config.get("calib_midpoint_augment_steps"),
        "calib_midpoint_augment_weight": config.get("calib_midpoint_augment_weight"),
        "sup_cosent_exclude_tags": config.get("sup_cosent_exclude_tags"),
        "sup_cosine_exclude_tags": config.get("sup_cosine_exclude_tags"),
        "best_round": round_number,
        "best_stage": best.get("stage"),
        "best_cand_mae": best.get("cand_mae"),
        "best_cand_acc": best.get("cand_acc"),
        "best_accepted": best.get("accepted"),
        "failed_gates": failed_gates,
        "gate_failure_counts": summary.get("gate_failure_counts"),
        "antonym_base_mae": antonym.get("base_mae"),
        "antonym_cand_mae": antonym.get("cand_mae"),
        "antonym_base_acc": antonym.get("base_acc"),
        "antonym_cand_acc": antonym.get("cand_acc"),
        "antonym_extra": antonym.get("extra"),
        "antonym_mid_rows": sampling.get("antonym_mid_rows"),
        "antonym_mid_examples_after_repeat": sampling.get("antonym_mid_examples_after_repeat"),
        "required_proxy_antonym_train_rows": sampling.get("required_proxy_antonym_train_rows"),
        "required_proxy_antonym_calib_rows": sampling.get("required_proxy_antonym_calib_rows"),
        "proxy_antonym_rows": sampling.get("proxy_antonym_rows"),
        "proxy_antonym_examples_after_repeat": sampling.get("proxy_antonym_examples_after_repeat"),
        "proxy_antonym_min_angle_repeat": sampling.get("proxy_antonym_min_angle_repeat"),
        "round_robin_original_min_batches": sampling.get("round_robin_original_min_batches"),
        "round_robin_target_batches_per_objective": sampling.get("round_robin_target_batches_per_objective"),
        "round_robin_protected_min_batches": sampling.get("round_robin_protected_min_batches"),
        "round_robin_padded_examples": sampling.get("round_robin_padded_examples"),
        "round_robin_noop_padded_examples": sampling.get("round_robin_noop_padded_examples"),
        "fit_steps_per_epoch": sampling.get("fit_steps_per_epoch"),
        "fit_warmup_steps": sampling.get("fit_warmup_steps"),
        "cosent_exclude_tags": sampling.get("cosent_exclude_tags"),
        "cosent_excluded_examples_after_repeat": sampling.get("cosent_excluded_examples_after_repeat"),
        "cosent_base_guard_enabled": sampling.get("cosent_base_guard_enabled"),
        "cosent_base_guard_weight": sampling.get("cosent_base_guard_weight"),
        "cosent_base_guard_margin": sampling.get("cosent_base_guard_margin"),
        "cosent_base_guard_protected_examples": sampling.get(
            "cosent_base_guard_protected_examples"
        ),
        "midpoint_base_guard_enabled": sampling.get("midpoint_base_guard_enabled"),
        "midpoint_base_guard_weight": sampling.get("midpoint_base_guard_weight"),
        "midpoint_base_guard_margin": sampling.get("midpoint_base_guard_margin"),
        "midpoint_base_guard_examples": sampling.get("midpoint_base_guard_examples"),
        "midpoint_base_guard_protected_examples": sampling.get(
            "midpoint_base_guard_protected_examples"
        ),
        "cosine_examples_after_repeat": sampling.get("cosine_examples_after_repeat"),
        "cosine_exclude_tags": sampling.get("cosine_exclude_tags"),
        "cosine_excluded_rows": sampling.get("cosine_excluded_rows"),
        "cosine_excluded_examples_after_repeat": sampling.get("cosine_excluded_examples_after_repeat"),
        "bucket_only_tags": sampling.get("bucket_only_tags"),
        "bucket_only_rows": sampling.get("bucket_only_rows"),
        "bucket_only_examples_after_repeat": sampling.get("bucket_only_examples_after_repeat"),
        "cosent_bucket_only_excluded_examples_after_repeat": sampling.get(
            "cosent_bucket_only_excluded_examples_after_repeat"
        ),
        "cosine_bucket_only_excluded_examples_after_repeat": sampling.get(
            "cosine_bucket_only_excluded_examples_after_repeat"
        ),
        "bucket_band_tags": sampling.get("bucket_band_tags"),
        "bucket_band_base_guard_enabled": sampling.get("bucket_band_base_guard_enabled"),
        "bucket_band_base_guard_weight": sampling.get("bucket_band_base_guard_weight"),
        "bucket_band_base_guard_margin": sampling.get("bucket_band_base_guard_margin"),
        "bucket_band_base_guard_protected_examples": sampling.get(
            "bucket_band_base_guard_protected_examples"
        ),
        "cosine_base_guard_enabled": sampling.get("cosine_base_guard_enabled"),
        "cosine_base_guard_weight": sampling.get("cosine_base_guard_weight"),
        "cosine_base_guard_margin": sampling.get("cosine_base_guard_margin"),
        "cosine_base_guard_protected_examples": sampling.get(
            "cosine_base_guard_protected_examples"
        ),
        "bucket_band_hard_negative_repeat": sampling.get("bucket_band_hard_negative_repeat"),
        "bucket_band_examples_after_repeat": sampling.get("bucket_band_examples_after_repeat"),
        "priority_antonym_calib_anchor_rows": sampling.get("priority_antonym_calib_anchor_rows"),
        "priority_antonym_calib_weight_rows": sampling.get("priority_antonym_calib_weight_rows"),
        "antonym_calib_anchor_weight": sampling.get("antonym_calib_anchor_weight"),
        "priority_antonym_calib_anchor_weight": sampling.get("priority_antonym_calib_anchor_weight"),
        "gold_to_calib_rows": sampling.get("gold_to_calib_rows"),
        "gold_to_calib_weight": sampling.get("gold_to_calib_weight"),
        "min_tag_rows": sampling.get("min_tag_rows"),
        "min_tag_bucket_rows": sampling.get("min_tag_bucket_rows"),
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
            f"bucket_min_tags={row['sup_min_tag_bucket_rows'] or '-'} "
            f"calib_support_low={row['calib_support_positive_target_low'] or '-'} "
            f"calib_midpoint={row['calib_midpoint_augment_radius'] or '-'}/"
            f"{row['calib_midpoint_augment_steps'] or '-'}/"
            f"{row['calib_midpoint_augment_weight'] or '-'} "
            f"calibration_eval={row['calibration_eval_mode'] or '-'} "
            f"base_guard={row['base_guard_score_mode'] or '-'} "
            f"cosent_exclude={row['sup_cosent_exclude_tags']} "
            f"cosine_exclude={row['sup_cosine_exclude_tags'] or '-'}"
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
            f"proxy_train={row['required_proxy_antonym_train_rows'] or '-'} "
            f"proxy_calib={row['required_proxy_antonym_calib_rows'] or '-'} "
            f"proxy_examples={row['proxy_antonym_examples_after_repeat'] or '-'} "
            f"cosent_excluded={row['cosent_excluded_examples_after_repeat'] or '-'} "
            f"cosent_exclude_tags={row['cosent_exclude_tags'] or '-'} "
            f"cosent_base_guard={row['cosent_base_guard_enabled'] or '-'} "
            f"cosent_guard_margin={row['cosent_base_guard_margin'] or '-'} "
            f"cosent_guard_protected={row['cosent_base_guard_protected_examples'] or '-'} "
            f"midpoint_base_guard={row['midpoint_base_guard_enabled'] or '-'} "
            f"midpoint_guard_margin={row['midpoint_base_guard_margin'] or '-'} "
            f"midpoint_guard_protected={row['midpoint_base_guard_protected_examples'] or '-'} "
            f"cosine_examples={row['cosine_examples_after_repeat'] or '-'} "
            f"cosine_excluded={row['cosine_excluded_examples_after_repeat'] or '-'} "
            f"cosine_exclude_tags={row['cosine_exclude_tags'] or '-'} "
            f"bucket_only={row['bucket_only_tags'] or '-'} "
            f"bucket_only_examples={row['bucket_only_examples_after_repeat'] or '-'} "
            f"bucket_only_excluded=cosent:{row['cosent_bucket_only_excluded_examples_after_repeat'] or '-'},"
            f"cosine:{row['cosine_bucket_only_excluded_examples_after_repeat'] or '-'} "
            f"base_bucket_guard={row['bucket_band_base_guard_enabled'] or '-'} "
            f"guard_margin={row['bucket_band_base_guard_margin'] or '-'} "
            f"guard_protected={row['bucket_band_base_guard_protected_examples'] or '-'} "
            f"cosine_base_guard={row['cosine_base_guard_enabled'] or '-'} "
            f"cosine_guard_margin={row['cosine_base_guard_margin'] or '-'} "
            f"cosine_guard_protected={row['cosine_base_guard_protected_examples'] or '-'} "
            f"bucket_band_hard_neg_repeat={row['bucket_band_hard_negative_repeat'] or '-'} "
            f"bucket_band_examples={row['bucket_band_examples_after_repeat'] or '-'} "
            f"rr_batches={row['round_robin_target_batches_per_objective'] or '-'} "
            f"fit_steps={row['fit_steps_per_epoch'] or '-'} "
            f"fit_warmup={row['fit_warmup_steps'] or '-'} "
            f"rr_padded={row['round_robin_padded_examples'] or '-'} "
            f"rr_noop_padded={row['round_robin_noop_padded_examples'] or '-'} "
            f"min_tag_rows={row['min_tag_rows'] or '-'} "
            f"min_tag_bucket_rows={row['min_tag_bucket_rows'] or '-'}"
        )
        print(
            "  antonym_calib: "
            f"gold_rows={row['gold_to_calib_rows'] or '-'} "
            f"gold_weight={row['gold_to_calib_weight'] or '-'} "
            f"priority_rows={row['priority_antonym_calib_anchor_rows'] or '-'} "
            f"priority_weight_rows={row['priority_antonym_calib_weight_rows'] or '-'} "
            f"base_weight={row['antonym_calib_anchor_weight'] or '-'} "
            f"priority_weight={row['priority_antonym_calib_anchor_weight'] or '-'}"
        )
        if row["failed_gates"]:
            print("  failed_gates: " + ", ".join(str(item) for item in row["failed_gates"]))
            if row.get("gate_failure_counts"):
                print("  gate_failure_counts: " + str(row["gate_failure_counts"]))


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
