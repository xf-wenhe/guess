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


def launchd_log_text(health: dict[str, object]) -> str:
    texts: list[str] = []
    for key in ("stdout_log", "stderr_log"):
        raw_path = str(health.get(key) or "")
        if not raw_path:
            continue
        path = Path(raw_path)
        candidates = [path, *sorted(path.parent.glob(path.name + ".*.bak"))]
        for candidate in candidates:
            if candidate.exists():
                texts.append(candidate.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texts)


def launchd_device_evidence(health: dict[str, object]) -> dict[str, object]:
    return analyze_nightly_report_v26.parse_log_devices(launchd_log_text(health))


def parse_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_tag_bucket_spec(spec: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in spec.split(","):
        part = item.strip()
        if not part or ":" not in part:
            continue
        key, raw_value = part.rsplit(":", 1)
        key = key.strip()
        value = parse_int(raw_value)
        if key and value is not None:
            result[key] = value
    return result


def parse_tag_bucket_json(value: object) -> dict[str, int]:
    if isinstance(value, dict):
        raw = value
    else:
        text = str(value or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        raw = parsed

    result: dict[str, int] = {}
    for key, item in raw.items():
        parsed_value = parse_int(item)
        if parsed_value is not None:
            result[str(key)] = parsed_value
    return result


CALIBRATION_REPORT_FIELDS = {
    "calib_midpoint_augment_radius": (
        "calib_midpoint_augment_radius_loaded",
        "NIGHTLY_CALIB_MIDPOINT_AUGMENT_RADIUS",
    ),
    "calib_midpoint_augment_steps": (
        "calib_midpoint_augment_steps_loaded",
        "NIGHTLY_CALIB_MIDPOINT_AUGMENT_STEPS",
    ),
    "calib_midpoint_augment_weight": (
        "calib_midpoint_augment_weight_loaded",
        "NIGHTLY_CALIB_MIDPOINT_AUGMENT_WEIGHT",
    ),
}

PARTITION_REPORT_FIELDS = (
    "eval_antonym_rows",
    "eval_holdout_antonym_rows",
    "eval_non_holdout_antonym_rows",
    "unexpected_train_calib_symmetric_overlap",
)

ROUND_ROBIN_REPORT_FIELDS = (
    "objective_count",
    "round_robin_steps_per_epoch",
    "round_robin_original_min_batches",
    "round_robin_target_batches_per_objective",
    "round_robin_protected_min_batches",
    "round_robin_padded_examples",
    "round_robin_noop_padded_examples",
)

SENTENCE_TRANSFORMER_FIT_REPORT_FIELDS = (
    "fit_steps_per_epoch",
    "fit_warmup_steps",
)
SENTENCE_TRANSFORMER_FIT_BACKEND = "SentenceTransformer.fit"


def calibration_value_matches(key: str, expected: str, actual: str) -> bool:
    try:
        if key.endswith("_steps"):
            return int(actual) == int(expected)
        return abs(float(actual) - float(expected)) <= 1e-9
    except (TypeError, ValueError):
        return actual == expected


def semantic_strategy_checks(health: dict[str, object], analysis: dict[str, object]) -> dict[str, object]:
    warnings = [str(item) for item in health.get("warnings", [])]
    report_predates_install = any("predates current launchd install" in item for item in warnings)
    expected_exclude = str(health.get("sup_cosent_exclude_tags") or "").strip()
    expected_cosine_exclude = str(health.get("sup_cosine_exclude_tags") or "").strip()
    expected_midpoint = str(health.get("sup_midpoint_tags") or "antonym_mid").strip()
    expected_bucket_rows = str(health.get("sup_min_tag_bucket_rows") or "").strip()
    expected_bucket_repeat = str(
        health.get("sup_bucket_band_hard_negative_repeat") or ""
    ).strip()
    expected_midpoint_band = {
        "sup_midpoint_band_low": str(health.get("sup_midpoint_band_low") or "").strip(),
        "sup_midpoint_band_high": str(health.get("sup_midpoint_band_high") or "").strip(),
    }
    expected_support_low = str(health.get("calib_support_positive_target_low") or "").strip()
    expected_calib = {
        key: str(health.get(key) or "").strip()
        for key in CALIBRATION_REPORT_FIELDS
    }
    loaded_calib = {
        loaded_key: str(health.get(loaded_key) or "").strip()
        for loaded_key in (item[0] for item in CALIBRATION_REPORT_FIELDS.values())
    }
    rows = analysis.get("train_sampling") or []
    issues: list[str] = []
    calibration_report_values: dict[str, str] = {}
    calibration_report_verified = False
    midpoint_band_report_values: dict[str, str] = {}
    midpoint_band_report_verified = False
    partition_report_values: list[dict[str, object]] = []
    partition_report_verified = False
    round_robin_report_values: list[dict[str, object]] = []
    round_robin_report_verified = False
    fit_report_values: list[dict[str, object]] = []
    fit_report_verified = False

    def make_result(
        *,
        ok: bool,
        skipped: bool,
        reason: str,
        missing_evidence: list[str] | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "ok": ok,
            "skipped": skipped,
            "reason": reason,
            "expected_cosent_exclude_tags": expected_exclude,
            "expected_cosine_exclude_tags": expected_cosine_exclude,
            "expected_midpoint_tags": expected_midpoint,
            "expected_min_tag_bucket_rows": expected_bucket_rows,
            "expected_bucket_band_hard_negative_repeat": expected_bucket_repeat,
            "expected_midpoint_band_low": expected_midpoint_band["sup_midpoint_band_low"],
            "expected_midpoint_band_high": expected_midpoint_band["sup_midpoint_band_high"],
            "expected_calib_support_positive_target_low": expected_support_low,
            "expected_calib_midpoint_augment_radius": expected_calib[
                "calib_midpoint_augment_radius"
            ],
            "expected_calib_midpoint_augment_steps": expected_calib[
                "calib_midpoint_augment_steps"
            ],
            "expected_calib_midpoint_augment_weight": expected_calib[
                "calib_midpoint_augment_weight"
            ],
            "calib_midpoint_augment_radius_loaded": loaded_calib[
                "calib_midpoint_augment_radius_loaded"
            ],
            "calib_midpoint_augment_steps_loaded": loaded_calib[
                "calib_midpoint_augment_steps_loaded"
            ],
            "calib_midpoint_augment_weight_loaded": loaded_calib[
                "calib_midpoint_augment_weight_loaded"
            ],
            "calib_midpoint_report_verified": calibration_report_verified,
            "calib_midpoint_report_values": calibration_report_values,
            "midpoint_band_report_verified": midpoint_band_report_verified,
            "midpoint_band_report_values": midpoint_band_report_values,
            "partition_report_verified": partition_report_verified,
            "partition_report_values": partition_report_values,
            "round_robin_report_verified": round_robin_report_verified,
            "round_robin_report_values": round_robin_report_values,
            "fit_report_verified": fit_report_verified,
            "fit_report_values": fit_report_values,
            "issues": issues,
        }
        if missing_evidence is not None:
            result["missing_evidence"] = missing_evidence
        return result

    if report_predates_install:
        return make_result(
            ok=True,
            skipped=True,
            reason="latest real report predates current launchd install",
        )

    if all(expected_calib.values()) and analysis.get("three_rounds_ok"):
        launchd_mismatches = []
        for report_key, (loaded_key, env_key) in CALIBRATION_REPORT_FIELDS.items():
            loaded_value = loaded_calib[loaded_key]
            expected_code_value = str(
                check_nightly_launchd_v26.EXPECTED_CALIB_MIDPOINT_AUGMENT[env_key]
            )
            if loaded_value and not calibration_value_matches(
                report_key, expected_code_value, loaded_value
            ):
                launchd_mismatches.append(
                    f"{loaded_key}={loaded_value!r} != code default {expected_code_value!r}"
                )
        if launchd_mismatches:
            return make_result(
                ok=True,
                skipped=True,
                reason="launchd midpoint calibration settings differ from current code defaults",
            )

        report_config = analysis.get("config")
        if not isinstance(report_config, dict):
            report_config = {}
        missing_calibration = [
            key
            for key in expected_calib
            if not str(report_config.get(key) or "").strip()
        ]
        if missing_calibration:
            return make_result(
                ok=True,
                skipped=True,
                reason="latest real report lacks midpoint calibration evidence",
                missing_evidence=missing_calibration,
            )
        calibration_report_values = {
            key: str(report_config.get(key) or "").strip()
            for key in expected_calib
        }
        for key, expected_value in expected_calib.items():
            actual_value = calibration_report_values[key]
            if not calibration_value_matches(key, expected_value, actual_value):
                issues.append(
                    f"report config {key}={actual_value!r} != effective launchd value {expected_value!r}"
                )
        calibration_report_verified = not any(
            issue.startswith("report config calib_midpoint_augment_") for issue in issues
        )

    if all(expected_midpoint_band.values()) and analysis.get("three_rounds_ok"):
        report_config = analysis.get("config")
        if not isinstance(report_config, dict):
            report_config = {}
        missing_band = [
            key for key in expected_midpoint_band if not str(report_config.get(key) or "").strip()
        ]
        if missing_band:
            return make_result(
                ok=True,
                skipped=True,
                reason="latest real report lacks midpoint band evidence",
                missing_evidence=missing_band,
            )
        midpoint_band_report_values = {
            key: str(report_config.get(key) or "").strip()
            for key in expected_midpoint_band
        }
        for key, expected_value in expected_midpoint_band.items():
            actual_value = midpoint_band_report_values[key]
            if not calibration_value_matches(key, expected_value, actual_value):
                issues.append(
                    f"report config {key}={actual_value!r} != effective launchd value {expected_value!r}"
                )
        midpoint_band_report_verified = not any(
            issue.startswith("report config sup_midpoint_band_") for issue in issues
        )

    if rows:
        required_cosine_evidence = {
            "cosine_examples_after_repeat",
            "cosine_exclude_tags",
            "cosine_excluded_rows",
            "cosine_excluded_examples_after_repeat",
            "bucket_band_tags",
            "bucket_band_examples_after_repeat",
        }
        if expected_bucket_repeat and analysis.get("three_rounds_ok"):
            required_cosine_evidence.add("bucket_band_hard_negative_repeat")
        missing_evidence = sorted(
            key for key in required_cosine_evidence
            if any(key not in row for row in rows)
        )
        if missing_evidence:
            return make_result(
                ok=True,
                skipped=True,
                reason="latest real report lacks cosine/bucket training evidence",
                missing_evidence=missing_evidence,
            )

    if expected_cosine_exclude == "":
        if not rows:
            issues.append("missing train_sampling rows in latest report")
        for row in rows:
            round_id = row.get("round", "?")
            total_examples = parse_int(row.get("train_examples_after_repeat"))
            cosent_examples = parse_int(row.get("cosent_examples_after_repeat"))
            cosent_excluded_examples = parse_int(row.get("cosent_excluded_examples_after_repeat"))
            cosine_examples = parse_int(row.get("cosine_examples_after_repeat"))
            tags = str(row.get("cosine_exclude_tags") or "")
            excluded_rows = parse_int(row.get("cosine_excluded_rows"))
            excluded_examples = parse_int(row.get("cosine_excluded_examples_after_repeat"))
            if total_examples is not None and cosine_examples is not None and excluded_examples is not None:
                if cosine_examples + excluded_examples != total_examples:
                    issues.append(
                        f"round {round_id}: cosine_examples_after_repeat {cosine_examples} + "
                        f"cosine_excluded_examples_after_repeat {excluded_examples} != "
                        f"train_examples_after_repeat {total_examples}"
                    )
            if total_examples is not None and cosent_examples is not None and cosent_excluded_examples is not None:
                if cosent_examples + cosent_excluded_examples != total_examples:
                    issues.append(
                        f"round {round_id}: cosent_examples_after_repeat {cosent_examples} + "
                        f"cosent_excluded_examples_after_repeat {cosent_excluded_examples} != "
                        f"train_examples_after_repeat {total_examples}"
                    )
            if "antonym_mid" in tags:
                issues.append(f"round {round_id}: cosine_exclude_tags must retain antonym_mid")
            if tags not in {"", "[]"}:
                issues.append(f"round {round_id}: unexpected cosine_exclude_tags {tags}")
            if excluded_rows != 0:
                issues.append(f"round {round_id}: cosine_excluded_rows={excluded_rows}, expected 0")
            if excluded_examples != 0:
                issues.append(
                    f"round {round_id}: cosine_excluded_examples_after_repeat={excluded_examples}, expected 0"
                )

    if expected_bucket_repeat and analysis.get("three_rounds_ok"):
        for row in rows:
            round_id = row.get("round", "?")
            actual_bucket_repeat = str(
                row.get("bucket_band_hard_negative_repeat") or ""
            ).strip()
            if parse_int(actual_bucket_repeat) != parse_int(expected_bucket_repeat):
                issues.append(
                    f"round {round_id}: bucket_band_hard_negative_repeat="
                    f"{actual_bucket_repeat!r} != expected {expected_bucket_repeat!r}"
                )

    if expected_exclude == "antonym_mid":
        if not rows:
            issues.append("missing train_sampling rows in latest report")
        for row in rows:
            round_id = row.get("round", "?")
            tags = str(row.get("cosent_exclude_tags") or "")
            antonym_examples = parse_int(row.get("antonym_mid_examples_after_repeat"))
            excluded_examples = parse_int(row.get("cosent_excluded_examples_after_repeat"))
            if "antonym_mid" not in tags:
                issues.append(f"round {round_id}: cosent_exclude_tags missing antonym_mid")
            if antonym_examples is not None and excluded_examples is not None:
                if excluded_examples < antonym_examples:
                    issues.append(
                        f"round {round_id}: cosent_excluded_examples_after_repeat "
                        f"{excluded_examples} < antonym_mid_examples_after_repeat {antonym_examples}"
                    )
            else:
                issues.append(f"round {round_id}: missing cosent exclusion count")

    if expected_midpoint == "antonym_mid":
        if not rows:
            issues.append("missing train_sampling rows in latest report")
        for row in rows:
            round_id = row.get("round", "?")
            tags = str(row.get("midpoint_tags") or "")
            antonym_examples = parse_int(row.get("antonym_mid_examples_after_repeat"))
            midpoint_examples = parse_int(row.get("midpoint_examples_after_repeat"))
            if "antonym_mid" not in tags:
                issues.append(f"round {round_id}: midpoint_tags missing antonym_mid")
            if antonym_examples is not None and midpoint_examples is not None:
                if midpoint_examples < antonym_examples:
                    issues.append(
                        f"round {round_id}: midpoint_examples_after_repeat "
                        f"{midpoint_examples} < antonym_mid_examples_after_repeat {antonym_examples}"
                    )
            else:
                issues.append(f"round {round_id}: missing midpoint anchor count")

    if expected_bucket_rows:
        expected_buckets = parse_tag_bucket_spec(expected_bucket_rows)
        if not rows:
            issues.append("missing train_sampling rows in latest report")
        for row in rows:
            round_id = row.get("round", "?")
            actual_buckets = parse_tag_bucket_json(row.get("min_tag_bucket_rows"))
            if not actual_buckets:
                issues.append(f"round {round_id}: missing min_tag_bucket_rows")
                continue
            for key, expected_count in expected_buckets.items():
                if key not in actual_buckets:
                    issues.append(f"round {round_id}: min_tag_bucket_rows missing {key}")
                    continue
                actual_count = actual_buckets[key]
                if actual_count < expected_count:
                    issues.append(
                        f"round {round_id}: min_tag_bucket_rows {key} {actual_count} < expected {expected_count}"
                    )

    if rows and analysis.get("three_rounds_ok"):
        missing_partition = sorted(
            field
            for field in PARTITION_REPORT_FIELDS
            if any(not str(row.get(field) or "").strip() for row in rows)
        )
        if missing_partition:
            issues.append(
                "latest real report lacks train/calib/eval partition evidence: "
                + ", ".join(missing_partition)
            )
        else:
            partition_issues: list[str] = []
            for row in rows:
                round_id = row.get("round", "?")
                values = {
                    field: parse_int(row.get(field))
                    for field in PARTITION_REPORT_FIELDS
                }
                partition_report_values.append({"round": round_id, **values})
                if any(value is None for value in values.values()):
                    partition_issues.append(f"round {round_id}: invalid partition evidence")
                    continue
                if values["eval_non_holdout_antonym_rows"] != 0:
                    partition_issues.append(
                        f"round {round_id}: eval_non_holdout_antonym_rows="
                        f"{values['eval_non_holdout_antonym_rows']}, expected 0"
                    )
                if values["eval_antonym_rows"] != values["eval_holdout_antonym_rows"]:
                    partition_issues.append(
                        f"round {round_id}: eval_antonym_rows="
                        f"{values['eval_antonym_rows']} != eval_holdout_antonym_rows="
                        f"{values['eval_holdout_antonym_rows']}"
                    )
                if values["unexpected_train_calib_symmetric_overlap"] != 0:
                    partition_issues.append(
                        f"round {round_id}: unexpected_train_calib_symmetric_overlap="
                        f"{values['unexpected_train_calib_symmetric_overlap']}, expected 0"
                    )
            issues.extend(partition_issues)
            partition_report_verified = not partition_issues

        missing_round_robin = sorted(
            field
            for field in ROUND_ROBIN_REPORT_FIELDS
            if any(not str(row.get(field) or "").strip() for row in rows)
        )
        if missing_round_robin:
            issues.append(
                "latest real report lacks round-robin schedule evidence: "
                + ", ".join(missing_round_robin)
            )
        else:
            round_robin_issues: list[str] = []
            for row in rows:
                round_id = row.get("round", "?")
                values = {
                    field: parse_int(row.get(field))
                    for field in ROUND_ROBIN_REPORT_FIELDS
                }
                round_robin_report_values.append({"round": round_id, **values})
                if any(value is None for value in values.values()):
                    round_robin_issues.append(f"round {round_id}: invalid round-robin evidence")
                    continue
                objective_count = values["objective_count"]
                steps_per_epoch = values["round_robin_steps_per_epoch"]
                original_min = values["round_robin_original_min_batches"]
                target_batches = values["round_robin_target_batches_per_objective"]
                protected_batches = values["round_robin_protected_min_batches"]
                padded_examples = values["round_robin_padded_examples"]
                noop_padded_examples = values["round_robin_noop_padded_examples"]
                if objective_count <= 0:
                    round_robin_issues.append(
                        f"round {round_id}: objective_count={objective_count}, expected positive"
                    )
                if original_min <= 0 or target_batches <= 0 or protected_batches <= 0:
                    round_robin_issues.append(
                        f"round {round_id}: invalid positive batch budget "
                        f"original={original_min} target={target_batches} protected={protected_batches}"
                    )
                if target_batches < max(original_min, protected_batches):
                    round_robin_issues.append(
                        f"round {round_id}: target_batches={target_batches} is below "
                        f"original/protected budget {max(original_min, protected_batches)}"
                    )
                if steps_per_epoch != target_batches * objective_count:
                    round_robin_issues.append(
                        f"round {round_id}: steps_per_epoch={steps_per_epoch} != "
                        f"target_batches*objective_count={target_batches * objective_count}"
                    )
                if padded_examples < 0:
                    round_robin_issues.append(
                        f"round {round_id}: round_robin_padded_examples={padded_examples}, expected non-negative"
                    )
                if noop_padded_examples < 0 or noop_padded_examples > padded_examples:
                    round_robin_issues.append(
                        f"round {round_id}: round_robin_noop_padded_examples={noop_padded_examples}, "
                        f"expected between 0 and round_robin_padded_examples={padded_examples}"
                    )
            issues.extend(round_robin_issues)
            round_robin_report_verified = not round_robin_issues

        fit_backend_required = analysis.get("actual_device_inferred") in {"mps", "cuda"}
        fit_rows = (
            rows
            if fit_backend_required
            else [
                row
                for row in rows
                if str(row.get("trainer_backend") or "").strip()
                == SENTENCE_TRANSFORMER_FIT_BACKEND
            ]
        )
        if fit_rows:
            fit_issues: list[str] = []
            if fit_backend_required:
                missing_backend_rounds = [
                    str(row.get("round", "?"))
                    for row in fit_rows
                    if not str(row.get("trainer_backend") or "").strip()
                ]
                unexpected_backend = sorted(
                    {
                        str(row.get("trainer_backend") or "").strip()
                        for row in fit_rows
                        if str(row.get("trainer_backend") or "").strip()
                        and str(row.get("trainer_backend") or "").strip()
                        != SENTENCE_TRANSFORMER_FIT_BACKEND
                    }
                )
                if missing_backend_rounds:
                    fit_issues.append(
                        "MPS/CUDA report missing trainer_backend in rounds: "
                        + ", ".join(missing_backend_rounds)
                    )
                if unexpected_backend:
                    fit_issues.append(
                        "MPS/CUDA report uses unexpected trainer_backend: "
                        + ", ".join(unexpected_backend)
                    )
            missing_fit = sorted(
                field
                for field in SENTENCE_TRANSFORMER_FIT_REPORT_FIELDS
                if any(not str(row.get(field) or "").strip() for row in fit_rows)
            )
            if missing_fit:
                fit_issues.append(
                    "latest real report lacks SentenceTransformer.fit schedule evidence: "
                    + ", ".join(missing_fit)
                )
            else:
                for row in fit_rows:
                    round_id = row.get("round", "?")
                    values = {
                        field: parse_int(row.get(field))
                        for field in SENTENCE_TRANSFORMER_FIT_REPORT_FIELDS
                    }
                    fit_report_values.append({"round": round_id, **values})
                    if any(value is None for value in values.values()):
                        fit_issues.append(
                            f"round {round_id}: invalid SentenceTransformer.fit schedule evidence"
                        )
                        continue
                    round_robin_steps = parse_int(row.get("round_robin_steps_per_epoch"))
                    objective_count = parse_int(row.get("objective_count"))
                    target_batches = parse_int(
                        row.get("round_robin_target_batches_per_objective")
                    )
                    warmup_steps = parse_int(row.get("warmup_steps"))
                    if (
                        round_robin_steps is None
                        or objective_count is None
                        or target_batches is None
                        or warmup_steps is None
                    ):
                        fit_issues.append(
                            f"round {round_id}: missing round-robin or warmup evidence for SentenceTransformer.fit check"
                        )
                        continue
                    if values["fit_steps_per_epoch"] != round_robin_steps:
                        fit_issues.append(
                            f"round {round_id}: fit_steps_per_epoch="
                            f"{values['fit_steps_per_epoch']} != "
                            f"round_robin_steps_per_epoch={round_robin_steps}"
                        )
                    if values["fit_steps_per_epoch"] != target_batches * objective_count:
                        fit_issues.append(
                            f"round {round_id}: fit_steps_per_epoch="
                            f"{values['fit_steps_per_epoch']} must equal target_batches_per_objective*objective_count"
                        )
                    if values["fit_warmup_steps"] != warmup_steps:
                        fit_issues.append(
                            f"round {round_id}: fit_warmup_steps="
                            f"{values['fit_warmup_steps']} != warmup_steps={warmup_steps}"
                        )
            issues.extend(fit_issues)
            fit_report_verified = not fit_issues

    return make_result(ok=not issues, skipped=False, reason="")


def triage_status(
    health: dict[str, object],
    analysis: dict[str, object],
    strategy_checks: dict[str, object],
) -> tuple[str, int]:
    if not health.get("ok"):
        return "launchd_unhealthy", 2
    if health.get("run_log_after_latest_schedule"):
        latest_run = str(health.get("latest_run_log_stamp") or "")
        latest_report = str(health.get("latest_real_stamp") or "")
        if not latest_run or latest_run != latest_report:
            return "nightly_started_waiting_for_report", 0
    if health.get("partial_run_after_latest_schedule"):
        latest_run = str(health.get("latest_run_log_stamp") or "")
        latest_report = str(health.get("latest_real_stamp") or "")
        if not latest_run or latest_run != latest_report:
            return "nightly_partial_run_no_report", 3
    if health.get("missed_latest_schedule"):
        return "missed_schedule", 3
    if not analysis.get("three_rounds_ok"):
        return "waiting_for_next_real_three_round_report", 0
    if strategy_checks.get("skipped"):
        return "waiting_for_next_real_strategy_report", 0
    if not strategy_checks.get("ok"):
        return "semantic_strategy_failed", 4
    return "ok", 0


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
    if analysis.get("actual_device_inferred") == "unknown":
        device = launchd_device_evidence(health)
        if device.get("actual_device_inferred") != "unknown":
            analysis.update(device)
    if not analysis.get("gate_status"):
        gate_status = analyze_nightly_report_v26.parse_gate_status(launchd_log_text(health))
        if gate_status.get("gate_status"):
            analysis.update(gate_status)
    strategy_checks = semantic_strategy_checks(health, analysis)

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

    status, exit_code = triage_status(health, analysis, strategy_checks)

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
            "gate_status_available": bool(analysis.get("gate_status")),
            "failed_gates": analysis.get("failed_gates"),
            "gate_failure_counts": analysis.get("gate_failure_counts"),
            "group_regressions": analysis.get("group_regressions"),
            "bucket_confusions": analysis.get("bucket_confusions"),
            "train_sampling": analysis.get("train_sampling"),
            "antonym_group": analysis.get("antonym_group"),
        },
        "todo": todo_summary,
        "strategy_checks": strategy_checks,
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
    strategy = payload["strategy_checks"]
    print(f"status={payload['status']}")
    print(f"launchd_ok={health['ok']}")
    print(f"missed_latest_schedule={health['missed_latest_schedule']}")
    print(f"wrapper_loaded={health['wrapper_loaded']}")
    print(f"nightly_total_runs={health['nightly_total_runs']}")
    print(f"sup_cosent_exclude_tags={health.get('sup_cosent_exclude_tags')}")
    print(f"sup_cosine_exclude_tags={health.get('sup_cosine_exclude_tags')}")
    print(
        "calib_midpoint_augment="
        f"radius:{health.get('calib_midpoint_augment_radius')} "
        f"steps:{health.get('calib_midpoint_augment_steps')} "
        f"weight:{health.get('calib_midpoint_augment_weight')}"
    )
    print(f"latest_run_log={health['latest_run_log']}")
    print(f"run_log_after_latest_schedule={health['run_log_after_latest_schedule']}")
    print(f"latest_partial_run_artifact={health.get('latest_partial_run_artifact', '')}")
    print(f"partial_run_after_latest_schedule={health.get('partial_run_after_latest_schedule', False)}")
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
        if analysis.get("gate_failure_counts"):
            print(f"gate_failure_counts={analysis['gate_failure_counts']}")
    elif not analysis.get("gate_status_available"):
        print("failed_gates=(unavailable: matching gate log not found)")
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
    if analysis.get("train_sampling"):
        print("train_sampling:")
        for item in analysis["train_sampling"][:5]:
            print(
                "- "
                f"round={item.get('round')} "
                f"antonym_mid_rows={item.get('antonym_mid_rows', '-')} "
                f"antonym_mid_examples={item.get('antonym_mid_examples_after_repeat', '-')} "
                f"proxy_train={item.get('required_proxy_antonym_train_rows', '-')} "
                f"proxy_calib={item.get('required_proxy_antonym_calib_rows', '-')} "
                f"proxy_examples={item.get('proxy_antonym_examples_after_repeat', '-')} "
                f"cosent_excluded_examples={item.get('cosent_excluded_examples_after_repeat', '-')} "
                f"cosine_examples={item.get('cosine_examples_after_repeat', '-')} "
                f"cosine_excluded_examples={item.get('cosine_excluded_examples_after_repeat', '-')} "
                f"gold_to_calib_rows={item.get('gold_to_calib_rows', '-')} "
                f"gold_to_calib_weight={item.get('gold_to_calib_weight', '-')} "
                f"priority_antonym_calib_rows={item.get('priority_antonym_calib_anchor_rows', '-')} "
                f"priority_antonym_weight_rows={item.get('priority_antonym_calib_weight_rows', '-')} "
                f"cosent_exclude_tags={item.get('cosent_exclude_tags', '-')} "
                f"cosine_exclude_tags={item.get('cosine_exclude_tags', '-')} "
                f"rr_original_min={item.get('round_robin_original_min_batches', '-')} "
                f"rr_target={item.get('round_robin_target_batches_per_objective', '-')} "
                f"rr_protected={item.get('round_robin_protected_min_batches', '-')} "
                f"rr_padded={item.get('round_robin_padded_examples', '-')} "
                f"bucket_band_examples={item.get('bucket_band_examples_after_repeat', '-')} "
                f"midpoint_examples={item.get('midpoint_examples_after_repeat', '-')} "
                f"midpoint_tags={item.get('midpoint_tags', '-')} "
                f"min_tag_rows={item.get('min_tag_rows', '-')} "
                f"min_tag_bucket_rows={item.get('min_tag_bucket_rows', '-')}"
            )
    if analysis["antonym_group"]:
        print(f"antonym_group={analysis['antonym_group']}")
    else:
        print("antonym_group=(missing)")
    print(f"strategy_checks_ok={strategy['ok']}")
    print(f"calib_midpoint_report_verified={strategy.get('calib_midpoint_report_verified')}")
    print(f"midpoint_band_report_verified={strategy.get('midpoint_band_report_verified')}")
    print(f"partition_report_verified={strategy.get('partition_report_verified')}")
    print(f"round_robin_report_verified={strategy.get('round_robin_report_verified')}")
    if strategy.get("skipped"):
        print(f"strategy_checks_skipped={strategy.get('reason')}")
    if strategy.get("issues"):
        print("strategy_check_issues:")
        for item in strategy["issues"]:
            print(f"- {item}")
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
    strategy = payload["strategy_checks"]
    lines = [
        "# Nightly Next-Morning Triage",
        "",
        f"- status: `{payload['status']}`",
        f"- launchd_ok: `{health['ok']}`",
        f"- missed_latest_schedule: `{health['missed_latest_schedule']}`",
        f"- latest_run_log: `{health['latest_run_log']}`",
        f"- run_log_after_latest_schedule: `{health['run_log_after_latest_schedule']}`",
        f"- latest_partial_run_artifact: `{health.get('latest_partial_run_artifact', '')}`",
        f"- partial_run_after_latest_schedule: `{health.get('partial_run_after_latest_schedule', False)}`",
        f"- wrapper_loaded: `{health['wrapper_loaded']}`",
        f"- nightly_total_runs: `{health['nightly_total_runs']}`",
        f"- sup_min_tag_rows: `{health.get('sup_min_tag_rows')}`",
        f"- sup_min_tag_bucket_rows: `{health.get('sup_min_tag_bucket_rows')}`",
        f"- calib_support_positive_target_low: `{health.get('calib_support_positive_target_low')}`",
        f"- calib_midpoint_augment_radius: `{health.get('calib_midpoint_augment_radius')}`",
        f"- calib_midpoint_augment_steps: `{health.get('calib_midpoint_augment_steps')}`",
        f"- calib_midpoint_augment_weight: `{health.get('calib_midpoint_augment_weight')}`",
        f"- sup_cosent_exclude_tags: `{health.get('sup_cosent_exclude_tags')}`",
        f"- sup_cosine_exclude_tags: `{health.get('sup_cosine_exclude_tags')}`",
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
        if analysis.get("gate_failure_counts"):
            lines.append(f"- failure_counts: `{analysis['gate_failure_counts']}`")
    elif not analysis.get("gate_status_available"):
        lines.append("- unavailable: matching gate log was not found; use regressed groups and bucket confusions below")
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

    lines.extend(["", "## Train Sampling", ""])
    sampling = analysis.get("train_sampling") or []
    if sampling:
        for item in sampling[:10]:
            lines.append(
                "- "
                f"round `{item.get('round', '')}`: "
                f"antonym_mid_rows `{item.get('antonym_mid_rows', '-')}`, "
                f"antonym_mid_examples `{item.get('antonym_mid_examples_after_repeat', '-')}`, "
                f"proxy_train `{item.get('required_proxy_antonym_train_rows', '-')}`, "
                f"proxy_calib `{item.get('required_proxy_antonym_calib_rows', '-')}`, "
                f"proxy_examples `{item.get('proxy_antonym_examples_after_repeat', '-')}`, "
                f"cosent_excluded_examples `{item.get('cosent_excluded_examples_after_repeat', '-')}`, "
                f"cosine_examples `{item.get('cosine_examples_after_repeat', '-')}`, "
                f"cosine_excluded_examples `{item.get('cosine_excluded_examples_after_repeat', '-')}`, "
                f"gold_to_calib_rows `{item.get('gold_to_calib_rows', '-')}`, "
                f"gold_to_calib_weight `{item.get('gold_to_calib_weight', '-')}`, "
                f"priority_antonym_calib_rows `{item.get('priority_antonym_calib_anchor_rows', '-')}`, "
                f"priority_antonym_weight_rows `{item.get('priority_antonym_calib_weight_rows', '-')}`, "
                f"cosent_exclude_tags `{item.get('cosent_exclude_tags', '-')}`, "
                f"cosine_exclude_tags `{item.get('cosine_exclude_tags', '-')}`, "
                f"rr_original_min `{item.get('round_robin_original_min_batches', '-')}`, "
                f"rr_target `{item.get('round_robin_target_batches_per_objective', '-')}`, "
                f"rr_protected `{item.get('round_robin_protected_min_batches', '-')}`, "
                f"rr_padded `{item.get('round_robin_padded_examples', '-')}`, "
                f"bucket_band_examples `{item.get('bucket_band_examples_after_repeat', '-')}`, "
                f"min_tag_rows `{item.get('min_tag_rows', '-')}`, "
                f"min_tag_bucket_rows `{item.get('min_tag_bucket_rows', '-')}`"
            )
    else:
        lines.append("- unavailable: report has no actual training sampling section")

    lines.extend(["", "## Antonym", ""])
    antonym = analysis.get("antonym_group")
    if antonym:
        lines.append(f"- `{antonym}`")
    else:
        lines.append("- antonym group missing")

    lines.extend(["", "## Strategy Checks", ""])
    lines.append(f"- ok: `{strategy.get('ok')}`")
    lines.append(f"- expected_cosent_exclude_tags: `{strategy.get('expected_cosent_exclude_tags')}`")
    lines.append(f"- expected_cosine_exclude_tags: `{strategy.get('expected_cosine_exclude_tags')}`")
    lines.append(f"- expected_midpoint_tags: `{strategy.get('expected_midpoint_tags')}`")
    lines.append(
        f"- expected_midpoint_band: `[{strategy.get('expected_midpoint_band_low')}, "
        f"{strategy.get('expected_midpoint_band_high')}]`"
    )
    lines.append(f"- expected_min_tag_bucket_rows: `{strategy.get('expected_min_tag_bucket_rows')}`")
    lines.append(
        f"- expected_calib_support_positive_target_low: "
        f"`{strategy.get('expected_calib_support_positive_target_low')}`"
    )
    lines.append(
        f"- expected_calib_midpoint_augment: "
        f"`radius={strategy.get('expected_calib_midpoint_augment_radius')}, "
        f"steps={strategy.get('expected_calib_midpoint_augment_steps')}, "
        f"weight={strategy.get('expected_calib_midpoint_augment_weight')}`"
    )
    lines.append(
        f"- calib_midpoint_report_verified: `{strategy.get('calib_midpoint_report_verified')}`"
    )
    lines.append(
        f"- midpoint_band_report_verified: `{strategy.get('midpoint_band_report_verified')}`"
    )
    lines.append(f"- partition_report_verified: `{strategy.get('partition_report_verified')}`")
    lines.append(f"- round_robin_report_verified: `{strategy.get('round_robin_report_verified')}`")
    lines.append(f"- fit_report_verified: `{strategy.get('fit_report_verified')}`")
    if strategy.get("calib_midpoint_report_values"):
        lines.append(
            f"- calib_midpoint_report_values: `{strategy.get('calib_midpoint_report_values')}`"
        )
    if strategy.get("partition_report_values"):
        lines.append(f"- partition_report_values: `{strategy.get('partition_report_values')}`")
    if strategy.get("round_robin_report_values"):
        lines.append(f"- round_robin_report_values: `{strategy.get('round_robin_report_values')}`")
    if strategy.get("fit_report_values"):
        lines.append(f"- fit_report_values: `{strategy.get('fit_report_values')}`")
    if strategy.get("skipped"):
        lines.append(f"- skipped: `{strategy.get('reason')}`")
    if strategy.get("missing_evidence"):
        lines.append(f"- missing_evidence: `{strategy.get('missing_evidence')}`")
    issues = strategy.get("issues") or []
    if issues:
        lines.extend(f"- issue: `{item}`" for item in issues)

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
