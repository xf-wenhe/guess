import csv
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_nightly_10pm_launchd.sh"
NIGHTLY_SCRIPT = REPO_ROOT / "scripts" / "nightly_train_v26.sh"
TRACE_EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "extract_score_trace_review_candidates.py"
WORST_CASE_EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "extract_nightly_worst_case_review_candidates.py"
BUILD_NIGHTLY_SETS_SCRIPT = REPO_ROOT / "scripts" / "build_nightly_semantic_sets.py"
REGRESSION_PAIRS_PATH = REPO_ROOT / "data" / "regression_pairs_v23.json"
ANALYZE_NIGHTLY_REPORT_SCRIPT = REPO_ROOT / "scripts" / "analyze_nightly_report_v26.py"
COMPARE_NIGHTLY_REPORTS_SCRIPT = REPO_ROOT / "scripts" / "compare_recent_nightly_reports_v26.py"
CHECK_NIGHTLY_LAUNCHD_SCRIPT = REPO_ROOT / "scripts" / "check_nightly_launchd_v26.py"
NEXT_MORNING_TRIAGE_SCRIPT = REPO_ROOT / "scripts" / "nightly_next_morning_triage_v26.py"
TODO_STATUS_SCRIPT = REPO_ROOT / "scripts" / "semantic_training_todo_status.py"
VALIDATE_REVIEW_SCRIPT = REPO_ROOT / "scripts" / "validate_review_candidates.py"
VALIDATE_SCRIPT_MANIFEST = REPO_ROOT / "scripts" / "validate_semantic_script_manifest.py"
SCRIPTS_README = REPO_ROOT / "scripts" / "README.md"
SEMANTIC_SCRIPT_MANIFEST = REPO_ROOT / "scripts" / "semantic_script_manifest.json"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "preflight_v26.sh"


class NightlyScriptsTest(unittest.TestCase):
    def test_scripts_readme_lists_current_semantic_entrypoints(self):
        guide = SCRIPTS_README.read_text(encoding="utf-8")
        manifest = json.loads(SEMANTIC_SCRIPT_MANIFEST.read_text(encoding="utf-8"))
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT_MANIFEST), "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertEqual(manifest["schema_version"], 1)
        self.assertIn("semantic_script_manifest.json", guide)
        documented_groups = (
            "current_entrypoints",
            "nightly_pipeline",
            "review_data_loop",
            "source_dataset_builders",
            "manual_or_historical",
        )
        for group in documented_groups:
            for script_name in manifest[group]:
                self.assertTrue((REPO_ROOT / "scripts" / script_name).exists(), msg=f"{group}:{script_name}")
        for script_name in manifest["current_entrypoints"] + manifest["nightly_pipeline"] + manifest["review_data_loop"]:
            self.assertIn(f"`{script_name}`", guide)
        for script_name in manifest["removed_obsolete"]:
            self.assertFalse((REPO_ROOT / "scripts" / script_name).exists(), msg=f"removed obsolete script still exists: {script_name}")
        self.assertIn("Historical Or Manual-Only Entrypoints", guide)
        self.assertIn("antonym/opposite pairs", guide)

    def test_semantic_training_todo_status_reports_pending_goal_items(self):
        result = subprocess.run(
            [sys.executable, str(TODO_STATUS_SCRIPT), "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertGreater(payload["total"], 0)
        self.assertGreater(payload["pending"], 0)
        self.assertLess(payload["done"], payload["total"])
        pending_text = "\n".join(item["text"] for item in payload["pending_items"])
        self.assertIn("At least one real candidate passes strict gates", pending_text)
        self.assertIn("Isolate and reduce the latest real-nightly bucket regressions", pending_text)

    def test_analyze_gate_status_preserves_failures_from_earlier_rounds(self):
        spec = importlib.util.spec_from_file_location(
            "analyze_nightly_report_v26_gate_aggregation",
            REPO_ROOT / "scripts" / "analyze_nightly_report_v26.py",
        )
        self.assertIsNotNone(spec)
        analyzer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(analyzer)

        payload = analyzer.parse_gate_status(
            "\n".join(
                (
                    "mae_ok=False",
                    "antonym_strict_mid_recall_ok=False",
                    "regression_ok=False",
                    "mae_ok=True",
                    "antonym_strict_mid_recall_ok=True",
                    "regression_ok=True",
                )
            )
        )

        self.assertFalse(payload["gate_status"]["antonym_strict_mid_recall_ok"])
        self.assertFalse(payload["gate_status"]["regression_ok"])
        self.assertEqual(
            payload["failed_gates"],
            ["mae_ok", "antonym_strict_mid_recall_ok", "regression_ok"],
        )
        self.assertEqual(payload["gate_failure_counts"]["regression_ok"], 1)

    def test_next_morning_triage_strategy_check_validates_cosent_exclusion_counts(self):
        spec = importlib.util.spec_from_file_location(
            "nightly_next_morning_triage_v26",
            NEXT_MORNING_TRIAGE_SCRIPT,
        )
        self.assertIsNotNone(spec)
        triage = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            spec.loader.exec_module(triage)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        health = {
            "warnings": [],
            "sup_cosent_exclude_tags": "antonym_mid",
            "sup_cosine_exclude_tags": "",
            "sup_midpoint_tags": "antonym_mid",
            "sup_min_tag_bucket_rows": "same_category_mid@40-59:20,same_category_mid@60-79:12",
            "sup_bucket_band_hard_negative_repeat": "2",
            "calib_support_positive_target_low": "60",
        }
        analysis = {
            "train_sampling": [
                {
                    "round": "1",
                    "antonym_mid_examples_after_repeat": "153",
                    "train_examples_after_repeat": "579",
                    "cosent_examples_after_repeat": "426",
                    "cosine_examples_after_repeat": "579",
                    "cosent_exclude_tags": '["antonym_mid"]',
                    "cosent_excluded_examples_after_repeat": "153",
                    "cosent_base_guard_enabled": "True",
                    "cosent_base_guard_weight": "1.0",
                    "cosent_base_guard_margin": "0.02",
                    "cosent_base_guard_examples": "426",
                    "cosent_base_guard_protected_examples": "180",
                    "midpoint_base_guard_enabled": "True",
                    "midpoint_base_guard_weight": "1.0",
                    "midpoint_base_guard_margin": "0.02",
                    "midpoint_base_guard_examples": "306",
                    "midpoint_base_guard_protected_examples": "180",
                    "cosine_exclude_tags": "[]",
                    "cosine_excluded_rows": "0",
                    "cosine_excluded_examples_after_repeat": "0",
                    "bucket_only_tags": '["same_category_but_far"]',
                    "bucket_only_rows": "0",
                    "bucket_only_examples_after_repeat": "0",
                    "cosent_bucket_only_excluded_rows": "0",
                    "cosent_bucket_only_excluded_examples_after_repeat": "0",
                    "cosine_bucket_only_excluded_rows": "0",
                    "cosine_bucket_only_excluded_examples_after_repeat": "0",
                    "midpoint_tags": '["antonym_mid"]',
                    "midpoint_examples_after_repeat": "306",
                    "bucket_band_tags": '["same_category_mid"]',
                    "bucket_band_hard_negative_repeat": "2",
                    "bucket_band_examples_after_repeat": "42",
                    "min_tag_bucket_rows": '{"same_category_mid@40-59": 20, "same_category_mid@60-79": 12}',
                    "eval_antonym_rows": "1",
                    "eval_holdout_antonym_rows": "1",
                    "eval_non_holdout_antonym_rows": "0",
                    "unexpected_train_calib_symmetric_overlap": "0",
                    "objective_count": "5",
                    "round_robin_steps_per_epoch": "235",
                    "round_robin_original_min_batches": "34",
                    "round_robin_target_batches_per_objective": "47",
                    "round_robin_protected_min_batches": "47",
                    "round_robin_padded_examples": "120",
                    "round_robin_noop_padded_examples": "104",
                    "trainer_backend": "SentenceTransformer.fit",
                    "fit_steps_per_epoch": "235",
                    "fit_warmup_steps": "23",
                    "warmup_steps": "23",
                }
            ]
        }
        ok = triage.semantic_strategy_checks(health, analysis)
        self.assertTrue(ok["ok"])
        self.assertFalse(ok["skipped"])

        route_health = {**health, "sup_bucket_only_tags": "same_category_but_far"}
        route_analysis = {
            **analysis,
            "three_rounds_ok": True,
            "config": {
                "sup_bucket_only_tags": "same_category_but_far",
                "calibration_eval_mode": "global_curve_v1",
                "base_guard_score_mode": "angle_view_v1",
            },
        }
        verified_route = triage.semantic_strategy_checks(route_health, route_analysis)
        self.assertTrue(verified_route["ok"])
        self.assertFalse(verified_route["skipped"])
        old_eval_route = {
            **route_analysis,
            "config": {"sup_bucket_only_tags": "same_category_but_far"},
        }
        waiting_for_new_eval = triage.semantic_strategy_checks(
            route_health,
            old_eval_route,
        )
        self.assertTrue(waiting_for_new_eval["skipped"])
        self.assertIn("global calibration or base-guard strategy", waiting_for_new_eval["reason"])
        self.assertIn("calibration_eval_mode", waiting_for_new_eval["missing_evidence"][0])
        route_analysis["config"]["sup_bucket_only_tags"] = (
            "same_category_but_far,same_category_mid"
        )
        stale_route = triage.semantic_strategy_checks(route_health, route_analysis)
        self.assertTrue(stale_route["ok"])
        self.assertTrue(stale_route["skipped"])
        self.assertIn("different bucket-only policy", stale_route["reason"])

        sampling_row = analysis["train_sampling"][0]
        bucket_only_tags = sampling_row["bucket_only_tags"]
        sampling_row.update(
            {
                "bucket_only_rows": "2",
                "bucket_only_examples_after_repeat": "10",
                "cosent_bucket_only_excluded_rows": "2",
                "cosent_bucket_only_excluded_examples_after_repeat": "10",
                "cosine_bucket_only_excluded_rows": "2",
                "cosine_bucket_only_excluded_examples_after_repeat": "10",
                "cosent_examples_after_repeat": "416",
                "cosine_examples_after_repeat": "569",
            }
        )
        verified_bucket_only = triage.semantic_strategy_checks(health, analysis)
        self.assertTrue(verified_bucket_only["ok"])
        self.assertFalse(verified_bucket_only["skipped"])

        sampling_row["cosent_bucket_only_excluded_examples_after_repeat"] = "9"
        bad_bucket_only = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad_bucket_only["ok"])
        self.assertIn(
            "cosent_bucket_only_excluded_examples_after_repeat",
            " ".join(bad_bucket_only["issues"]),
        )
        sampling_row.update(
            {
                "bucket_only_rows": "0",
                "bucket_only_examples_after_repeat": "0",
                "cosent_bucket_only_excluded_rows": "0",
                "cosent_bucket_only_excluded_examples_after_repeat": "0",
                "cosine_bucket_only_excluded_rows": "0",
                "cosine_bucket_only_excluded_examples_after_repeat": "0",
                "cosent_examples_after_repeat": "426",
                "cosine_examples_after_repeat": "579",
                "bucket_only_tags": bucket_only_tags,
            }
        )

        calibration_health = {
            **health,
            "calib_midpoint_augment_radius": "3.5",
            "calib_midpoint_augment_steps": "2",
            "calib_midpoint_augment_weight": "0.5",
        }
        calibration_analysis = {
            **analysis,
            "three_rounds_ok": True,
            "config": {
                "calibration_eval_mode": "global_curve_v1",
                "base_guard_score_mode": "angle_view_v1",
            },
        }
        waiting_for_calibration = triage.semantic_strategy_checks(
            calibration_health,
            calibration_analysis,
        )
        self.assertTrue(waiting_for_calibration["ok"])
        self.assertTrue(waiting_for_calibration["skipped"])
        self.assertIn(
            "midpoint calibration evidence",
            waiting_for_calibration["reason"],
        )

        calibration_analysis["config"] = {
            "calib_midpoint_augment_radius": "3.5",
            "calib_midpoint_augment_steps": "2",
            "calib_midpoint_augment_weight": "0.5",
            "calibration_eval_mode": "global_curve_v1",
            "base_guard_score_mode": "angle_view_v1",
        }
        verified_calibration = triage.semantic_strategy_checks(
            calibration_health,
            calibration_analysis,
        )
        self.assertTrue(verified_calibration["ok"])
        self.assertFalse(verified_calibration["skipped"])
        self.assertTrue(verified_calibration["calib_midpoint_report_verified"])

        band_health = {
            **calibration_health,
            "sup_midpoint_band_low": "0.45",
            "sup_midpoint_band_high": "0.55",
        }
        band_analysis = {
            **calibration_analysis,
            "config": {
                "calib_midpoint_augment_radius": "3.5",
                "calib_midpoint_augment_steps": "2",
                "calib_midpoint_augment_weight": "0.5",
                "calibration_eval_mode": "global_curve_v1",
                "base_guard_score_mode": "angle_view_v1",
                "sup_midpoint_band_low": "0.47",
                "sup_midpoint_band_high": "0.53",
            },
        }
        stale_band = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertFalse(stale_band["ok"])
        self.assertFalse(stale_band["skipped"])
        self.assertFalse(stale_band["midpoint_band_report_verified"])
        self.assertIn("sup_midpoint_band_low", stale_band["issues"][0])

        band_analysis["config"]["sup_midpoint_band_low"] = "0.45"
        band_analysis["config"]["sup_midpoint_band_high"] = "0.55"
        verified_band = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertTrue(verified_band["ok"])
        self.assertFalse(verified_band["skipped"])
        self.assertTrue(verified_band["midpoint_band_report_verified"])
        self.assertTrue(verified_band["partition_report_verified"])
        self.assertTrue(verified_band["round_robin_report_verified"])
        self.assertTrue(verified_band["fit_report_verified"])

        sampling_row = band_analysis["train_sampling"][0]
        sampling_row["eval_non_holdout_antonym_rows"] = "1"
        bad_partition = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertFalse(bad_partition["ok"])
        self.assertFalse(bad_partition["partition_report_verified"])
        self.assertIn("eval_non_holdout_antonym_rows", bad_partition["issues"][-1])
        sampling_row["eval_non_holdout_antonym_rows"] = "0"

        sampling_row["round_robin_steps_per_epoch"] = "230"
        bad_schedule = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertFalse(bad_schedule["ok"])
        self.assertFalse(bad_schedule["round_robin_report_verified"])
        self.assertIn("steps_per_epoch", bad_schedule["issues"][-1])
        sampling_row["round_robin_steps_per_epoch"] = "235"

        sampling_row["fit_steps_per_epoch"] = "234"
        bad_fit_schedule = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertFalse(bad_fit_schedule["ok"])
        self.assertFalse(bad_fit_schedule["fit_report_verified"])
        self.assertIn("fit_steps_per_epoch", bad_fit_schedule["issues"][-1])
        sampling_row["fit_steps_per_epoch"] = "235"

        band_analysis["actual_device_inferred"] = "mps"
        missing_backend = sampling_row.pop("trainer_backend")
        bad_backend_evidence = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertFalse(bad_backend_evidence["ok"])
        self.assertFalse(bad_backend_evidence["fit_report_verified"])
        self.assertIn("trainer_backend", " ".join(bad_backend_evidence["issues"]))
        sampling_row["trainer_backend"] = missing_backend
        band_analysis.pop("actual_device_inferred")

        sampling_row["round_robin_noop_padded_examples"] = "121"
        bad_noop_padding = triage.semantic_strategy_checks(band_health, band_analysis)
        self.assertFalse(bad_noop_padding["ok"])
        self.assertFalse(bad_noop_padding["round_robin_report_verified"])
        self.assertIn("noop_padded_examples", bad_noop_padding["issues"][-1])
        sampling_row["round_robin_noop_padded_examples"] = "104"

        calibration_analysis["config"]["calib_midpoint_augment_radius"] = "2.5"
        mismatched_calibration = triage.semantic_strategy_checks(
            calibration_health,
            calibration_analysis,
        )
        self.assertFalse(mismatched_calibration["ok"])
        self.assertFalse(mismatched_calibration["skipped"])
        self.assertIn("calib_midpoint_augment_radius", mismatched_calibration["issues"][0])

        analysis["train_sampling"][0]["cosine_exclude_tags"] = '["antonym_mid"]'
        bad_cosine = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad_cosine["ok"])
        self.assertIn("cosine_exclude_tags", bad_cosine["issues"][0])
        analysis["train_sampling"][0]["cosine_exclude_tags"] = "[]"

        analysis["train_sampling"][0]["cosine_examples_after_repeat"] = "578"
        bad_counts = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad_counts["ok"])
        self.assertIn("cosine_examples_after_repeat", bad_counts["issues"][0])
        analysis["train_sampling"][0]["cosine_examples_after_repeat"] = "579"

        analysis["train_sampling"][0]["cosent_excluded_examples_after_repeat"] = "10"
        bad = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad["ok"])
        self.assertIn("cosent_excluded_examples_after_repeat", bad["issues"][0])
        analysis["train_sampling"][0]["cosent_excluded_examples_after_repeat"] = "153"
        analysis["train_sampling"][0]["midpoint_examples_after_repeat"] = "10"
        bad_midpoint = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad_midpoint["ok"])
        self.assertIn("midpoint_examples_after_repeat", bad_midpoint["issues"][0])
        analysis["train_sampling"][0]["midpoint_examples_after_repeat"] = "306"
        analysis["train_sampling"][0]["min_tag_bucket_rows"] = '{"same_category_mid@40-59": 12}'
        bad_bucket_rows = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad_bucket_rows["ok"])
        self.assertIn("min_tag_bucket_rows", bad_bucket_rows["issues"][-1])
        self.assertEqual(
            triage.triage_status(
                {"ok": True, "missed_latest_schedule": False, "run_log_after_latest_schedule": False},
                {"three_rounds_ok": True},
                bad,
            ),
            ("semantic_strategy_failed", 4),
        )
        self.assertEqual(
            triage.triage_status(
                {"ok": True, "missed_latest_schedule": True, "run_log_after_latest_schedule": False},
                {"three_rounds_ok": True},
                bad,
            ),
            ("missed_schedule", 3),
        )
        self.assertEqual(
            triage.triage_status(
                {
                    "ok": True,
                    "missed_latest_schedule": False,
                    "run_log_after_latest_schedule": True,
                    "latest_run_log_stamp": "20260821_230003",
                    "latest_real_stamp": "20260821_230003",
                },
                {"three_rounds_ok": True},
                {"ok": True},
            ),
            ("ok", 0),
        )
        stale = triage.semantic_strategy_checks(
            health,
            {"train_sampling": [{"round": "1"}]},
        )
        self.assertTrue(stale["skipped"])
        self.assertIn("cosine/bucket", stale["reason"])
        skipped = triage.semantic_strategy_checks(
            {
                "warnings": ["latest real report predates current launchd install; wait for next 23:00 run"],
                "sup_cosent_exclude_tags": "antonym_mid",
                "sup_cosine_exclude_tags": "",
                "sup_min_tag_bucket_rows": "same_category_mid@40-59:20,same_category_mid@60-79:12",
                "calib_support_positive_target_low": "60",
            },
            analysis,
        )
        self.assertTrue(skipped["ok"])
        self.assertTrue(skipped["skipped"])
        self.assertEqual(
            triage.triage_status(
                {"ok": True, "missed_latest_schedule": False, "run_log_after_latest_schedule": False},
                {"three_rounds_ok": True},
                skipped,
            ),
            ("waiting_for_next_real_strategy_report", 0),
        )

    def test_preflight_runs_semantic_script_manifest_check_first(self):
        source = PREFLIGHT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("[1/7] semantic script manifest check", source)
        self.assertIn("scripts/validate_semantic_script_manifest.py", source)
        self.assertIn("[7/7] global hint quality gate", source)

    def test_install_script_generates_project_local_daily_launchd_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            fake_bin = tmp_path / "fake-bin"
            home_dir.mkdir(parents=True)
            fake_bin.mkdir(parents=True)
            logs_dir = home_dir / ".guess_nightly" / "logs"
            logs_dir.mkdir(parents=True)
            old_stdout = logs_dir / "launchd_nightly_v26.out.log"
            old_stderr = logs_dir / "launchd_nightly_v26.err.log"
            old_stdout.write_text("old stdout\n", encoding="utf-8")
            old_stderr.write_text("old stderr\n", encoding="utf-8")

            self._write_executable(
                fake_bin / "launchctl",
                "#!/bin/sh\nexit 0\n",
            )
            self._write_executable(
                fake_bin / "rsync",
                textwrap.dedent(
                    """#!/bin/sh
                    set -eu
                    dest="${@: -1}"
                    mkdir -p "$dest"
                    exit 0
                    """
                ),
            )

            env = os.environ.copy()
            env["HOME"] = str(home_dir)
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            plist_path = home_dir / "Library" / "LaunchAgents" / "com.guess.nightly-train-v26.plist"
            self.assertTrue(plist_path.exists(), msg=result.stdout)
            plist = plist_path.read_text(encoding="utf-8")

            self.assertIn("<key>Hour</key>", plist)
            self.assertIn("<integer>23</integer>", plist)
            self.assertIn("<key>Minute</key>", plist)
            self.assertIn("<integer>0</integer>", plist)
            self.assertIn("<key>NIGHTLY_TOTAL_RUNS</key>", plist)
            self.assertIn("<key>NIGHTLY_TRAIN_PROFILE</key>", plist)
            self.assertIn("<string>daily</string>", plist)
            self.assertIn("<string>3</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_LOSS_MODE</key>", plist)
            self.assertIn("<string>mixed</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIN_TAG_ROWS</key>", plist)
            self.assertIn("<string>antonym_mid:45</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS</key>", plist)
            self.assertIn(
                "<string>same_category_mid@40-59:20,same_category_mid@60-79:12</string>",
                plist,
            )
            self.assertIn("<key>NIGHTLY_SUP_MIN_ANGLE_REPEAT_TAG_BUCKETS</key>", plist)
            self.assertIn("<key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key>", plist)
            self.assertIn("<string>antonym_mid</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_COSINE_EXCLUDE_TAGS</key>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_TAGS</key>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_REPEAT_BOOST</key>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_BAND_LOW</key>", plist)
            self.assertIn("<string>0.45</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_BAND_HIGH</key>", plist)
            self.assertIn("<string>0.55</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_BAND_WEIGHT</key>", plist)
            self.assertIn("<string>4.0</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_CENTER_WEIGHT</key>", plist)
            self.assertIn("<string>1.0</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_MIDPOINT_OBJECTIVE_REPEATS</key>", plist)
            self.assertIn("<string>2</string>", plist)
            self.assertIn("<key>NIGHTLY_SUP_BUCKET_BAND_HARD_NEG_REPEAT</key>", plist)
            self.assertIn("<string>2</string>", plist)
            self.assertIn("<key>NIGHTLY_CALIB_SUPPORT_POSITIVE_TARGET_LOW</key>", plist)
            self.assertIn("<string>60</string>", plist)
            self.assertIn("<key>NIGHTLY_CALIB_MIDPOINT_AUGMENT_RADIUS</key>", plist)
            self.assertIn("<string>3.5</string>", plist)
            self.assertIn("<key>NIGHTLY_CALIB_MIDPOINT_AUGMENT_STEPS</key>", plist)
            self.assertIn("<key>NIGHTLY_CALIB_MIDPOINT_AUGMENT_WEIGHT</key>", plist)
            self.assertIn("<key>NIGHTLY_ENABLE_ANCHOR_FINETUNE</key>", plist)
            self.assertIn("<key>NIGHTLY_MIN_MAE_IMPROVEMENT</key>", plist)
            self.assertIn("<string>0.3</string>", plist)
            self.assertIn("<key>NIGHTLY_MIN_ACC_IMPROVEMENT</key>", plist)
            self.assertIn("<string>2.0</string>", plist)
            self.assertIn("<key>NIGHTLY_REQUIRE_NO_DEGRADE_ALL</key>", plist)
            self.assertNotIn("workspaces/guess_runtime", plist)
            self.assertIn(f"<string>{REPO_ROOT}/.nightly</string>", plist)
            wrapper_path = home_dir / ".guess_nightly" / "nightly_launcher.sh"
            self.assertTrue(wrapper_path.exists(), msg=result.stdout)
            self.assertIn(f"<string>{wrapper_path}</string>", plist)
            wrapper = wrapper_path.read_text(encoding="utf-8")
            self.assertIn(f'cd "{REPO_ROOT}"', wrapper)
            self.assertIn(f'exec /bin/bash "{REPO_ROOT}/scripts/nightly_train_v26.sh"', wrapper)
            self.assertNotIn("$HOME/.guess_nightly/nightly_train_v26.sh", wrapper)
            self.assertFalse(old_stdout.exists())
            self.assertFalse(old_stderr.exists())
            self.assertTrue(list(logs_dir.glob("launchd_nightly_v26.out.log.*.bak")))
            self.assertTrue(list(logs_dir.glob("launchd_nightly_v26.err.log.*.bak")))

            check = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_NIGHTLY_LAUNCHD_SCRIPT),
                    "--root",
                    str(REPO_ROOT),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-07T13:00:00",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, msg=check.stderr or check.stdout)
            payload = json.loads(check.stdout)
            self.assertTrue(payload["ok"], msg=payload)
            self.assertEqual(payload["wrapper_loaded"], str(wrapper_path))
            self.assertEqual(payload["nightly_total_runs"], "3")
            self.assertEqual(payload["antonym_gate"], "0.0")
            self.assertEqual(payload["sup_min_tag_rows"], "antonym_mid:45")
            self.assertEqual(
                payload["sup_min_tag_bucket_rows"],
                "same_category_mid@40-59:20,same_category_mid@60-79:12",
            )
            self.assertEqual(payload["sup_midpoint_objective_repeats"], "2")
            self.assertEqual(payload["sup_min_angle_repeat_tag_buckets"], "")
            self.assertEqual(payload["calib_support_positive_target_low"], "60")
            self.assertFalse(payload["missed_latest_schedule"])

    def test_check_nightly_launchd_warns_after_missed_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            root = tmp_path / "repo"
            resolved_root = root.resolve()
            plist_dir = home_dir / "Library" / "LaunchAgents"
            wrapper_dir = home_dir / ".guess_nightly"
            reports_dir = root / ".nightly" / "reports"
            scripts_dir = root / "scripts"
            plist_dir.mkdir(parents=True)
            wrapper_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)

            nightly_script = resolved_root / "scripts" / "nightly_train_v26.sh"
            nightly_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            wrapper = wrapper_dir / "nightly_launcher.sh"
            wrapper.write_text(
                f'#!/usr/bin/env bash\ncd "{resolved_root}"\nexec /bin/bash "{nightly_script}"\n',
                encoding="utf-8",
            )
            plist = plist_dir / "com.guess.nightly-train-v26.plist"
            plist.write_text(
                textwrap.dedent(
                    f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                      <key>Label</key><string>com.guess.nightly-train-v26</string>
                      <key>ProgramArguments</key>
                      <array><string>/bin/bash</string><string>{wrapper}</string></array>
                      <key>EnvironmentVariables</key>
                      <dict>
                        <key>NIGHTLY_TOTAL_RUNS</key><string>3</string>
                        <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key><string>0.0</string>
                        <key>NIGHTLY_SUP_MIN_TAG_ROWS</key><string>antonym_mid:45</string>
                        <key>NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS</key><string>same_category_mid@40-59:20,same_category_mid@60-79:12</string>
                        <key>NIGHTLY_CALIB_SUPPORT_POSITIVE_TARGET_LOW</key><string>60</string>
                        <key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key><string>antonym_mid</string>
                      </dict>
                      <key>StartCalendarInterval</key>
                      <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
                    </dict>
                    </plist>
                    """
                ),
                encoding="utf-8",
            )
            report = reports_dir / "nightly_promotion_20260606_230000.md"
            report.write_text("# real report\n", encoding="utf-8")
            installed_at = datetime(2026, 6, 7, 12, 0, 0).timestamp()
            os.utime(plist, (installed_at, installed_at))

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_NIGHTLY_LAUNCHD_SCRIPT),
                    "--root",
                    str(root),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-08T09:00:00",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"], msg=payload)
            self.assertTrue(payload["missed_latest_schedule"])
            self.assertIn("latest scheduled 23:00 run has passed", "\n".join(payload["warnings"]))

    def test_check_nightly_launchd_treats_new_run_log_as_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            root = tmp_path / "repo"
            resolved_root = root.resolve()
            plist_dir = home_dir / "Library" / "LaunchAgents"
            wrapper_dir = home_dir / ".guess_nightly"
            launchd_logs_dir = wrapper_dir / "logs"
            reports_dir = root / ".nightly" / "reports"
            logs_dir = root / ".nightly" / "data" / "tmp"
            scripts_dir = root / "scripts"
            plist_dir.mkdir(parents=True)
            wrapper_dir.mkdir(parents=True)
            launchd_logs_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)

            nightly_script = resolved_root / "scripts" / "nightly_train_v26.sh"
            nightly_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            wrapper = wrapper_dir / "nightly_launcher.sh"
            wrapper.write_text(
                f'#!/usr/bin/env bash\ncd "{resolved_root}"\nexec /bin/bash "{nightly_script}"\n',
                encoding="utf-8",
            )
            plist = plist_dir / "com.guess.nightly-train-v26.plist"
            plist.write_text(
                textwrap.dedent(
                    f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                      <key>Label</key><string>com.guess.nightly-train-v26</string>
                      <key>ProgramArguments</key>
                      <array><string>/bin/bash</string><string>{wrapper}</string></array>
                      <key>EnvironmentVariables</key>
                      <dict>
                        <key>NIGHTLY_TOTAL_RUNS</key><string>3</string>
                        <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key><string>0.0</string>
                        <key>NIGHTLY_SUP_MIN_TAG_ROWS</key><string>antonym_mid:45</string>
                        <key>NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS</key><string>same_category_mid@40-59:20,same_category_mid@60-79:12</string>
                        <key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key><string>antonym_mid</string>
                      </dict>
                      <key>StartCalendarInterval</key>
                      <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
                    </dict>
                    </plist>
                    """
                ),
                encoding="utf-8",
            )
            report = reports_dir / "nightly_promotion_20260606_230000.md"
            report.write_text("# real report\n", encoding="utf-8")
            run_log = logs_dir / "nightly_train_v26_20260607_230100.log"
            run_log.write_text("TRAIN_DEVICE=auto\n[nightly] still running\n", encoding="utf-8")
            run_started = datetime(2026, 6, 7, 23, 1, 0).timestamp()
            os.utime(run_log, (run_started, run_started))

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_NIGHTLY_LAUNCHD_SCRIPT),
                    "--root",
                    str(root),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-08T09:00:00",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"], msg=payload)
            self.assertFalse(payload["missed_latest_schedule"], msg=payload)
            self.assertTrue(payload["run_log_after_latest_schedule"], msg=payload)
            self.assertEqual(payload["latest_run_log_stamp"], "20260607_230100")
            self.assertIn("appears to have started", "\n".join(payload["warnings"]))

    def test_check_nightly_launchd_fails_on_post_install_stderr_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            root = tmp_path / "repo"
            resolved_root = root.resolve()
            plist_dir = home_dir / "Library" / "LaunchAgents"
            wrapper_dir = home_dir / ".guess_nightly"
            log_dir = wrapper_dir / "logs"
            reports_dir = root / ".nightly" / "reports"
            scripts_dir = root / "scripts"
            plist_dir.mkdir(parents=True)
            wrapper_dir.mkdir(parents=True)
            log_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)

            nightly_script = resolved_root / "scripts" / "nightly_train_v26.sh"
            nightly_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            wrapper = wrapper_dir / "nightly_launcher.sh"
            wrapper.write_text(
                f'#!/usr/bin/env bash\ncd "{resolved_root}"\nexec /bin/bash "{nightly_script}"\n',
                encoding="utf-8",
            )
            plist = plist_dir / "com.guess.nightly-train-v26.plist"
            plist.write_text(
                textwrap.dedent(
                    f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                      <key>Label</key><string>com.guess.nightly-train-v26</string>
                      <key>ProgramArguments</key>
                      <array><string>/bin/bash</string><string>{wrapper}</string></array>
                      <key>EnvironmentVariables</key>
                      <dict>
                        <key>NIGHTLY_TOTAL_RUNS</key><string>3</string>
                        <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key><string>0.0</string>
                        <key>NIGHTLY_SUP_MIN_TAG_ROWS</key><string>antonym_mid:45</string>
                        <key>NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS</key><string>same_category_mid@40-59:20,same_category_mid@60-79:12</string>
                        <key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key><string>antonym_mid</string>
                      </dict>
                      <key>StartCalendarInterval</key>
                      <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
                    </dict>
                    </plist>
                    """
                ),
                encoding="utf-8",
            )
            stderr_log = log_dir / "launchd_nightly_v26.err.log"
            stderr_log.write_text("Traceback: simulated launchd failure\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_NIGHTLY_LAUNCHD_SCRIPT),
                    "--root",
                    str(root),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-07T13:00:00",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("launchd stderr has fatal-looking lines", "\n".join(payload["problems"]))
            self.assertEqual(payload["fatal_stderr_lines"], ["Traceback: simulated launchd failure"])

    def test_next_morning_triage_reports_missed_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            root = tmp_path / "repo"
            resolved_root = root.resolve()
            plist_dir = home_dir / "Library" / "LaunchAgents"
            wrapper_dir = home_dir / ".guess_nightly"
            launchd_logs_dir = wrapper_dir / "logs"
            reports_dir = root / ".nightly" / "reports"
            logs_dir = root / ".nightly" / "data" / "tmp"
            scripts_dir = root / "scripts"
            plist_dir.mkdir(parents=True)
            wrapper_dir.mkdir(parents=True)
            launchd_logs_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)

            nightly_script = resolved_root / "scripts" / "nightly_train_v26.sh"
            nightly_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            wrapper = wrapper_dir / "nightly_launcher.sh"
            wrapper.write_text(
                f'#!/usr/bin/env bash\ncd "{resolved_root}"\nexec /bin/bash "{nightly_script}"\n',
                encoding="utf-8",
            )
            plist = plist_dir / "com.guess.nightly-train-v26.plist"
            plist.write_text(
                textwrap.dedent(
                    f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                      <key>Label</key><string>com.guess.nightly-train-v26</string>
                      <key>ProgramArguments</key>
                      <array><string>/bin/bash</string><string>{wrapper}</string></array>
                      <key>EnvironmentVariables</key>
                      <dict>
                        <key>NIGHTLY_TOTAL_RUNS</key><string>3</string>
                        <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key><string>0.0</string>
                        <key>NIGHTLY_SUP_MIN_TAG_ROWS</key><string>antonym_mid:45</string>
                        <key>NIGHTLY_SUP_MIN_TAG_BUCKET_ROWS</key><string>same_category_mid@40-59:20,same_category_mid@60-79:12</string>
                        <key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key><string>antonym_mid</string>
                      </dict>
                      <key>StartCalendarInterval</key>
                      <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
                    </dict>
                    </plist>
                    """
                ),
                encoding="utf-8",
            )
            report = reports_dir / "nightly_promotion_20260606_230000.md"
            report.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260606_230000

                    **总轮次**: 1

                    ## 各轮结果

                    | 轮次 | stage | base_mae | cand_mae | base_acc | cand_acc | reg_ok | accepted |
                    |------|-------|----------|----------|----------|----------|--------|----------|
                    | 1 | supervised | - | 7.5 | - | 66.0 | True | False |

                    **结果**: 无轮次通过门控，未晋升

                    ## 拒绝诊断 Round 1 (supervised)

                    | group | base_mae | cand_mae | base_acc | cand_acc | extra |
                    |-------|----------|----------|----------|----------|-------|
                    | same_category | 7.0 | 8.5 | 55.0 | 50.0 |  |

                    ### 校准桶错分 Top

                    | target_bucket | predicted_bucket | base_count | cand_count | cand_avg_error | top_tags | top_groups | examples |
                    |---------------|------------------|------------|------------|----------------|----------|------------|----------|
                    | 80-100 | 60-80 | 1 | 3 | 18.5 | alias_synonym_high:3 | synonym_alias:3 | 医生->大夫 |

                    ## 实际训练抽样 Round 1

                    | item | value |
                    |------|-------|
                    | source_rows | 300 |
                    | train_examples_after_repeat | 579 |
                    | cosine_examples_after_repeat | 579 |
                    | cosine_exclude_tags | [] |
                    | cosine_excluded_rows | 0 |
                    | cosine_excluded_examples_after_repeat | 0 |
                    | bucket_only_tags | ["same_category_but_far"] |
                    | bucket_only_rows | 0 |
                    | bucket_only_examples_after_repeat | 0 |
                    | cosent_bucket_only_excluded_rows | 0 |
                    | cosent_bucket_only_excluded_examples_after_repeat | 0 |
                    | cosine_bucket_only_excluded_rows | 0 |
                    | cosine_bucket_only_excluded_examples_after_repeat | 0 |
                    | hard_negative_rows | 66 |
                    | antonym_mid_rows | 51 |
                    | antonym_mid_examples_after_repeat | 153 |
                    | cosent_exclude_tags | ["antonym_mid"] |
                    | cosent_excluded_examples_after_repeat | 153 |
                    | cosent_base_guard_enabled | True |
                    | cosent_base_guard_weight | 1.0 |
                    | cosent_base_guard_margin | 0.02 |
                    | cosent_base_guard_examples | 426 |
                    | cosent_base_guard_protected_examples | 180 |
                    | midpoint_base_guard_enabled | True |
                    | midpoint_base_guard_weight | 1.0 |
                    | midpoint_base_guard_margin | 0.02 |
                    | midpoint_base_guard_examples | 306 |
                    | midpoint_base_guard_protected_examples | 180 |
                    | priority_antonym_calib_anchor_rows | 7 |
                    | priority_antonym_calib_weight_rows | 4 |
                    | midpoint_tags | ["antonym_mid"] |
                    | midpoint_examples_after_repeat | 306 |
                    | bucket_band_tags | ["same_category_mid"] |
                    | bucket_band_examples_after_repeat | 42 |
                    | min_tag_rows | {"antonym_mid": 45} |
                    | min_tag_bucket_rows | {"same_category_mid@40-59": 20, "same_category_mid@60-79": 12} |
                    """
                ),
                encoding="utf-8",
            )
            (launchd_logs_dir / "launchd_nightly_v26.out.log.20260607_120000.bak").write_text(
                "TRAIN_DEVICE=auto\ntrain_v28c: device=mps\nmae_ok=False\naccepted=False\n",
                encoding="utf-8",
            )
            installed_at = datetime(2026, 6, 7, 12, 0, 0).timestamp()
            os.utime(plist, (installed_at, installed_at))
            md_out = tmp_path / "triage.md"
            review_out = tmp_path / "review.csv"

            result = subprocess.run(
                [
                    sys.executable,
                    str(NEXT_MORNING_TRIAGE_SCRIPT),
                    "--root",
                    str(root),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-08T09:00:00",
                    "--markdown-output",
                    str(md_out),
                    "--write-review-csv",
                    "--review-output",
                    str(review_out),
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "missed_schedule")
            self.assertTrue(payload["health"]["missed_latest_schedule"])
            self.assertFalse(payload["analysis"]["three_rounds_ok"])
            self.assertEqual(payload["analysis"]["actual_device_inferred"], "mps")
            self.assertTrue(payload["analysis"]["used_gpu_or_mps"])
            self.assertFalse(payload["analysis"]["gate_status_available"])
            self.assertEqual(payload["analysis"]["failed_gates"], [])
            self.assertEqual(payload["analysis"]["bucket_confusions"][0]["target_bucket"], "80-100")
            self.assertEqual(payload["analysis"]["bucket_confusions"][0]["top_tags"], "alias_synonym_high:3")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["antonym_mid_rows"], "51")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["antonym_mid_examples_after_repeat"], "153")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["cosent_excluded_examples_after_repeat"], "153")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["priority_antonym_calib_anchor_rows"], "7")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["priority_antonym_calib_weight_rows"], "4")
            self.assertTrue(payload["strategy_checks"]["ok"])
            self.assertFalse(payload["strategy_checks"]["skipped"])
            self.assertEqual(payload["review_source_counts"]["nightly_bucket_confusion"], 1)
            self.assertEqual(payload["review_summary"]["status_counts"]["pending"], 1)
            self.assertEqual(payload["review_summary"]["severity_counts"]["medium"], 1)
            self.assertTrue(payload["review_validation"]["ok"])
            self.assertEqual(payload["review_validation"]["issue_count"], 0)
            self.assertGreater(payload["todo"]["pending"], 0)
            with review_out.open("r", encoding="utf-8") as file:
                review_rows = list(csv.DictReader(file))
            self.assertEqual(review_rows[0]["source"], "nightly_bucket_confusion")
            md = md_out.read_text(encoding="utf-8")
            self.assertIn("# Nightly Next-Morning Triage", md)
            self.assertIn("status: `missed_schedule`", md)
            self.assertIn("todo_progress:", md)
            self.assertIn("## Goal TODO", md)
            self.assertIn("## Bucket Confusions", md)
            self.assertIn("`80-100->60-80`", md)
            self.assertIn("## Train Sampling", md)
            self.assertIn("antonym_mid_rows `51`", md)
            self.assertIn("cosent_excluded_examples `153`", md)
            self.assertIn("priority_antonym_calib_rows `7`", md)
            self.assertIn("priority_antonym_weight_rows `4`", md)
            self.assertIn("## Strategy Checks", md)
            self.assertIn("expected_cosent_exclude_tags: `antonym_mid`", md)
            self.assertIn("expected_midpoint_tags: `antonym_mid`", md)
            self.assertIn("expected_min_tag_bucket_rows: `same_category_mid@40-59:20,same_category_mid@60-79:12`", md)
            self.assertIn("expected_calib_support_positive_target_low:", md)
            self.assertIn("alias_synonym_high:3", md)
            self.assertIn("source_counts:", md)
            self.assertIn("status_counts:", md)
            self.assertIn("severity_counts:", md)
            self.assertIn("validation_ok:", md)
            self.assertIn("matching gate log was not found", md)
            self.assertIn("antonym group missing", md)

    def test_next_morning_triage_reports_started_waiting_for_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            root = tmp_path / "repo"
            resolved_root = root.resolve()
            plist_dir = home_dir / "Library" / "LaunchAgents"
            wrapper_dir = home_dir / ".guess_nightly"
            reports_dir = root / ".nightly" / "reports"
            logs_dir = root / ".nightly" / "data" / "tmp"
            scripts_dir = root / "scripts"
            plist_dir.mkdir(parents=True)
            wrapper_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)

            nightly_script = resolved_root / "scripts" / "nightly_train_v26.sh"
            nightly_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            wrapper = wrapper_dir / "nightly_launcher.sh"
            wrapper.write_text(
                f'#!/usr/bin/env bash\ncd "{resolved_root}"\nexec /bin/bash "{nightly_script}"\n',
                encoding="utf-8",
            )
            plist = plist_dir / "com.guess.nightly-train-v26.plist"
            plist.write_text(
                textwrap.dedent(
                    f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                      <key>Label</key><string>com.guess.nightly-train-v26</string>
                      <key>ProgramArguments</key>
                      <array><string>/bin/bash</string><string>{wrapper}</string></array>
                      <key>EnvironmentVariables</key>
                      <dict>
                        <key>NIGHTLY_TOTAL_RUNS</key><string>3</string>
                        <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key><string>0.0</string>
                        <key>NIGHTLY_SUP_MIN_TAG_ROWS</key><string>antonym_mid:45</string>
                        <key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key><string>antonym_mid</string>
                      </dict>
                      <key>StartCalendarInterval</key>
                      <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
                    </dict>
                    </plist>
                    """
                ),
                encoding="utf-8",
            )
            report = reports_dir / "nightly_promotion_20260606_230000.md"
            report.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260606_230000

                    **总轮次**: 1

                    **结果**: 无轮次通过门控，未晋升
                    """
                ),
                encoding="utf-8",
            )
            old_report_time = datetime(2026, 6, 6, 23, 0, 0).timestamp()
            os.utime(report, (old_report_time, old_report_time))
            run_log = logs_dir / "nightly_train_v26_20260607_230100.log"
            run_log.write_text("TRAIN_DEVICE=auto\n[nightly] still running\n", encoding="utf-8")
            run_started = datetime(2026, 6, 7, 23, 1, 0).timestamp()
            os.utime(run_log, (run_started, run_started))

            result = subprocess.run(
                [
                    sys.executable,
                    str(NEXT_MORNING_TRIAGE_SCRIPT),
                    "--root",
                    str(root),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-08T09:00:00",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "nightly_started_waiting_for_report")
            self.assertFalse(payload["health"]["missed_latest_schedule"])
            self.assertTrue(payload["health"]["run_log_after_latest_schedule"])
            self.assertIn("todo", payload)
            self.assertGreater(payload["todo"]["total"], 0)

    def test_next_morning_triage_reports_partial_run_without_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            root = tmp_path / "repo"
            resolved_root = root.resolve()
            plist_dir = home_dir / "Library" / "LaunchAgents"
            wrapper_dir = home_dir / ".guess_nightly"
            reports_dir = root / ".nightly" / "reports"
            logs_dir = root / ".nightly" / "data" / "tmp"
            scripts_dir = root / "scripts"
            plist_dir.mkdir(parents=True)
            wrapper_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)

            nightly_script = resolved_root / "scripts" / "nightly_train_v26.sh"
            nightly_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            wrapper = wrapper_dir / "nightly_launcher.sh"
            wrapper.write_text(
                f'#!/usr/bin/env bash\ncd "{resolved_root}"\nexec /bin/bash "{nightly_script}"\n',
                encoding="utf-8",
            )
            plist = plist_dir / "com.guess.nightly-train-v26.plist"
            plist.write_text(
                textwrap.dedent(
                    f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                      <key>Label</key><string>com.guess.nightly-train-v26</string>
                      <key>ProgramArguments</key>
                      <array><string>/bin/bash</string><string>{wrapper}</string></array>
                      <key>EnvironmentVariables</key>
                      <dict>
                        <key>NIGHTLY_TOTAL_RUNS</key><string>3</string>
                        <key>NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT</key><string>0.0</string>
                        <key>NIGHTLY_SUP_MIN_TAG_ROWS</key><string>antonym_mid:45</string>
                        <key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key><string>antonym_mid</string>
                        <key>NIGHTLY_SUP_MIDPOINT_TAGS</key><string>antonym_mid</string>
                        <key>NIGHTLY_SUP_MIDPOINT_REPEAT_BOOST</key><string>2.0</string>
                        <key>NIGHTLY_SUP_MIDPOINT_BAND_LOW</key><string>0.45</string>
                        <key>NIGHTLY_SUP_MIDPOINT_BAND_HIGH</key><string>0.55</string>
                        <key>NIGHTLY_SUP_MIDPOINT_BAND_WEIGHT</key><string>4.0</string>
                        <key>NIGHTLY_SUP_MIDPOINT_CENTER_WEIGHT</key><string>1.0</string>
                      </dict>
                      <key>StartCalendarInterval</key>
                      <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
                    </dict>
                    </plist>
                    """
                ),
                encoding="utf-8",
            )
            report = reports_dir / "nightly_promotion_20260606_230000.md"
            report.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260606_230000

                    **总轮次**: 3

                    **结果**: 无轮次通过门控，未晋升
                    """
                ),
                encoding="utf-8",
            )
            old_report_time = datetime(2026, 6, 6, 23, 0, 0).timestamp()
            os.utime(report, (old_report_time, old_report_time))
            partial = logs_dir / "nightly_train_stats_20260607_230005_r1.json"
            partial.write_text('{"source_rows":300}\n', encoding="utf-8")
            partial_started = datetime(2026, 6, 7, 23, 5, 0).timestamp()
            os.utime(partial, (partial_started, partial_started))

            result = subprocess.run(
                [
                    sys.executable,
                    str(NEXT_MORNING_TRIAGE_SCRIPT),
                    "--root",
                    str(root),
                    "--home",
                    str(home_dir),
                    "--now",
                    "2026-06-08T09:00:00",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "nightly_partial_run_no_report")
            self.assertFalse(payload["health"]["missed_latest_schedule"])
            self.assertTrue(payload["health"]["partial_run_after_latest_schedule"])
            self.assertIn("partial nightly artifacts", "\n".join(payload["health"]["warnings"]))

    def test_regression_pairs_include_antonym_mid_checks(self):
        pairs = json.loads(REGRESSION_PAIRS_PATH.read_text(encoding="utf-8"))
        antonyms = [item for item in pairs if item.get("type") == "antonym"]

        self.assertGreaterEqual(len(antonyms), 5)
        for item in antonyms:
            self.assertEqual(item["target_min"], 45)
            self.assertEqual(item["target_max"], 55)

    def test_regression_score_preserves_semantic_midband_boundary(self):
        spec = importlib.util.spec_from_file_location(
            "run_regression_pairs_v23_score_policy",
            REPO_ROOT / "scripts" / "run_regression_pairs_v23.py",
        )
        self.assertIsNotNone(spec)
        regression = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(regression)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        self.assertEqual(regression.final_score(49.8, 0, 53.3), 40)
        self.assertEqual(regression.final_score(47.52, 0, 47.87), 40)
        self.assertEqual(regression.final_score(37.91, 0, 42.90, "related"), 40)
        self.assertEqual(regression.final_score(37.91, 0, 42.90, "unrelated"), 15)
        self.assertEqual(regression.final_score(33.50, 0, 39.85, "related"), 40)
        self.assertNotEqual(regression.final_score(29.99, 0, 39.85, "related"), 40)
        self.assertEqual(regression.final_score(45.0, 0, 30.0), 10)
        self.assertEqual(regression.final_score(15.0, 0, 25.0), 10)

    def test_nightly_builder_reads_approved_worst_case_review_candidates(self):
        source = BUILD_NIGHTLY_SETS_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"data/nightly_worst_case_review_candidates.csv"', source)
        self.assertIn('review_status not in {"approved", "merged"}', source)

    def test_analyze_nightly_report_skips_dry_run_and_extracts_training_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            nightly = Path(tmp) / ".nightly"
            reports = nightly / "reports"
            logs = nightly / "data" / "tmp"
            reports.mkdir(parents=True)
            logs.mkdir(parents=True)

            (reports / "nightly_promotion_20260605_102434.md").write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260605_102434

                    **时间**: 2026-06-05 10:24:34 CST
                    **模型**: bge-m3-finetuned-v27-semreal-anchor
                    **总轮次**: 3

                    ## 运行配置

                    | item | value |
                    |------|-------|
                    | dry_run | 1 |
                    | requested_device | auto |

                    **结果**: DRY_RUN - 未实际晋升
                    """
                ),
                encoding="utf-8",
            )

            report = reports / "nightly_promotion_20260604_230005.md"
            report.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260604_230005

                    **时间**: 2026-06-05 01:15:21 CST
                    **模型**: bge-m3-finetuned-v27-semreal-anchor
                    **总轮次**: 3

                    ## 运行配置

                    | item | value |
                    |------|-------|
                    | dry_run | 0 |
                    | requested_device | auto |
                    | sup_rows | 300 |
                    | sup_min_tag_bucket_rows | same_category_mid@40-59:20,same_category_mid@60-79:12 |
                    | calib_support_positive_target_low | 60 |

                    ## 晋升门控

                    | gate | value |
                    |------|-------|
                    | min_antonym_mid_recall_improvement | 0.0 |
                    | regression_gate | passed == total |

                    ## 各轮结果

                    | 轮次 | stage | base_mae | cand_mae | base_acc | cand_acc | reg_ok | accepted |
                    |------|-------|----------|----------|----------|----------|--------|----------|
                    | 1 | supervised | - | 7.7 | - | 66.0 | False | False |
                    | 2 | supervised | - | 7.2 | - | 69.0 | True | True |
                    | 3 | supervised | - | 7.5 | - | 67.0 | True | False |

                    **结果**: 无轮次通过门控，未晋升

                    ## 拒绝诊断 Round 1 (supervised)

                    | group | base_mae | cand_mae | base_acc | cand_acc | extra |
                    |-------|----------|----------|----------|----------|-------|
                    | antonym | 10.0 | 8.0 | 20.0 | 60.0 | mid@40-60 20.0 -> 60.0; strict@45-55 10.0 -> 50.0 |
                    | same_category | 7.0 | 8.5 | 55.0 | 50.0 |  |

                    ### 校准桶错分 Top

                    | target_bucket | predicted_bucket | base_count | cand_count | cand_avg_error | top_tags | top_groups | examples |
                    |---------------|------------------|------------|------------|----------------|----------|------------|----------|
                    | 80-100 | 60-80 | 1 | 3 | 18.5 | alias_synonym_high:3 | synonym_alias:3 | 医生->大夫 |

                    ## 实际训练抽样 Round 1

                    | item | value |
                    |------|-------|
                    | source_rows | 300 |
                    | train_examples_after_repeat | 579 |
                    | hard_negative_rows | 66 |
                    | antonym_mid_rows | 51 |
                    | antonym_mid_examples_after_repeat | 153 |
                    | cosent_exclude_tags | ["antonym_mid"] |
                    | cosent_excluded_examples_after_repeat | 153 |
                    | cosent_base_guard_enabled | True |
                    | cosent_base_guard_weight | 1.0 |
                    | cosent_base_guard_margin | 0.02 |
                    | cosent_base_guard_examples | 426 |
                    | cosent_base_guard_protected_examples | 180 |
                    | midpoint_base_guard_enabled | True |
                    | midpoint_base_guard_weight | 1.0 |
                    | midpoint_base_guard_margin | 0.02 |
                    | midpoint_base_guard_examples | 306 |
                    | midpoint_base_guard_protected_examples | 180 |
                    | priority_antonym_calib_anchor_rows | 7 |
                    | priority_antonym_calib_weight_rows | 4 |
                    | min_tag_rows | {"antonym_mid": 45} |
                    | min_tag_bucket_rows | {"same_category_mid@40-59": 20, "same_category_mid@60-79": 12} |

                    ## 训练数据分布 Round 2

                    | item | value |
                    |------|-------|
                    | gold_to_calib_rows | 1 |
                    | gold_to_calib_weight | 10 |
                    | priority_antonym_calib_anchor_rows | 9 |
                    | priority_antonym_calib_weight_rows | 4 |

                    ## 拒绝诊断 Round 2 (supervised)

                    | group | base_mae | cand_mae | base_acc | cand_acc | extra |
                    |-------|----------|----------|----------|----------|-------|
                    | antonym | 2.0 | 4.8 | 100.0 | 100.0 | mid@40-60 100.0 -> 100.0; strict@45-55 100.0 -> 100.0 |
                    | same_category | 6.0 | 7.0 | 60.0 | 58.0 |  |

                    ### 校准桶错分 Top

                    | target_bucket | predicted_bucket | base_count | cand_count | cand_avg_error | top_tags | top_groups | examples |
                    |---------------|------------------|------------|------------|----------------|----------|------------|----------|
                    | 40-60 | 20-40 | 2 | 4 | 6.2 | same_category_mid:4 | same_category:4 | 钢琴->黑白键 |

                    ## 实际训练抽样 Round 2

                    | item | value |
                    |------|-------|
                    | source_rows | 300 |
                    | train_examples_after_repeat | 580 |
                    | hard_negative_rows | 65 |
                    | antonym_mid_rows | 50 |
                    | antonym_mid_examples_after_repeat | 150 |
                    | cosent_exclude_tags | ["antonym_mid"] |
                    | cosent_excluded_examples_after_repeat | 150 |
                    | min_tag_rows | {"antonym_mid": 45} |
                    | min_tag_bucket_rows | {"same_category_mid@40-59": 20, "same_category_mid@60-79": 12} |
                    """
                ),
                encoding="utf-8",
            )
            (logs / "nightly_train_v26_20260604_230005.log").write_text(
                "[nightly][config] TRAIN_DEVICE=auto train_profile=daily\n"
                "train_v28c: device=mps\n"
                "mae_ok=False\n"
                "acc_ok=True\n"
                "hard_negative_ok=True\n"
                "synonym_recall_ok=True\n"
                "antonym_mid_recall_ok=True\n"
                "antonym_strict_mid_recall_ok=True\n"
                "regression_ok=True\n"
                "accepted=False\n"
                "[nightly] no accepted rounds, no promotion\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ANALYZE_NIGHTLY_REPORT_SCRIPT),
                    "--nightly-root",
                    str(nightly),
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["report"], str(report))
            self.assertFalse(payload["dry_run"])
            self.assertTrue(payload["three_rounds_ok"])
            self.assertEqual(payload["requested_device"], "auto")
            self.assertEqual(payload["actual_device_inferred"], "mps")
            self.assertTrue(payload["used_gpu_or_mps"])
            self.assertEqual(payload["best_round"]["轮次"], "2")
            self.assertEqual(payload["best_round_diagnostics"]["round"], "2")
            self.assertEqual(payload["antonym_group"]["group"], "antonym")
            self.assertEqual(payload["antonym_group"]["cand_mae"], "4.8")
            self.assertEqual(payload["failed_gates"], ["mae_ok"])
            self.assertEqual(payload["group_regressions"][0]["group"], "antonym")
            self.assertEqual(payload["bucket_confusions"][0]["target_bucket"], "40-60")
            self.assertEqual(payload["bucket_confusions"][0]["predicted_bucket"], "20-40")
            self.assertEqual(payload["bucket_confusions"][0]["top_groups"], "same_category:4")
            self.assertEqual(payload["train_sampling"][0]["round"], "1")
            self.assertEqual(payload["train_sampling"][0]["antonym_mid_rows"], "51")
            self.assertEqual(payload["train_sampling"][0]["antonym_mid_examples_after_repeat"], "153")
            self.assertEqual(payload["train_sampling"][0]["cosent_excluded_examples_after_repeat"], "153")
            self.assertEqual(payload["train_sampling"][0]["priority_antonym_calib_anchor_rows"], "7")
            self.assertEqual(payload["train_sampling"][0]["priority_antonym_calib_weight_rows"], "4")
            self.assertEqual(
                payload["train_sampling"][0]["min_tag_bucket_rows"],
                '{"same_category_mid@40-59": 20, "same_category_mid@60-79": 12}',
            )
            round2_sampling = next(item for item in payload["train_sampling"] if item["round"] == "2")
            self.assertEqual(round2_sampling["gold_to_calib_rows"], "1")
            self.assertEqual(round2_sampling["gold_to_calib_weight"], "10")
            self.assertEqual(round2_sampling["priority_antonym_calib_anchor_rows"], "9")

    def test_compare_recent_nightly_reports_summarizes_multi_night_trends(self):
        with tempfile.TemporaryDirectory() as tmp:
            nightly = Path(tmp) / ".nightly"
            reports = nightly / "reports"
            logs = nightly / "data" / "tmp"
            reports.mkdir(parents=True)
            logs.mkdir(parents=True)

            dry_run = reports / "nightly_promotion_20260615_120000.md"
            dry_run.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260615_120000

                    **总轮次**: 3

                    ## 运行配置

                    | item | value |
                    |------|-------|
                    | dry_run | 1 |

                    **结果**: DRY_RUN - 未实际晋升
                    """
                ),
                encoding="utf-8",
            )

            latest = reports / "nightly_promotion_20260614_230003.md"
            latest.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260614_230003

                    **总轮次**: 3

                    ## 运行配置

                    | item | value |
                    |------|-------|
                    | dry_run | 0 |
                    | requested_device | auto |
                    | train_profile | daily |
                    | sup_rows | 300 |
                    | sup_loss_mode | mixed |
                    | sup_min_tag_rows | antonym_mid:45 |
                    | sup_min_tag_bucket_rows | same_category_mid@40-59:20,same_category_mid@60-79:12 |
                    | calib_support_positive_target_low | 60 |
                    | sup_cosent_exclude_tags | antonym_mid |
                    | sup_cosine_exclude_tags |  |
                    | sup_bucket_only_tags | same_category_but_far |

                    ## 各轮结果

                    | 轮次 | stage | base_mae | cand_mae | base_acc | cand_acc | reg_ok | accepted |
                    |------|-------|----------|----------|----------|----------|--------|----------|
                    | 1 | supervised | - | 6.9 | - | 68.0 | False | False |
                    | 2 | supervised | - | 6.6 | - | 69.5 | True | False |
                    | 3 | supervised | - | 6.8 | - | 68.8 | True | False |

                    **结果**: 无轮次通过门控，未晋升

                    ## 拒绝诊断 Round 2 (supervised)

                    | group | base_mae | cand_mae | base_acc | cand_acc | extra |
                    |-------|----------|----------|----------|----------|-------|
                    | antonym | 15.0 | 22.5 | 50.0 | 0.0 | mid@40-60 50.0 -> 0.0; strict@45-55 50.0 -> 0.0 |

                    ## 训练数据分布 Round 2

                    | item | value |
                    |------|-------|
                    | gold_to_calib_rows | 1 |
                    | gold_to_calib_weight | 10 |
                    | priority_antonym_calib_anchor_rows | 7 |
                    | priority_antonym_calib_weight_rows | 4 |
                    | antonym_calib_anchor_weight | 10 |
                    | priority_antonym_calib_anchor_weight | 13 |

                    ## 实际训练抽样 Round 2

                    | item | value |
                    |------|-------|
                    | antonym_mid_rows | 50 |
                    | antonym_mid_examples_after_repeat | 150 |
                    | cosine_examples_after_repeat | 659 |
                    | cosent_exclude_tags | ["antonym_mid"] |
                    | cosent_excluded_examples_after_repeat | 150 |
                    | cosent_base_guard_enabled | True |
                    | cosent_base_guard_weight | 1.0 |
                    | cosent_base_guard_margin | 0.02 |
                    | cosent_base_guard_examples | 426 |
                    | cosent_base_guard_protected_examples | 180 |
                    | midpoint_base_guard_enabled | True |
                    | midpoint_base_guard_weight | 1.0 |
                    | midpoint_base_guard_margin | 0.02 |
                    | midpoint_base_guard_examples | 300 |
                    | midpoint_base_guard_protected_examples | 180 |
                    | cosine_exclude_tags | [] |
                    | cosine_excluded_rows | 0 |
                    | cosine_excluded_examples_after_repeat | 0 |
                    | bucket_only_tags | ["same_category_but_far"] |
                    | bucket_only_rows | 3 |
                    | bucket_only_examples_after_repeat | 15 |
                    | cosent_bucket_only_excluded_rows | 3 |
                    | cosent_bucket_only_excluded_examples_after_repeat | 15 |
                    | cosine_bucket_only_excluded_rows | 3 |
                    | cosine_bucket_only_excluded_examples_after_repeat | 15 |
                    | bucket_band_tags | ["same_category_mid"] |
                    | bucket_band_examples_after_repeat | 42 |
                    | min_tag_rows | {"antonym_mid": 45} |
                    | min_tag_bucket_rows | {"same_category_mid@40-59": 20, "same_category_mid@60-79": 12} |
                    """
                ),
                encoding="utf-8",
            )
            (logs / "nightly_train_v26_20260614_230003.log").write_text(
                "TRAIN_DEVICE=auto\n"
                "train_v28c: device=mps\n"
                "acc_ok=False\n"
                "antonym_strict_mid_recall_ok=False\n"
                "regression_ok=False\n"
                "accepted=False\n",
                encoding="utf-8",
            )

            older = reports / "nightly_promotion_20260613_230005.md"
            older.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260613_230005

                    **总轮次**: 3

                    ## 运行配置

                    | item | value |
                    |------|-------|
                    | dry_run | 0 |
                    | requested_device | auto |
                    | train_profile | daily |
                    | sup_rows | 300 |
                    | sup_loss_mode | mixed |
                    | sup_min_tag_rows | antonym_mid:45 |

                    ## 各轮结果

                    | 轮次 | stage | base_mae | cand_mae | base_acc | cand_acc | reg_ok | accepted |
                    |------|-------|----------|----------|----------|----------|--------|----------|
                    | 1 | supervised | - | 7.1 | - | 67.0 | True | False |
                    | 2 | supervised | - | 6.7 | - | 68.0 | True | False |
                    | 3 | supervised | - | 6.9 | - | 67.5 | True | False |

                    **结果**: 无轮次通过门控，未晋升
                    """
                ),
                encoding="utf-8",
            )

            for offset, path in enumerate((older, latest, dry_run), start=1):
                stamp = datetime(2026, 6, 15, 12, offset, 0).timestamp()
                os.utime(path, (stamp, stamp))

            result = subprocess.run(
                [
                    sys.executable,
                    str(COMPARE_NIGHTLY_REPORTS_SCRIPT),
                    "--nightly-root",
                    str(nightly),
                    "--limit",
                    "2",
                    "--json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["report_count"], 2)
            rows = payload["reports"]
            self.assertEqual(rows[0]["stamp"], "20260614_230003")
            self.assertEqual(rows[0]["actual_device_inferred"], "mps")
            self.assertTrue(rows[0]["used_gpu_or_mps"])
            self.assertTrue(rows[0]["three_rounds_ok"])
            self.assertEqual(rows[0]["best_round"], "2")
            self.assertEqual(rows[0]["best_cand_mae"], "6.6")
            self.assertEqual(rows[0]["sup_cosent_exclude_tags"], "antonym_mid")
            self.assertEqual(rows[0]["sup_cosine_exclude_tags"], "")
            self.assertEqual(
                rows[0]["sup_min_tag_bucket_rows"],
                "same_category_mid@40-59:20,same_category_mid@60-79:12",
            )
            self.assertEqual(rows[0]["calib_support_positive_target_low"], "60")
            self.assertEqual(rows[0]["antonym_mid_rows"], "50")
            self.assertEqual(rows[0]["cosent_excluded_examples_after_repeat"], "150")
            self.assertEqual(rows[0]["cosine_examples_after_repeat"], "659")
            self.assertEqual(rows[0]["cosine_exclude_tags"], "[]")
            self.assertEqual(rows[0]["cosine_excluded_rows"], "0")
            self.assertEqual(rows[0]["cosine_excluded_examples_after_repeat"], "0")
            self.assertEqual(rows[0]["bucket_only_tags"], '["same_category_but_far"]')
            self.assertEqual(rows[0]["bucket_only_rows"], "3")
            self.assertEqual(rows[0]["bucket_only_examples_after_repeat"], "15")
            self.assertEqual(
                rows[0]["cosent_bucket_only_excluded_examples_after_repeat"],
                "15",
            )
            self.assertEqual(
                rows[0]["cosine_bucket_only_excluded_examples_after_repeat"],
                "15",
            )
            self.assertEqual(rows[0]["bucket_band_examples_after_repeat"], "42")
            self.assertEqual(rows[0]["priority_antonym_calib_anchor_rows"], "7")
            self.assertEqual(rows[0]["priority_antonym_calib_weight_rows"], "4")
            self.assertEqual(rows[0]["antonym_calib_anchor_weight"], "10")
            self.assertEqual(rows[0]["priority_antonym_calib_anchor_weight"], "13")
            self.assertEqual(rows[0]["gold_to_calib_rows"], "1")
            self.assertEqual(rows[0]["gold_to_calib_weight"], "10")
            self.assertEqual(
                rows[0]["min_tag_bucket_rows"],
                '{"same_category_mid@40-59": 20, "same_category_mid@60-79": 12}',
            )
            self.assertEqual(
                rows[0]["failed_gates"],
                ["acc_ok", "antonym_strict_mid_recall_ok", "regression_ok"],
            )
            self.assertEqual(rows[1]["stamp"], "20260613_230005")

    def test_nightly_dry_run_runs_three_rounds_and_copies_round_base_from_project_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare_fake_repo(root)
            self._write_round_aware_python(root / ".venv" / "bin" / "python")

            nightly_script_copy = root / "scripts" / "nightly_train_v26.sh"
            nightly_script_copy.write_text(NIGHTLY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            nightly_script_copy.chmod(nightly_script_copy.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["NIGHTLY_ROOT"] = str(root / ".nightly")
            env["NIGHTLY_ENFORCE_FREE_SPACE_CHECK"] = "0"
            env["NIGHTLY_DRY_RUN"] = "1"
            env["NIGHTLY_TOTAL_RUNS"] = "3"
            env["NIGHTLY_SCRIPT_ROOT"] = str(root)

            result = subprocess.run(
                ["bash", str(nightly_script_copy)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            output = result.stdout + result.stderr
            self.assertIn("[nightly] root=", output)
            self.assertIn("[nightly] ===== round 1/3 =====", output)
            self.assertIn("[nightly] ===== round 2/3 =====", output)
            self.assertIn("[nightly] ===== round 3/3 =====", output)
            self.assertIn("[nightly] round_seed=20260303 data_split_seed=20260303", output)
            self.assertIn("[nightly] round_seed=20260304 data_split_seed=20260303", output)
            self.assertIn("[nightly] round_seed=20260305 data_split_seed=20260303", output)
            self.assertEqual(output.count("copy round base model from project"), 3, msg=output)
            self.assertNotIn("workspaces/guess_runtime", output)

            reports_dir = root / ".nightly" / "reports"
            promotion_records = sorted(reports_dir.glob("nightly_promotion_*.md"))
            self.assertTrue(promotion_records, msg=f"no promotion report found in {reports_dir}\n{output}")
            promotion_text = promotion_records[-1].read_text(encoding="utf-8")
            run_logs = sorted((root / ".nightly" / "data" / "tmp").glob("nightly_train_v26_*.log"))
            self.assertTrue(run_logs, msg=f"no nightly run log found\n{output}")
            self.assertIn("[nightly] start at", run_logs[-1].read_text(encoding="utf-8"))
            self.assertIn("## 运行配置", promotion_text)
            self.assertIn("| requested_device | auto |", promotion_text)
            self.assertIn("| sup_rows | 300 |", promotion_text)
            self.assertIn("| data_split_seed | 20260303 |", promotion_text)
            self.assertIn("| train_sample_seed | 20260303 |", promotion_text)
            self.assertIn("## 晋升门控", promotion_text)
            self.assertIn("| min_antonym_mid_recall_improvement | 0.0 |", promotion_text)
            self.assertIn("| regression_gate | passed == total |", promotion_text)

    def test_nightly_cleans_stale_lock_before_starting_new_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare_fake_repo(root)
            self._write_round_aware_python(root / ".venv" / "bin" / "python")

            lock_dir = root / ".nightly" / "data" / "tmp" / ".nightly_train_v26.lock"
            lock_dir.mkdir(parents=True)
            (lock_dir / "pid").write_text("999999\n", encoding="utf-8")

            nightly_script_copy = root / "scripts" / "nightly_train_v26.sh"
            nightly_script_copy.write_text(NIGHTLY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            nightly_script_copy.chmod(nightly_script_copy.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["NIGHTLY_ROOT"] = str(root / ".nightly")
            env["NIGHTLY_ENFORCE_FREE_SPACE_CHECK"] = "0"
            env["NIGHTLY_DRY_RUN"] = "1"
            env["NIGHTLY_TOTAL_RUNS"] = "1"
            env["NIGHTLY_SCRIPT_ROOT"] = str(root)

            result = subprocess.run(
                ["bash", str(nightly_script_copy)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            output = result.stdout + result.stderr
            self.assertIn("stale lock detected", output)
            self.assertNotIn("another training is running, skip", output)
            self.assertFalse(lock_dir.exists())

    def test_nightly_promotes_best_round_records_summary_and_cleans_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare_fake_repo(root)
            self._write_round_aware_python(root / ".venv" / "bin" / "python")

            nightly_script_copy = root / "scripts" / "nightly_train_v26.sh"
            nightly_script_copy.write_text(NIGHTLY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            nightly_script_copy.chmod(nightly_script_copy.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["NIGHTLY_ROOT"] = str(root / ".nightly")
            env["NIGHTLY_ENFORCE_FREE_SPACE_CHECK"] = "0"
            env["NIGHTLY_TOTAL_RUNS"] = "3"
            env["NIGHTLY_SCRIPT_ROOT"] = str(root)
            env["NIGHTLY_ENABLE_ANCHOR_FINETUNE"] = "0"
            env["NIGHTLY_REQUIRE_NO_DEGRADE_ALL"] = "0"
            env["NIGHTLY_REQUIRE_STRICT_IMPROVEMENT"] = "1"
            env["NIGHTLY_MIN_MAE_IMPROVEMENT"] = "0.0"
            env["NIGHTLY_MIN_ACC_IMPROVEMENT"] = "0.0"

            result = subprocess.run(
                ["bash", str(nightly_script_copy)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            output = result.stdout + result.stderr
            self.assertIn("project_antonym_mid_recall_45_55=100.00", output)
            self.assertIn("best_antonym_mid_recall_45_55=100.00", output)

            # Promotion report should exist
            reports_dir = root / ".nightly" / "reports"
            promotion_records = sorted(reports_dir.glob("nightly_promotion_*.md"))
            self.assertTrue(promotion_records, msg=f"no promotion report found in {reports_dir}\n{output}")
            promotion_text = promotion_records[-1].read_text(encoding="utf-8")
            self.assertIn("最佳轮次**: 2", promotion_text)
            self.assertIn("已晋升", promotion_text)

            # Best round 2 model should be promoted to models/
            promoted_marker = root / "models" / "bge-m3-finetuned-v27-semreal-anchor" / "round.txt"
            self.assertTrue(promoted_marker.exists(),
                           msg=f"promoted marker missing. models/ contents: {list((root / 'models').glob('**/*'))}\n{output}")
            self.assertEqual(promoted_marker.read_text(encoding="utf-8").strip(), "2")

            # Nightly run artifacts should be cleaned
            output_model_base = root / ".nightly" / "data" / "models" / "bge-m3-finetuned-local-candidate"
            remaining = list(output_model_base.parent.glob("bge-m3-finetuned-local-candidate*"))
            self.assertEqual(remaining, [], msg=f"nightly artifacts not cleaned: {remaining}\n{output}")

    def test_nightly_script_passes_support_positive_target_low_to_gate_and_best_round_eval(self):
        source = NIGHTLY_SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count('SEM_CALIB_SUPPORT_POSITIVE_TARGET_LOW="$CALIB_SUPPORT_POSITIVE_TARGET_LOW"'), 4)
        self.assertIn('KEEP_REJECTED_CALIBRATION="${NIGHTLY_KEEP_REJECTED_CALIBRATION:-1}"', source)
        project_gate = source.split("# Gate against project model", 1)[1]
        self.assertIn("b_ant_strict_recall = float(base_ant.get('mid_score_recall_45_55', 0.0))", project_gate)
        self.assertIn("c_ant_strict_recall = float(cand_ant.get('mid_score_recall_45_55', 0.0))", project_gate)

    def test_nightly_keeps_data_split_seed_fixed_but_training_seed_per_round(self):
        source = NIGHTLY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('DATA_SPLIT_SEED="${NIGHTLY_DATA_SPLIT_SEED:-$BASE_SEED}"', source)
        self.assertIn('run_cmd "SEM_SEED=$DATA_SPLIT_SEED \\\n    SEM_PUZZLES_JSON=', source)
        self.assertIn('SEM_SEED=$round_seed \\\n      SEM_SAMPLE_SEED=$DATA_SPLIT_SEED \\\n      SEM_TRAIN_CSV=', source)
        self.assertIn('SEM_SEED=$round_seed \\\n          SEM_SAMPLE_SEED=$DATA_SPLIT_SEED \\\n          SEM_TRAIN_CSV=', source)

    def test_nightly_rejected_candidate_report_includes_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare_fake_repo(root)
            self._write_round_aware_python(root / ".venv" / "bin" / "python")

            nightly_script_copy = root / "scripts" / "nightly_train_v26.sh"
            nightly_script_copy.write_text(NIGHTLY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            nightly_script_copy.chmod(nightly_script_copy.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["NIGHTLY_ROOT"] = str(root / ".nightly")
            env["NIGHTLY_ENFORCE_FREE_SPACE_CHECK"] = "0"
            env["NIGHTLY_TOTAL_RUNS"] = "1"
            env["NIGHTLY_SCRIPT_ROOT"] = str(root)
            env["NIGHTLY_ENABLE_ANCHOR_FINETUNE"] = "0"
            env["NIGHTLY_MIN_MAE_IMPROVEMENT"] = "999.0"
            env["NIGHTLY_REQUIRE_NO_DEGRADE_ALL"] = "0"

            result = subprocess.run(
                ["bash", str(nightly_script_copy)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            reports_dir = root / ".nightly" / "reports"
            promotion_records = sorted(reports_dir.glob("nightly_promotion_*.md"))
            self.assertTrue(promotion_records, msg=result.stdout + result.stderr)
            promotion_text = promotion_records[-1].read_text(encoding="utf-8")
            self.assertIn("无轮次通过门控", promotion_text)
            self.assertIn("训练数据分布 Round 1", promotion_text)
            self.assertIn("Top Train Tags", promotion_text)
            self.assertIn("实际训练抽样 Round 1", promotion_text)
            self.assertIn("| antonym_mid_rows | 51 |", promotion_text)
            self.assertIn("| antonym_mid_examples_after_repeat | 153 |", promotion_text)
            self.assertIn("| cosent_excluded_examples_after_repeat | 153 |", promotion_text)
            self.assertIn("| min_tag_rows | {\"antonym_mid\": 45} |", promotion_text)
            self.assertIn(
                "| min_tag_bucket_rows | {\"same_category_mid@40-59\": 20, \"same_category_mid@60-79\": 12} |",
                promotion_text,
            )
            self.assertIn("拒绝诊断 Round 1", promotion_text)
            self.assertIn("hard_negative", promotion_text)
            self.assertIn("synonym_alias", promotion_text)
            self.assertIn("校准桶错分 Top", promotion_text)
            self.assertIn("| 80-100 | 60-80 |", promotion_text)
            base_metrics = sorted((root / ".nightly" / "data" / "tmp").glob("nightly_base_metrics_*.json"))
            cand_metrics = sorted((root / ".nightly" / "data" / "tmp").glob("nightly_candidate_metrics_*.json"))
            self.assertTrue(base_metrics, msg=result.stdout + result.stderr)
            self.assertTrue(cand_metrics, msg=result.stdout + result.stderr)
            self.assertEqual(
                json.loads(base_metrics[-1].read_text(encoding="utf-8"))["support_positive_calibration_target_low"],
                60.0,
            )
            self.assertEqual(
                json.loads(cand_metrics[-1].read_text(encoding="utf-8"))["support_positive_calibration_target_low"],
                60.0,
            )
            train_stats = sorted((root / ".nightly" / "data" / "tmp").glob("nightly_train_stats_*.json"))
            self.assertTrue(train_stats, msg=result.stdout + result.stderr)
            self.assertEqual(json.loads(train_stats[-1].read_text(encoding="utf-8"))["sample_seed"], 20260303)
            retained_calibrations = sorted(
                (root / ".nightly" / "data" / "tmp").glob("semantic_calibration_local_candidate_*.json")
            )
            self.assertTrue(retained_calibrations, msg="rejected candidate calibration was not retained")

    def test_nightly_auto_device_retries_supervised_training_on_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare_fake_repo(root)
            self._write_round_aware_python(root / ".venv" / "bin" / "python")

            nightly_script_copy = root / "scripts" / "nightly_train_v26.sh"
            nightly_script_copy.write_text(NIGHTLY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            nightly_script_copy.chmod(nightly_script_copy.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["NIGHTLY_ROOT"] = str(root / ".nightly")
            env["NIGHTLY_ENFORCE_FREE_SPACE_CHECK"] = "0"
            env["NIGHTLY_TOTAL_RUNS"] = "1"
            env["NIGHTLY_SCRIPT_ROOT"] = str(root)
            env["NIGHTLY_ENABLE_ANCHOR_FINETUNE"] = "0"
            env["NIGHTLY_REQUIRE_NO_DEGRADE_ALL"] = "0"
            env["NIGHTLY_MIN_MAE_IMPROVEMENT"] = "0.0"
            env["NIGHTLY_MIN_ACC_IMPROVEMENT"] = "0.0"
            env["FAKE_FAIL_SUPERVISED_UNLESS_CPU"] = "1"

            result = subprocess.run(
                ["bash", str(nightly_script_copy)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            output = result.stdout + result.stderr
            self.assertIn("retry with SEM_DEVICE=cpu", output)
            self.assertIn("ACCELERATE_USE_CPU=true", output)
            self.assertIn("saved=", output)

    def test_extract_score_trace_review_candidates_writes_pending_review_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "score_trace.log"
            out_path = tmp_path / "score_trace_review_candidates.csv"
            log_path.write_text(
                "\n".join(
                    [
                        '[score_trace] {"event":"semantic_mix","guess":"刘备","answer":"猫咪","final":86,"notes":["cap"]}',
                        '[score_trace] {"event":"semantic_mix","guess":"大夫","answer":"医生","final":18,"notes":[]}',
                        '[score_trace] {"event":"exact_match","guess":"猫","answer":"猫","final":100}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TRACE_EXTRACT_SCRIPT),
                    str(log_path),
                    "--output",
                    str(out_path),
                    "--created-at",
                    "2026-06-01",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with out_path.open("r", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["review_status"], "pending")
            self.assertEqual(rows[0]["source"], "score_trace")
            self.assertIn(rows[0]["error_type"], {"possible_false_positive_high_score", "possible_false_negative_low_score"})

    def test_extract_nightly_worst_cases_writes_pending_review_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_path = tmp_path / "nightly_promotion_20260604_230005.md"
            out_path = tmp_path / "nightly_worst_case_review_candidates.csv"
            report_path.write_text(
                textwrap.dedent(
                    """\
                    # Nightly Promotion Report - 20260604_230005

                    **结果**: 无轮次通过门控，未晋升

                    ### 候选最差样本

                    | answer | input | target | candidate | error | group | tag |
                    |--------|-------|--------|-----------|-------|-------|-----|
                    | 飞机 | 轮船 | 22.0 | 75.4 | 53.4 | hard_negative | same_category_but_far |
                    | 高兴 | 难过 | 10.0 | 61.0 | 51.0 | hard_negative | antonym_or_conflict |

                    ### 校准桶错分 Top

                    | target_bucket | predicted_bucket | base_count | cand_count | cand_avg_error | top_tags | top_groups | examples |
                    |---------------|------------------|------------|------------|----------------|----------|------------|----------|
                    | 80-100 | 60-80 | 1 | 2 | 18.5 | alias_synonym_high:2 | synonym_alias:2 | 医生->大夫, 开心->快乐 |
                    """
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(WORST_CASE_EXTRACT_SCRIPT),
                    "--report",
                    str(report_path),
                    "--output",
                    str(out_path),
                    "--min-error",
                    "18",
                    "--created-at",
                    "2026-06-05",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            with out_path.open("r", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 4)
            row = rows[0]
            self.assertEqual(row["answer"], "飞机")
            self.assertEqual(row["user_input"], "轮船")
            self.assertEqual(row["current_score"], "75")
            self.assertEqual(row["corrected_score"], "22")
            self.assertEqual(row["error_type"], "same_category_but_far")
            self.assertEqual(row["review_status"], "pending")
            self.assertEqual(row["source"], "nightly_worst_case")
            antonym = rows[1]
            self.assertEqual(antonym["answer"], "高兴")
            self.assertEqual(antonym["user_input"], "难过")
            self.assertEqual(antonym["corrected_score"], "50")
            self.assertEqual(antonym["error_type"], "antonym_mid")
            bucket = rows[2]
            self.assertEqual(bucket["answer"], "医生")
            self.assertEqual(bucket["user_input"], "大夫")
            self.assertEqual(bucket["current_score"], "70")
            self.assertEqual(bucket["corrected_score"], "90")
            self.assertEqual(bucket["error_type"], "alias_synonym_high")
            self.assertEqual(bucket["natural_relation"], "synonym_alias")
            self.assertEqual(bucket["source"], "nightly_bucket_confusion")

    def test_validate_review_candidates_blocks_bad_approved_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            review_path = tmp_path / "review.csv"
            review_path.write_text(
                textwrap.dedent(
                    """\
                    case_id,answer,user_input,current_score,corrected_score,error_type,error_severity,why_wrong,natural_relation,evidence,review_status,reviewer,source,created_at
                    1,高兴,难过,10,40,antonym_or_conflict,high,approved bad antonym,antonym,x,approved,,nightly_worst_case,2026-06-07
                    2,猫,猫咪,80,95,alias_synonym_high,medium,ok,synonym_alias,x,pending,,nightly_bucket_confusion,2026-06-07
                    3,猫,猫咪,80,95,alias_synonym_high,medium,duplicate,synonym_alias,x,pending,,nightly_bucket_confusion,2026-06-07
                    """
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(VALIDATE_REVIEW_SCRIPT), str(review_path), "--json"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stdout)
            payload = json.loads(result.stdout)
            problems = "\n".join(";".join(item["problems"]) for item in payload["issues"])
            self.assertIn("antonym rows must have corrected_score=50", problems)
            self.assertIn("duplicate pair", problems)

    def test_validate_review_candidates_allows_clean_pending_and_approved_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            review_path = tmp_path / "review.csv"
            review_path.write_text(
                textwrap.dedent(
                    """\
                    case_id,answer,user_input,current_score,corrected_score,error_type,error_severity,why_wrong,natural_relation,evidence,review_status,reviewer,source,created_at
                    1,高兴,难过,10,50,antonym_mid,high,approved antonym,antonym,x,approved,,nightly_worst_case,2026-06-07
                    2,医生,大夫,70,90,alias_synonym_high,medium,pending synonym,synonym_alias,x,pending,,nightly_bucket_confusion,2026-06-07
                    """
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(VALIDATE_REVIEW_SCRIPT), str(review_path), "--json"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["training_rows"], 1)

    def test_build_nightly_semantic_sets_keeps_fixed_holdout_out_of_train_and_calib(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            holdout_path = tmp_path / "holdout.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n"
                "刘备,猫咪,hard_negative_low,10,1.0\n"
                "香蕉,苹果,same_category_mid,55,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "香蕉,苹果,same_category_but_far,25,4.0\n"
                "刘备,猫咪,hard_negative_low,10,4.0\n"
                "开心,伤心,antonym_low,10,4.0\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n",
                encoding="utf-8",
            )
            holdout_path.write_text(
                "answer,user_input,relation_tag,score_0_100,status\n"
                "猫咪,刘备,hard_negative_low,10,frozen\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": str(holdout_path),
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            def read_pairs(path: Path) -> set[tuple[str, str]]:
                with path.open("r", encoding="utf-8") as file:
                    return {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}

            holdout_pair = ("猫咪", "刘备")
            reverse_holdout_pair = ("刘备", "猫咪")
            self.assertNotIn(holdout_pair, read_pairs(train_out))
            self.assertNotIn(reverse_holdout_pair, read_pairs(train_out))
            self.assertNotIn(holdout_pair, read_pairs(calib_out))
            self.assertNotIn(reverse_holdout_pair, read_pairs(calib_out))
            self.assertIn(holdout_pair, read_pairs(eval_out))
            self.assertIn(("香蕉", "苹果"), read_pairs(train_out))
            self.assertIn(("开心", "伤心"), read_pairs(train_out))
            with train_out.open("r", encoding="utf-8") as file:
                train_rows = list(csv.DictReader(file))
            banana_row = next(row for row in train_rows if (row["answer"], row["user_input"]) == ("香蕉", "苹果"))
            self.assertEqual(banana_row["reviewer"], "train_patch")
            self.assertEqual(banana_row["relation_tag"], "same_category_but_far")
            antonym_row = next(row for row in train_rows if (row["answer"], row["user_input"]) == ("开心", "伤心"))
            self.assertEqual(antonym_row["relation_tag"], "antonym_mid")
            self.assertEqual(antonym_row["score_0_100"], "50")
            self.assertEqual(antonym_row["expected_range"], "45-55")
            self.assertEqual(antonym_row["sample_weight"], "4.0000")
            required_antonym_row = next(row for row in train_rows if (row["answer"], row["user_input"]) == ("古代", "现代"))
            self.assertEqual(required_antonym_row["reviewer"], "required_antonym_patch")
            self.assertEqual(required_antonym_row["relation_tag"], "antonym_mid")
            self.assertEqual(required_antonym_row["score_0_100"], "50")
            self.assertEqual(required_antonym_row["sample_weight"], "4.0000")
            extra_required_antonym_row = next(
                row for row in train_rows if (row["answer"], row["user_input"]) == ("永恒", "瞬间")
            )
            self.assertEqual(extra_required_antonym_row["reviewer"], "required_antonym_patch")
            self.assertEqual(extra_required_antonym_row["relation_tag"], "antonym_mid")
            self.assertEqual(extra_required_antonym_row["score_0_100"], "50")
            emotion_required_antonym_row = next(
                row for row in train_rows if (row["answer"], row["user_input"]) == ("欣喜", "郁闷")
            )
            self.assertEqual(emotion_required_antonym_row["reviewer"], "required_antonym_patch")
            self.assertEqual(emotion_required_antonym_row["relation_tag"], "antonym_mid")
            self.assertEqual(emotion_required_antonym_row["score_0_100"], "50")
            self.assertFalse(any((row["answer"], row["user_input"]) == ("高兴", "伤心") for row in train_rows))
            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["fixed_holdout"], 1)
            self.assertEqual(stats["eval_antonym_rows"], 0)
            self.assertEqual(stats["eval_holdout_antonym_rows"], 0)
            self.assertEqual(stats["eval_non_holdout_antonym_rows"], 0)
            self.assertEqual(stats["train_patch"], 10)
            self.assertEqual(stats["required_proxy_antonym_train_rows"], 0)
            self.assertEqual(stats["required_proxy_antonym_calib_rows"], 0)
            self.assertEqual(stats["antonym_calib_anchor_rows"], 0)
            self.assertGreaterEqual(stats["train_gold"], 1)

    def test_build_nightly_semantic_sets_filters_base_rows_that_conflict_with_curated_gold_bidirectionally(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            scored_path = tmp_path / "scored.csv"
            extra_gold_path = tmp_path / "extra_gold.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"钢琴","category":"乐器","hints":["黑白键"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "钢琴,小提琴,same_category_mid,40,1.0,base_train\n"
                "小提琴,钢琴,same_category_mid,40,1.0,base_train\n"
                "猫咪,刘备,hard_negative_low,10,1.0,base_train\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n",
                encoding="utf-8",
            )
            extra_gold_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer\n"
                "钢琴,小提琴,same_category_but_far,30,manual_review\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": "",
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": str(extra_gold_path),
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            all_rows = []
            for path in (train_out, calib_out, eval_out):
                with path.open("r", encoding="utf-8") as file:
                    all_rows.extend(list(csv.DictReader(file)))

            pair_rows = [
                row
                for row in all_rows
                if {row["answer"], row["user_input"]} == {"钢琴", "小提琴"}
            ]
            self.assertTrue(pair_rows)
            self.assertFalse(any(row["reviewer"] == "base_train" for row in pair_rows))
            self.assertFalse(any(row["score_0_100"] == "40" for row in pair_rows))
            self.assertTrue(any(row["score_0_100"] == "30" for row in pair_rows))

    def test_build_nightly_semantic_sets_prevents_train_eval_overlap_for_scored_pairs_already_in_base_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"欣赏","category":"情感","hints":["观察"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "欣赏,欣慰,same_category_mid,60,1.0,scored_user_input\n"
                "掉线,连接断,hint_like_high,80,1.0,scored_user_input\n"
                "猫咪,刘备,hard_negative_low,10,1.0,base_train\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer\n"
                "欣赏,欣慰,same_category_mid,60,scored_user_input\n"
                "温馨,依恋,same_category_mid,60,scored_user_input\n"
                "羡慕,惊讶,same_category_mid,60,scored_user_input\n"
                "愤懑,敬佩,same_category_mid,60,scored_user_input\n"
                "掉线,连接断,hint_like_high,80,scored_user_input\n"
                "停下,不再动,hint_like_high,80,scored_user_input\n"
                "海洋,潮汐,hint_like_high,80,scored_user_input\n"
                "泡澡,热水,hint_like_high,80,scored_user_input\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": "",
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                    "SEM_SEED": "1",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            with eval_out.open("r", encoding="utf-8") as file:
                eval_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}

            self.assertEqual(train_pairs & eval_pairs, set())
            self.assertIn(("欣赏", "欣慰"), eval_pairs)
            self.assertNotIn(("欣赏", "欣慰"), train_pairs)
            self.assertNotIn(("掉线", "连接断"), eval_pairs & train_pairs)

            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["train_eval_exact_overlap"], 0)
            self.assertEqual(stats["train_eval_symmetric_overlap"], 0)
            self.assertEqual(stats["eval_calib_exact_overlap"], 0)
            self.assertEqual(stats["unexpected_train_calib_exact_overlap"], 0)

    def test_build_nightly_semantic_sets_keeps_bidirectional_pairs_in_single_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"开心","category":"情感","hints":["心情很好"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer\n"
                "开心,高兴,near_synonym_high,80,manual_gold_v26\n"
                "高兴,开心,near_synonym_high,80,manual_gold_v26\n"
                "孔明,诸葛亮,alias_synonym_high,85,manual_gold_v26\n"
                "诸葛亮,孔明,alias_synonym_high,85,manual_gold_v26\n"
                "不知道,总结,hard_negative_low,10,manual_gold_v26\n"
                "总结,不知道,hard_negative_low,10,manual_gold_v26\n"
                "你个der,猫咪,hard_negative_low,10,manual_gold_v26\n"
                "猫咪,你个der,hard_negative_low,10,manual_gold_v26\n"
                "停下,不再动,hint_like_high,80,scored_user_input\n"
                "掉线,连接断,hint_like_high,80,scored_user_input\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": "",
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                    "SEM_SEED": "3",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            split_rows = {}
            for split_name, path in (
                ("train", train_out),
                ("calib", calib_out),
                ("eval", eval_out),
            ):
                with path.open("r", encoding="utf-8") as file:
                    split_rows[split_name] = list(csv.DictReader(file))

            def containing_splits(pair_set):
                return {
                    split_name
                    for split_name, rows in split_rows.items()
                    if any({row["answer"], row["user_input"]} == pair_set for row in rows)
                }

            self.assertEqual(len(containing_splits({"开心", "高兴"})), 1)
            self.assertEqual(len(containing_splits({"孔明", "诸葛亮"})), 1)
            self.assertEqual(len(containing_splits({"不知道", "总结"})), 1)
            self.assertEqual(len(containing_splits({"你个der", "猫咪"})), 1)

            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["train_eval_symmetric_overlap"], 0)
            self.assertEqual(stats["eval_calib_symmetric_overlap"], 0)
            self.assertEqual(stats["train_calib_symmetric_overlap"], 0)
            self.assertEqual(stats["unexpected_train_calib_symmetric_overlap"], 0)
            self.assertEqual(stats["unexpected_train_calib_exact_overlap"], 0)

    def test_build_nightly_semantic_sets_excludes_suggested_relabel_noise_rows_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            extra_gold_path = tmp_path / "extra_gold.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"死神","category":"动漫","hints":["斩魄刀"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "猫咪,刘备,hard_negative_low,10,1.0,base_train\n",
                encoding="utf-8",
            )
            extra_gold_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer,sample_weight\n"
                "死神,鬼灭之刃,near_synonym_high,82,suggested_relabel_ab_v1,0.8\n"
                "医生,大夫,near_synonym_high,80,manual_review,1.0\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": "",
                    "SEM_SCORED_CSV": str(extra_gold_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            all_rows = []
            for path in (train_out, calib_out, eval_out, pool_out):
                with path.open("r", encoding="utf-8") as file:
                    all_rows.extend(list(csv.DictReader(file)))

            self.assertFalse(
                any((row["answer"], row["user_input"]) == ("死神", "鬼灭之刃") for row in all_rows)
            )
            self.assertTrue(
                any((row["answer"], row["user_input"]) == ("医生", "大夫") for row in all_rows)
            )

            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["excluded_reviewer_rows"], 1)
            self.assertEqual(stats["excluded_reviewer_counts"], {"suggested_relabel_ab_v1": 1})

    def test_build_nightly_semantic_sets_reserves_non_holdout_antonym_gold_rows_for_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            holdout_path = tmp_path / "holdout.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"高兴","category":"情感","hints":["心情很好"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            holdout_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer\n"
                "高兴,难过,antonym_mid,50,error_review_v1\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer\n"
                "虚无,存在,antonym_mid,50,semantic_error_review_template_v1\n"
                "学校,校园,related_mid,55,scored_user_input\n"
                "苹果,水果,related_mid,55,scored_user_input\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": "",
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": str(holdout_path),
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                    "SEM_EVAL_TO_CALIB_ANCHOR_WEIGHT": "6.0",
                    "SEM_SEED": "6",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            with eval_out.open("r", encoding="utf-8") as file:
                eval_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}

            self.assertIn(("虚无", "存在"), calib_pairs)
            self.assertNotIn(("虚无", "存在"), eval_pairs)
            self.assertIn(("高兴", "难过"), eval_pairs)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            reserved_row = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("虚无", "存在")
            )
            self.assertEqual(reserved_row["sample_weight"], "6.0000")

            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["gold_to_calib_tags"], ["antonym_mid"])
            self.assertEqual(stats["gold_to_calib_rows"], 1)
            self.assertEqual(stats["gold_to_calib_weight"], 6.0)
            self.assertEqual(stats["eval_to_calib_tags"], ["antonym_mid"])
            self.assertEqual(stats["eval_to_calib_rows"], 0)
            self.assertEqual(stats["eval_antonym_rows"], 1)
            self.assertEqual(stats["eval_holdout_antonym_rows"], 1)
            self.assertEqual(stats["eval_non_holdout_antonym_rows"], 0)
            self.assertEqual(stats["required_proxy_antonym_calib_rows"], 3)
            self.assertEqual(stats["calib_antonym_rows"], 4)

    def test_build_nightly_semantic_sets_rejects_non_holdout_antonym_eval_rows(self):
        spec = importlib.util.spec_from_file_location(
            "build_nightly_semantic_sets_partition_guard",
            BUILD_NIGHTLY_SETS_SCRIPT,
        )
        self.assertIsNotNone(spec)
        builder = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            spec.loader.exec_module(builder)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        with self.assertRaises(SystemExit) as error:
            builder.validate_dataset_partition(
                train_rows=[],
                calib_rows=[],
                eval_rows=[
                    {
                        "answer": "虚无",
                        "user_input": "存在",
                        "relation_tag": "antonym_mid",
                    }
                ],
                holdout_rows=[
                    {
                        "answer": "高兴",
                        "user_input": "难过",
                        "relation_tag": "antonym_mid",
                    }
                ],
            )
        self.assertIn("unexpected_eval_antonym_mid_rows", str(error.exception))

    def test_build_nightly_semantic_sets_rejects_reversed_train_calib_overlap(self):
        spec = importlib.util.spec_from_file_location(
            "build_nightly_semantic_sets_reversed_train_calib_guard",
            BUILD_NIGHTLY_SETS_SCRIPT,
        )
        self.assertIsNotNone(spec)
        builder = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            spec.loader.exec_module(builder)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        with self.assertRaises(SystemExit) as error:
            builder.validate_dataset_partition(
                train_rows=[
                    {
                        "answer": "开心",
                        "user_input": "伤心",
                        "relation_tag": "antonym_mid",
                        "reviewer": "antonym_script",
                        "sample_weight": "2.5",
                    }
                ],
                calib_rows=[
                    {
                        "answer": "伤心",
                        "user_input": "开心",
                        "relation_tag": "antonym_mid",
                        "reviewer": "nightly_patch_v1",
                        "sample_weight": "10.0",
                    }
                ],
                eval_rows=[],
                holdout_rows=[],
            )
        self.assertIn("unexpected_train_calib_symmetric_overlap", str(error.exception))

        stats = builder.validate_dataset_partition(
            train_rows=[
                {
                    "answer": "高兴",
                    "user_input": "伤心",
                    "relation_tag": "antonym_mid",
                    "reviewer": "required_antonym_proxy_train",
                    "sample_weight": "4.0",
                }
            ],
            calib_rows=[
                {
                    "answer": "高兴",
                    "user_input": "伤心",
                    "relation_tag": "antonym_mid",
                    "reviewer": "required_antonym_proxy_calib",
                    "sample_weight": "13.0",
                }
            ],
            eval_rows=[],
            holdout_rows=[
                {"answer": "高兴", "user_input": "难过", "relation_tag": "antonym_mid"}
            ],
        )
        self.assertEqual(stats["train_calib_symmetric_overlap"], 1)
        self.assertEqual(stats["unexpected_train_calib_symmetric_overlap"], 0)
        self.assertEqual(stats["train_calib_exact_overlap"], 1)
        self.assertEqual(stats["allowed_train_calib_exact_overlap"], 1)

    def test_build_nightly_semantic_sets_prefers_required_proxy_rows_on_pair_collision(self):
        spec = importlib.util.spec_from_file_location(
            "build_nightly_semantic_sets_proxy_precedence",
            BUILD_NIGHTLY_SETS_SCRIPT,
        )
        self.assertIsNotNone(spec)
        builder = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            spec.loader.exec_module(builder)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        holdout_keys = {builder.canonical_pair("高兴", "难过")}
        proxy_train_rows = builder.required_holdout_family_proxy_training_rows(holdout_keys)
        proxy_calib_rows = builder.required_holdout_family_proxy_calibration_rows(holdout_keys)
        self.assertEqual(len(proxy_train_rows), 3)
        self.assertEqual(len(proxy_calib_rows), 3)

        existing_train_row = dict(proxy_train_rows[0])
        existing_train_row.update(
            {
                "answer": proxy_train_rows[0]["user_input"],
                "user_input": proxy_train_rows[0]["answer"],
                "reviewer": "nightly_patch_v1",
                "sample_weight": "2.5",
            }
        )
        existing_calib_row = dict(proxy_calib_rows[0])
        existing_calib_row.update(
            {
                "answer": proxy_calib_rows[0]["user_input"],
                "user_input": proxy_calib_rows[0]["answer"],
                "reviewer": "nightly_patch_v1",
                "sample_weight": "10.0",
            }
        )
        merged_train = builder.dedupe_with_preferred_rows(
            proxy_train_rows,
            [existing_train_row, *proxy_train_rows[1:]],
        )
        merged_calib = builder.dedupe_with_preferred_rows(
            proxy_calib_rows,
            [existing_calib_row, *proxy_calib_rows[1:]],
        )

        train_row = next(
            row for row in merged_train if row["answer"] == proxy_train_rows[0]["answer"]
            and row["user_input"] == proxy_train_rows[0]["user_input"]
        )
        calib_row = next(
            row for row in merged_calib if row["answer"] == proxy_calib_rows[0]["answer"]
            and row["user_input"] == proxy_calib_rows[0]["user_input"]
        )
        self.assertNotIn(
            (proxy_train_rows[0]["user_input"], proxy_train_rows[0]["answer"]),
            {(row["answer"], row["user_input"]) for row in merged_train},
        )
        self.assertNotIn(
            (proxy_calib_rows[0]["user_input"], proxy_calib_rows[0]["answer"]),
            {(row["answer"], row["user_input"]) for row in merged_calib},
        )
        self.assertEqual(train_row["reviewer"], "required_antonym_proxy_train")
        self.assertEqual(calib_row["reviewer"], "required_antonym_proxy_calib")
        self.assertEqual(calib_row["sample_weight"], "13.0000")

    def test_build_nightly_semantic_sets_mirrors_required_holdout_family_proxy_rows_to_train_and_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            holdout_path = tmp_path / "holdout.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"高兴","category":"情感","hints":["心情很好"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            holdout_path.write_text(
                "answer,user_input,relation_tag,score_0_100,reviewer\n"
                "高兴,难过,antonym_mid,50,error_review_v1\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "学校,校园,related_mid,55\n"
                "苹果,水果,related_mid,55\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": "",
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": str(holdout_path),
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "1",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "10.0",
                    "SEM_PRIORITY_ANTONYM_CALIB_ANCHOR_WEIGHT": "13.0",
                    "SEM_SEED": "6",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            proxy_row = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("高兴", "伤心")
            )
            self.assertEqual(proxy_row["reviewer"], "required_antonym_proxy_calib")
            self.assertEqual(proxy_row["sample_weight"], "13.0000")

            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            for proxy_pair in (("高兴", "伤心"), ("开心", "悲伤"), ("快乐", "难过")):
                self.assertIn(proxy_pair, train_pairs)
            self.assertNotIn(("高兴", "难过"), train_pairs)

            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["antonym_calib_anchor_rows"], 0)
            self.assertEqual(stats["required_proxy_antonym_train_rows"], 3)
            self.assertEqual(stats["required_proxy_antonym_calib_rows"], 3)
            self.assertEqual(stats["priority_antonym_calib_anchor_rows"], 0)
            self.assertEqual(stats["priority_antonym_calib_weight_rows"], 0)
            self.assertEqual(stats["calib_antonym_rows"], 3)
            self.assertEqual(stats["train_calib_symmetric_overlap"], 3)
            self.assertEqual(stats["unexpected_train_calib_symmetric_overlap"], 0)

    def test_build_nightly_semantic_sets_can_reserve_antonym_patch_rows_for_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "开心,伤心,antonym_mid,50,4.0,nightly_patch_v1\n"
                "快乐,痛苦,antonym_mid,50,4.0,nightly_patch_v1\n"
                "古代,现代,antonym_mid,50,4.0,required_antonym_patch\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n"
                "学校,校园,related_mid,60\n"
                "苹果,水果,related_mid,55\n"
                "老师,教师,near_synonym_high,85\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "1",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "6.0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            with calib_out.open("r", encoding="utf-8") as file:
                calib_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            reserved = {("开心", "伤心"), ("快乐", "痛苦")}
            self.assertEqual(len(reserved & calib_pairs), 1)
            self.assertEqual(len(reserved & train_pairs), 2)
            self.assertIn(("古代", "现代"), train_pairs)
            self.assertNotIn(("古代", "现代"), calib_pairs)
            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            reserved_row = next(row for row in calib_rows if (row["answer"], row["user_input"]) in reserved)
            self.assertEqual(reserved_row["sample_weight"], "6.0000")
            self.assertIn((reserved_row["answer"], reserved_row["user_input"]), train_pairs)
            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["antonym_calib_anchor_rows"], 1)
            self.assertEqual(stats["required_proxy_antonym_calib_rows"], 0)
            self.assertEqual(stats["priority_antonym_calib_anchor_rows"], 0)
            self.assertEqual(stats["priority_antonym_calib_weight_rows"], 0)
            self.assertEqual(stats["calib_antonym_rows"], 1)

    def test_build_nightly_semantic_sets_prioritizes_v2_antonym_patch_rows_for_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "开心,伤心,antonym_mid,50,4.0,nightly_patch_v1\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n"
                "学校,校园,related_mid,60\n"
                "苹果,水果,related_mid,55\n"
                "老师,教师,near_synonym_high,85\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "1",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "6.0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            reserved_row = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("高兴", "难过")
            )
            self.assertEqual((reserved_row["answer"], reserved_row["user_input"]), ("高兴", "难过"))
            self.assertEqual(reserved_row["reviewer"], "nightly_patch_v2")
            self.assertEqual(reserved_row["sample_weight"], "6.0000")
            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            self.assertIn(("高兴", "难过"), train_pairs)
            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["required_proxy_antonym_calib_rows"], 0)
            self.assertEqual(stats["priority_antonym_calib_anchor_rows"], 1)
            self.assertEqual(stats["priority_antonym_calib_weight_rows"], 0)

    def test_build_nightly_semantic_sets_prioritizes_regression_antonym_pairs_within_v2_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "欣喜,郁闷,antonym_mid,50,4.0,nightly_patch_v2\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n"
                "白天,黑夜,antonym_mid,50,4.0,nightly_patch_v2\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n"
                "学校,校园,related_mid,60\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "1",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "6.0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            reserved_row = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("高兴", "难过")
            )
            self.assertEqual((reserved_row["answer"], reserved_row["user_input"]), ("高兴", "难过"))
            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            self.assertIn(("高兴", "难过"), train_pairs)

    def test_build_nightly_semantic_sets_prioritizes_emotion_family_proxy_for_holdout_antonym(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "快乐,痛苦,antonym_mid,50,4.0,nightly_patch_v1\n"
                "高兴,悲伤,antonym_mid,50,4.0,nightly_patch_v1\n"
                "开心,伤心,antonym_mid,50,4.0,nightly_patch_v1\n"
                "开心,难过,antonym_mid,50,4.0,nightly_patch_v1\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n"
                "学校,校园,related_mid,60\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "1",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "6.0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            reserved_row = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("高兴", "悲伤")
            )
            self.assertEqual((reserved_row["answer"], reserved_row["user_input"]), ("高兴", "悲伤"))
            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            self.assertIn(("高兴", "悲伤"), train_pairs)

    def test_build_nightly_semantic_sets_patch_rows_override_duplicate_supervised_gold_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            extra_gold_path = tmp_path / "extra_gold.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n"
                "学校,校园,related_mid,60\n",
                encoding="utf-8",
            )
            extra_gold_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,难过,antonym_mid,50,2.5,error_review_v1\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": str(extra_gold_path),
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "1",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "6.0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            anchor_rows = [
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("高兴", "难过")
            ]
            self.assertEqual(len(anchor_rows), 1)
            self.assertEqual(anchor_rows[0]["reviewer"], "nightly_patch_v2")
            self.assertEqual(anchor_rows[0]["sample_weight"], "6.0000")
            with train_out.open("r", encoding="utf-8") as file:
                train_pairs = {(row["answer"], row["user_input"]) for row in csv.DictReader(file)}
            self.assertIn(("高兴", "难过"), train_pairs)

            with eval_out.open("r", encoding="utf-8") as file:
                eval_rows = list(csv.DictReader(file))
            self.assertFalse(
                any((row["answer"], row["user_input"]) == ("高兴", "难过") for row in eval_rows)
            )

    def test_build_nightly_semantic_sets_patch_rows_override_reverse_direction_supervised_gold_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            extra_gold_path = tmp_path / "extra_gold.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"北京","category":"城市","hints":["首都"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "上海,北京,same_category_but_far,28,3.0,nightly_patch_v1\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "学校,校园,related_mid,60\n",
                encoding="utf-8",
            )
            extra_gold_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "北京,上海,same_category_but_far,28,1.0,semantic_error_review_template_v1\n"
                "天津,重庆,same_category_but_far,28,1.0,semantic_error_review_template_v1\n"
                "广州,深圳,same_category_but_far,28,1.0,semantic_error_review_template_v1\n"
                "南京,杭州,same_category_but_far,28,1.0,semantic_error_review_template_v1\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": str(extra_gold_path),
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "0",
                    "SEM_SEED": "20260304",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            for path in (train_out, calib_out, eval_out):
                with path.open("r", encoding="utf-8") as file:
                    rows = list(csv.DictReader(file))
                self.assertFalse(
                    any({row["answer"], row["user_input"]} == {"北京", "上海"} and row["reviewer"] == "semantic_error_review_template_v1" for row in rows)
                )

            with train_out.open("r", encoding="utf-8") as file:
                train_rows = list(csv.DictReader(file))
            self.assertTrue(
                any((row["answer"], row["user_input"]) == ("上海", "北京") and row["reviewer"] == "nightly_patch_v1" for row in train_rows)
            )

            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["train_eval_symmetric_overlap"], 0)
            self.assertEqual(stats["eval_calib_symmetric_overlap"], 0)
            self.assertEqual(stats["unexpected_train_calib_exact_overlap"], 0)

    def test_build_nightly_semantic_sets_uses_priority_calibration_weight_for_target_antonym_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            puzzles_path = tmp_path / "puzzles.json"
            manual_path = tmp_path / "manual.json"
            base_train_path = tmp_path / "base_train.csv"
            train_patch_path = tmp_path / "train_patch.csv"
            scored_path = tmp_path / "scored.csv"
            train_out = tmp_path / "train.csv"
            pool_out = tmp_path / "pool.csv"
            calib_out = tmp_path / "calib.csv"
            eval_out = tmp_path / "eval.csv"
            unsup_out = tmp_path / "unsup.jsonl"
            stats_out = tmp_path / "build_stats.json"

            puzzles_path.write_text(
                '[{"answer":"猫咪","category":"动物","hints":["会抓老鼠"]}]\n',
                encoding="utf-8",
            )
            manual_path.write_text("[]\n", encoding="utf-8")
            base_train_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "猫咪,刘备,hard_negative_low,10,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,悲伤,antonym_mid,50,4.0,nightly_patch_v1\n"
                "快乐,痛苦,antonym_mid,50,4.0,nightly_patch_v1\n",
                encoding="utf-8",
            )
            scored_path.write_text(
                "answer,user_input,relation_tag,score_0_100\n"
                "医生,大夫,near_synonym_high,80\n"
                "火,水,same_category_but_far,18\n"
                "学校,校园,related_mid,60\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "SEM_PUZZLES_JSON": str(puzzles_path),
                    "SEM_MANUAL_OVERRIDES": str(manual_path),
                    "SEM_BASE_TRAIN_CSV": str(base_train_path),
                    "SEM_TRAIN_PATCH_CSVS": str(train_patch_path),
                    "SEM_SCORED_CSV": str(scored_path),
                    "SEM_EXTRA_GOLD_CSVS": "",
                    "SEM_HOLDOUT_CSVS": "",
                    "SEM_OUTPUT_TRAIN_CSV": str(train_out),
                    "SEM_GOLD_POOL_CSV": str(pool_out),
                    "SEM_GOLD_CALIB_CSV": str(calib_out),
                    "SEM_GOLD_EVAL_CSV": str(eval_out),
                    "SEM_UNSUP_PAIRS_JSONL": str(unsup_out),
                    "SEM_BUILD_STATS_JSON": str(stats_out),
                    "SEM_GOLD_TARGET_TOTAL": "20",
                    "SEM_ANTONYM_CALIB_ANCHOR_TARGET": "2",
                    "SEM_ANTONYM_CALIB_ANCHOR_WEIGHT": "6.0",
                    "SEM_PRIORITY_ANTONYM_CALIB_ANCHOR_WEIGHT": "9.0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(BUILD_NIGHTLY_SETS_SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            with calib_out.open("r", encoding="utf-8") as file:
                calib_rows = list(csv.DictReader(file))
            boosted = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("高兴", "悲伤")
            )
            baseline = next(
                row for row in calib_rows if (row["answer"], row["user_input"]) == ("快乐", "痛苦")
            )
            self.assertEqual(boosted["sample_weight"], "9.0000")
            self.assertEqual(baseline["sample_weight"], "6.0000")
            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["priority_antonym_calib_anchor_rows"], 1)
            self.assertEqual(stats["priority_antonym_calib_weight_rows"], 1)
            self.assertEqual(stats["antonym_calib_anchor_weight"], 6.0)
            self.assertEqual(stats["priority_antonym_calib_anchor_weight"], 9.0)

    def test_supervised_trainer_boosts_real_failure_hard_negative_tags_without_antonyms(self):
        source = (REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py").read_text(encoding="utf-8")
        nightly_source = (REPO_ROOT / "scripts" / "nightly_train_v26.sh").read_text(encoding="utf-8")

        for tag in (
            "collocation_not_equivalent",
            "same_category_but_far",
        ):
            self.assertIn(f'"{tag}"', source)
        hard_neg_block = source.split("HARD_NEG_TAGS = {", 1)[1].split("}", 1)[0]
        self.assertNotIn('"antonym_low"', hard_neg_block)
        self.assertNotIn('"antonym_or_conflict"', hard_neg_block)
        self.assertIn("PIN_HIGH_VALUE_ROWS", source)
        self.assertIn("PIN_WEIGHT_THRESHOLD", source)
        self.assertIn("pinned_high_value_rows", source)
        self.assertIn("TAG_REPEAT_BOOSTS", source)
        self.assertIn('"antonym_mid": 2.0', source)
        self.assertIn("protected_positive_rows", source)
        self.assertIn("antonym_mid_examples_after_repeat", source)
        self.assertIn('SEM_MIN_TAG_ROWS", "antonym_mid:45"', source)
        self.assertIn("SEM_MIN_TAG_BUCKET_ROWS", source)
        self.assertIn('SEM_COSENT_EXCLUDE_TAGS", "antonym_mid"', source)
        self.assertIn('SEM_COSINE_EXCLUDE_TAGS", "").strip()', source)
        self.assertIn('SEM_BUCKET_ONLY_TAGS", "same_category_but_far"', source)
        self.assertIn(
            'NIGHTLY_SUP_BUCKET_ONLY_TAGS:-same_category_but_far',
            nightly_source,
        )
        self.assertIn("def validate_objective_scope", source)
        self.assertIn("MIDPOINT_TAGS & COSINE_EXCLUDE_TAGS", source)
        self.assertIn("antonym_mid must remain excluded from CoSENT", nightly_source)
        self.assertIn("antonym_mid must remain in cosine regression", nightly_source)
        self.assertIn('SEM_COSINE_EXCLUDE_TAGS=\\"${SUP_COSINE_EXCLUDE_TAGS}\\"', nightly_source)
        self.assertIn('SEM_BUCKET_ONLY_TAGS=\\"${SUP_BUCKET_ONLY_TAGS}\\"', nightly_source)
        self.assertIn("cosent_excluded_examples_after_repeat", source)
        self.assertIn("cosine_excluded_examples_after_repeat", source)
        self.assertIn("SEM_TRAIN_STATS_JSON", source)
        self.assertIn("SEM_MIN_ANGLE_REPEAT_FOR_HIGH_VALUE", source)
        self.assertIn("SEM_MIN_ANGLE_REPEAT_TAG_BUCKETS", source)
        self.assertIn("DEFAULT_MIN_ANGLE_REPEAT_TAG_BUCKETS", source)
        for bucket_spec in (
            "same_category_but_far@20-39:5",
            "same_category_mid@20-39:5",
            "same_category_mid@40-59:5",
            "same_category_mid@60-79:5",
        ):
            self.assertIn(bucket_spec, source)
        self.assertIn("SEM_REQUIRED_ANTONYM_MIN_ANGLE_REPEAT", source)
        self.assertIn("SEM_PRIORITY_ANTONYM_MIN_ANGLE_REPEAT", source)
        self.assertIn("SEM_PROXY_ANTONYM_MIN_ANGLE_REPEAT", source)
        self.assertIn("required_antonym_examples_after_repeat", source)
        self.assertIn("priority_antonym_examples_after_repeat", source)
        self.assertIn("proxy_antonym_examples_after_repeat", source)
        self.assertIn("full_angle_coverage_rows", source)
        self.assertIn("SEM_LOSS_MODE", source)
        self.assertIn("CosineSimilarityLoss", source)
        self.assertIn("OnlineContrastiveLoss", source)
        self.assertIn("mixed_contrastive", source)
        self.assertIn("SEM_CONTRASTIVE_MARGIN", source)
        self.assertIn("SEM_CONTRASTIVE_SCOPE", source)
        self.assertIn("CONTRASTIVE_POSITIVE_TAGS", source)
        self.assertIn("contrastive_label_counts", source)
        self.assertIn("BucketBandLoss", source)
        self.assertIn("BaseGuardedCosineLoss", source)
        self.assertIn("SEM_BUCKET_BAND_WEIGHT", source)
        self.assertIn('SEM_BUCKET_BAND_WEIGHT", "1.0"', source)
        self.assertIn("SEM_BUCKET_BAND_CENTER_WEIGHT", source)
        self.assertIn("SEM_BUCKET_BAND_HARD_NEG_REPEAT", source)
        self.assertIn('SEM_BUCKET_BAND_HARD_NEG_REPEAT", "2"', source)
        self.assertIn("SEM_BUCKET_BAND_BASE_GUARD", source)
        self.assertIn("attach_base_bucket_scores", source)
        self.assertIn("bucket_band_base_guard_protected_examples", source)
        self.assertIn("cosine_base_guard_protected_examples", source)
        self.assertIn("BaseGuardedCoSENTLoss", source)
        self.assertIn('BASE_GUARD_SCORE_MODE = "angle_view_v1"', source)
        self.assertIn("cosent_base_guard_protected_examples", source)
        self.assertIn("midpoint_base_guard_protected_examples", source)
        self.assertIn("cosine_base_guard_enabled", nightly_source)
        self.assertIn("sup_cosine_base_guard", nightly_source)
        self.assertIn("sup_cosent_base_guard", nightly_source)
        self.assertIn("sup_midpoint_base_guard", nightly_source)
        self.assertIn("CANONICAL_SUP_MIN_ANGLE_REPEAT_TAG_BUCKETS", nightly_source)
        self.assertIn("bucket_band_center_weight", source)
        self.assertIn("bucket_band_hard_negative_repeat", source)
        self.assertIn("bucket_band_hard_negative_examples_after_repeat", source)
        self.assertIn(
            'base_raw_mae_val="$(echo "$python_gate_output" | awk -F= \'/^base_raw_mae=/{print $2}\')"',
            nightly_source,
        )
        self.assertIn(
            'cand_raw_acc_val="$(echo "$python_gate_output" | awk -F= \'/^cand_raw_bucket_acc=/{print $2}\')"',
            nightly_source,
        )
        self.assertIn(
            'ROUND_RESULTS+=("${round}|${candidate_stage}|${candidate_model}|${round_output_calib}|${cand_mae_val}|${cand_acc_val}|${cand_raw_mae_val}|${cand_raw_acc_val}|${accepted}")',
            nightly_source,
        )
        self.assertIn('"abstract_confusion,nonsense_low"', source)
        self.assertIn("bucket_band_examples_after_repeat", source)
        self.assertIn('"abstract_confusion"', source)
        self.assertIn("same_category_weak", source)
        self.assertIn("SEM_MIDPOINT_TAGS", source)
        self.assertIn("midpoint_examples_after_repeat", source)
        self.assertIn('SAMPLE_SEED = int(os.getenv("SEM_SAMPLE_SEED", str(SEED)))', source)
        self.assertIn("seed_training(SEED)", source)
        self.assertIn("MidpointBandLoss", source)
        self.assertIn('SEM_MIDPOINT_BAND_LOW", "0.45"', source)
        self.assertIn('SEM_MIDPOINT_BAND_HIGH", "0.55"', source)
        self.assertIn('SEM_MIDPOINT_BAND_WEIGHT", "4.0"', source)
        self.assertIn('SEM_MIDPOINT_CENTER_WEIGHT", "1.0"', source)
        self.assertIn('SEM_MIDPOINT_OBJECTIVE_REPEATS", "2"', source)
        self.assertIn("range(MIDPOINT_OBJECTIVE_REPEATS)", source)
        self.assertIn("def round_robin_batch_budget", source)
        self.assertIn("def round_robin_schedule_stats", source)
        self.assertIn("pad_examples_to_batch_budget", source)
        self.assertIn("def round_robin_steps_per_epoch", source)
        self.assertIn("schedule_stats = round_robin_schedule_stats(", source)
        self.assertIn("round_robin_target_batches_per_objective", source)
        self.assertIn("round_robin_padded_examples", source)
        self.assertIn("round_robin_noop_padded_examples", source)
        self.assertIn('pad_label = float("nan") if isinstance(loss_fn, GUARDED_LOSS_TYPES) else None', source)
        self.assertIn("seed=SEED", source)
        eval_source = (REPO_ROOT / "scripts" / "eval_v26_gold.py").read_text(encoding="utf-8")
        self.assertIn("SEM_CALIB_MIDPOINT_AUGMENT_RADIUS", eval_source)
        self.assertIn("'3.5'", eval_source)
        self.assertIn("apply_global_calibration(raw, calib)", eval_source)
        self.assertNotIn("apply_relation_calibration", eval_source)
        self.assertNotIn('calib["relation_calibrations"]', eval_source)
        self.assertIn("CALIBRATION_EVAL_MODE = 'global_curve_v1'", eval_source)
        self.assertIn("global_midpoint_pred_aug", eval_source)
        self.assertNotIn("calib = constrain_calibration_interval(", eval_source)
        regression_source = (REPO_ROOT / "scripts" / "run_regression_pairs_v23.py").read_text(encoding="utf-8")
        self.assertIn("apply_global_calibration(raw_sem, calib)", regression_source)
        self.assertNotIn("apply_relation_calibration", regression_source)
        self.assertIn('echo "| calibration_eval_mode | global_curve_v1 |"', nightly_source)
        self.assertIn('echo "| base_guard_score_mode | angle_view_v1 |"', nightly_source)
        self.assertIn("SEM_CALIB_MIDPOINT_AUGMENT_STEPS", nightly_source)
        self.assertIn("SEM_CALIB_MIDPOINT_AUGMENT_WEIGHT", nightly_source)

    def test_supervised_trainer_preserves_legacy_mps_path_and_explicit_cpu_path(self):
        source = (REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py").read_text(encoding="utf-8")
        main_source = source.split("def main()", 1)[1]

        self.assertIn("def materialize_padded_objectives(", source)
        self.assertIn("def fit_with_explicit_trainer(", source)
        self.assertIn("def fit_with_sentence_transformer_fit(", source)
        self.assertIn("def fit_with_legacy_model_fit(", source)
        self.assertIn("seed=SEED", source)
        self.assertIn(
            'trainer_backend = "SentenceTransformerTrainer" if device == "cpu" else "SentenceTransformer.fit"',
            source,
        )
        self.assertIn("LEGACY_MODEL_FIT_SEED", source)
        self.assertIn('stats["trainer_backend"] = trainer_backend', source)
        self.assertIn('stats["trainer_seed"] = trainer_seed', source)
        self.assertIn('stats["round_robin_steps_per_epoch"] = steps_per_epoch', source)
        self.assertIn('stats["fit_steps_per_epoch"] = fit_steps_per_epoch', source)
        self.assertIn('stats["fit_warmup_steps"] = fit_warmup_steps', source)
        self.assertIn("write_train_stats(stats)", source)
        self.assertIn("multi_dataset_batch_sampler=MultiDatasetBatchSamplers.ROUND_ROBIN", source)
        self.assertIn("fit_with_explicit_trainer(", main_source)
        self.assertIn("fit_with_sentence_transformer_fit(", main_source)
        self.assertIn("device=device", main_source)
        self.assertIn("target_batches = round_robin_batch_budget(", source)
        self.assertIn("steps_per_epoch = round_robin_steps_per_epoch(", source)
        self.assertIn("fit_steps_per_epoch = (", main_source)
        self.assertIn("fit_warmup_steps = warmup_steps", main_source)
        self.assertNotIn("model.fit(", main_source)

    def test_legacy_model_fit_receives_padded_objectives_without_training(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_legacy_model_fit",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class CaptureModel:
            def __init__(self):
                self.fit_kwargs = None

            def fit(self, **kwargs):
                self.fit_kwargs = kwargs

        real_examples = [
            trainer.InputExample(texts=["a", "b"], label=0.2),
            trainer.InputExample(texts=["c", "d"], label=0.3),
            trainer.InputExample(texts=["e", "f"], label=0.4),
            trainer.InputExample(texts=["g", "h"], label=0.5),
            trainer.InputExample(texts=["i", "j"], label=0.6),
            trainer.InputExample(texts=["k", "l"], label=0.7),
        ]
        bucket_examples = [
            trainer.InputExample(texts=["m", "n"], label=0.2),
            trainer.InputExample(texts=["o", "p"], label=0.3),
        ]
        objectives = [
            (
                trainer.DataLoader(real_examples, batch_size=2, shuffle=False),
                object(),
            ),
            (
                trainer.DataLoader(bucket_examples, batch_size=2, shuffle=False),
                trainer.BucketBandLoss(None, band_weight=1.0),
            ),
        ]
        model = CaptureModel()
        trainer.fit_with_legacy_model_fit(
            model=model,
            train_objectives=objectives,
            epochs=1,
            batch_size=2,
            warmup_steps=1,
            learning_rate=2e-6,
            protected_min_batches=3,
        )

        self.assertIsNotNone(model.fit_kwargs)
        self.assertEqual(model.fit_kwargs["steps_per_epoch"], 6)
        padded_loaders = model.fit_kwargs["train_objectives"]
        self.assertEqual([len(loader) for loader, _ in padded_loaders], [3, 3])
        self.assertEqual([loader.sampler.__class__.__name__ for loader, _ in padded_loaders], ["SequentialSampler", "SequentialSampler"])
        padded_bucket_examples = padded_loaders[1][0].dataset
        self.assertEqual(len(padded_bucket_examples), 6)
        self.assertTrue(all(label != label for label in [example.label for example in padded_bucket_examples[2:]]))

    def test_supervised_trainer_materialization_is_stable_for_fixed_sample_seed(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_materialization_seed",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        def make_objectives():
            examples = [
                trainer.InputExample(texts=[f"a{idx}", f"b{idx}"], label=idx / 10)
                for idx in range(6)
            ]
            return [
                (trainer.DataLoader(list(examples), batch_size=2, shuffle=True), object()),
                (trainer.DataLoader(list(examples), batch_size=2, shuffle=True), object()),
            ]

        first = trainer.materialize_padded_objectives(
            make_objectives(),
            batch_size=2,
            protected_min_batches=2,
            sampling_seed=123,
        )
        second = trainer.materialize_padded_objectives(
            make_objectives(),
            batch_size=2,
            protected_min_batches=2,
            sampling_seed=123,
        )
        first_labels = [[example.label for example in examples] for examples, _ in first]
        second_labels = [[example.label for example in examples] for examples, _ in second]
        self.assertEqual(first_labels, second_labels)

    def test_supervised_trainer_normalizes_legacy_midpoint_band_on_direct_invocation(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_legacy_midpoint_band",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        previous_low = os.environ.get("SEM_MIDPOINT_BAND_LOW")
        previous_high = os.environ.get("SEM_MIDPOINT_BAND_HIGH")
        os.environ["SEM_MIDPOINT_BAND_LOW"] = "0.47"
        os.environ["SEM_MIDPOINT_BAND_HIGH"] = "0.53"
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)
        finally:
            if previous_low is None:
                os.environ.pop("SEM_MIDPOINT_BAND_LOW", None)
            else:
                os.environ["SEM_MIDPOINT_BAND_LOW"] = previous_low
            if previous_high is None:
                os.environ.pop("SEM_MIDPOINT_BAND_HIGH", None)
            else:
                os.environ["SEM_MIDPOINT_BAND_HIGH"] = previous_high

        self.assertEqual(trainer.MIDPOINT_BAND_LOW, 0.45)
        self.assertEqual(trainer.MIDPOINT_BAND_HIGH, 0.55)

    def test_eval_group_prioritizes_explicit_relation_tags_over_score_fallback(self):
        spec = importlib.util.spec_from_file_location(
            "eval_v26_gold_group_priority",
            REPO_ROOT / "scripts" / "eval_v26_gold.py",
        )
        self.assertIsNotNone(spec)
        evaluator = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            spec.loader.exec_module(evaluator)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        def group(tag, score):
            return evaluator.eval_group({"relation_tag": tag, "_score": score})

        self.assertEqual(group("hint_like_high", 90), "hint_like")
        self.assertEqual(group("hint_like_high", 20), "hard_negative")
        self.assertEqual(group("same_category_mid", 90), "same_category")
        self.assertEqual(group("same_category_mid", 20), "hard_negative")
        self.assertEqual(group("alias_synonym_high", 90), "synonym_alias")
        self.assertEqual(group("", 90), "synonym_alias")
        self.assertEqual(group("hard_negative_low", 90), "hard_negative")
        self.assertEqual(group("antonym_mid", 90), "antonym")

    def test_eval_calibration_diagnostics_use_global_augmentation_counts(self):
        source = (REPO_ROOT / "scripts" / "eval_v26_gold.py").read_text(encoding="utf-8")

        self.assertIn(
            "midpoint_calibration_augmented_rows = len(global_midpoint_pred_aug) - len(calib_pred)",
            source,
        )
        self.assertIn("augmented_rows={midpoint_calibration_augmented_rows}", source)
        self.assertIn(
            "support_positive_calibration_augmented_rows = len(support_pred_aug) - len(calib_pred)",
            source,
        )
        self.assertIn("augmented_rows={support_positive_calibration_augmented_rows}", source)
        self.assertNotIn("len(midpoint_pred_aug)", source)

    def test_triage_gate_fallback_requires_report_matched_run_log(self):
        spec = importlib.util.spec_from_file_location(
            "nightly_next_morning_triage_v26_matching_gate_log",
            NEXT_MORNING_TRIAGE_SCRIPT,
        )
        self.assertIsNotNone(spec)
        triage = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            spec.loader.exec_module(triage)
        finally:
            sys.path.remove(str(REPO_ROOT / "scripts"))

        stamp = "20260929_230003"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "reports" / f"nightly_promotion_{stamp}.md"
            run_log = root / "tmp" / f"nightly_train_v26_{stamp}.log"
            report.parent.mkdir(parents=True)
            run_log.parent.mkdir(parents=True)
            report.write_text("# report\n", encoding="utf-8")
            run_log.write_text("mae_ok=True\naccepted=False\n", encoding="utf-8")
            health = {
                "latest_run_log": str(run_log),
                "latest_run_log_stamp": stamp,
            }

            matched = triage.matching_run_log_text(health, report)
            self.assertEqual(matched, "mae_ok=True\naccepted=False\n")
            parsed = triage.analyze_nightly_report_v26.parse_gate_status(matched)
            self.assertEqual(parsed["failed_gates"], [])
            self.assertTrue(parsed["gate_status"]["mae_ok"])

            health["latest_run_log_stamp"] = "20260928_230003"
            self.assertEqual(triage.matching_run_log_text(health, report), "")

    def test_nightly_script_normalizes_stale_launchd_bucket_quotas(self):
        source = (REPO_ROOT / "scripts" / "nightly_train_v26.sh").read_text(encoding="utf-8")

        self.assertIn('CANONICAL_SUP_MIDPOINT_BAND_LOW="0.45"', source)
        self.assertIn('CANONICAL_SUP_MIDPOINT_BAND_HIGH="0.55"', source)
        self.assertIn('LEGACY_SUP_MIDPOINT_BAND_LOW="0.47"', source)
        self.assertIn('LEGACY_SUP_MIDPOINT_BAND_HIGH="0.53"', source)
        self.assertIn(
            'if [[ "$SUP_MIDPOINT_BAND_LOW" == "$LEGACY_SUP_MIDPOINT_BAND_LOW" || \\',
            source,
        )
        self.assertIn('SUP_MIDPOINT_BAND_LOW="$CANONICAL_SUP_MIDPOINT_BAND_LOW"', source)
        self.assertIn('SUP_MIDPOINT_BAND_HIGH="$CANONICAL_SUP_MIDPOINT_BAND_HIGH"', source)
        self.assertIn(
            'CANONICAL_SUP_MIN_TAG_BUCKET_ROWS="same_category_mid@40-59:20,same_category_mid@60-79:12"',
            source,
        )
        self.assertIn(
            'LEGACY_SUP_MIN_TAG_BUCKET_ROWS="same_category_mid@40-59:20,same_category_mid@60-79:12,hint_like_high@60-79:18,hint_like_high@80-100:18"',
            source,
        )
        self.assertIn(
            'if [[ "$SUP_MIN_TAG_BUCKET_ROWS" == "$LEGACY_SUP_MIN_TAG_BUCKET_ROWS" ]]; then',
            source,
        )
        self.assertIn('SUP_MIN_TAG_BUCKET_ROWS="$CANONICAL_SUP_MIN_TAG_BUCKET_ROWS"', source)

        checker_spec = importlib.util.spec_from_file_location(
            "check_nightly_launchd_v26_bucket_quota",
            CHECK_NIGHTLY_LAUNCHD_SCRIPT,
        )
        self.assertIsNotNone(checker_spec)
        checker = importlib.util.module_from_spec(checker_spec)
        self.assertIsNotNone(checker_spec.loader)
        checker_spec.loader.exec_module(checker)
        self.assertEqual(
            checker.effective_sup_min_tag_bucket_rows(
                checker.LEGACY_SUP_MIN_TAG_BUCKET_ROWS
            ),
            checker.CANONICAL_SUP_MIN_TAG_BUCKET_ROWS,
        )
        self.assertEqual(
            checker.effective_sup_min_tag_bucket_rows(
                checker.CANONICAL_SUP_MIN_TAG_BUCKET_ROWS
            ),
            checker.CANONICAL_SUP_MIN_TAG_BUCKET_ROWS,
        )
        self.assertEqual(
            checker.effective_sup_bucket_band_hard_neg_repeat("1"),
            "2",
        )
        self.assertEqual(
            checker.effective_sup_bucket_band_hard_neg_repeat(""),
            "2",
        )
        self.assertEqual(
            checker.effective_sup_bucket_band_hard_neg_repeat("2"),
            "2",
        )
        self.assertEqual(
            checker.effective_sup_bucket_only_tags(""),
            "same_category_but_far",
        )
        self.assertEqual(
            checker.effective_sup_bucket_only_tags("same_category_but_far,same_category_mid"),
            "same_category_but_far,same_category_mid",
        )
        self.assertEqual(
            checker.effective_sup_midpoint_band("0.45", "0.55"),
            ("0.45", "0.55"),
        )
        self.assertEqual(
            checker.effective_sup_midpoint_band("0.45", "0.53"),
            ("0.45", "0.55"),
        )
        self.assertEqual(
            checker.effective_sup_midpoint_band("0.47", "0.53"),
            ("0.45", "0.55"),
        )

    def test_supervised_trainer_round_robin_steps_include_repeated_objectives(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_round_robin_steps",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeLoader:
            def __init__(self, batches):
                self.batches = batches

            def __len__(self):
                return self.batches

        objectives = [
            (FakeLoader(61), None),
            (FakeLoader(83), None),
            (FakeLoader(45), None),
            (FakeLoader(45), None),
            (FakeLoader(46), None),
        ]
        self.assertEqual(trainer.round_robin_steps_per_epoch(objectives), 225)
        self.assertEqual(trainer.round_robin_steps_per_epoch(objectives[:4]), 180)

        with self.assertRaisesRegex(ValueError, "at least one"):
            trainer.round_robin_steps_per_epoch([])
        with self.assertRaisesRegex(ValueError, "at least one batch"):
            trainer.round_robin_steps_per_epoch([(FakeLoader(0), None)])

        self.assertEqual(trainer.round_robin_batch_budget(objectives, protected_min_batches=46), 46)
        self.assertEqual(trainer.round_robin_steps_per_epoch(objectives, protected_min_batches=46), 230)

    def test_supervised_trainer_protects_midpoint_batches_from_round_robin_truncation(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_midpoint_schedule",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeLoader:
            def __init__(self, batches):
                self.batches = batches

            def __len__(self):
                return self.batches

        objectives = [
            (FakeLoader(59), None),
            (FakeLoader(82), None),
            (FakeLoader(47), object()),
            (FakeLoader(47), object()),
            (FakeLoader(34), trainer.BucketBandLoss(None, band_weight=1.0)),
        ]
        self.assertEqual(trainer.round_robin_batch_budget(objectives, protected_min_batches=47), 47)
        self.assertEqual(trainer.round_robin_steps_per_epoch(objectives, protected_min_batches=47), 235)
        schedule_stats = trainer.round_robin_schedule_stats(
            objectives,
            batch_size=8,
            protected_min_batches=47,
        )
        self.assertEqual(schedule_stats["padded_examples"], 104)
        self.assertEqual(schedule_stats["noop_padded_examples"], 104)

    def test_supervised_trainer_pads_short_objective_to_protected_batch_budget(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_padding",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        texts, labels = trainer.pad_examples_to_batch_budget(
            [("a", "b"), ("c", "d")],
            [0.1, 0.2],
            5,
        )
        self.assertEqual(len(texts), 5)
        self.assertEqual(len(labels), 5)
        self.assertEqual(texts[:2], [("a", "b"), ("c", "d")])
        self.assertEqual(labels, [0.1, 0.2, 0.1, 0.2, 0.1])

        _, noop_labels = trainer.pad_examples_to_batch_budget(
            [("a", "b"), ("c", "d")],
            [0.1, 0.2],
            5,
            pad_label=float("nan"),
        )
        self.assertEqual(noop_labels[:2], [0.1, 0.2])
        self.assertTrue(all(label != label for label in noop_labels[2:]))

    def test_supervised_trainer_rejects_midpoint_cosine_exclusion(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_scope_guard",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        previous_midpoint_tags = trainer.MIDPOINT_TAGS
        previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
        previous_cosent_excluded = trainer.COSENT_EXCLUDE_TAGS
        try:
            trainer.MIDPOINT_TAGS = {"antonym_mid"}
            trainer.COSENT_EXCLUDE_TAGS = set()
            trainer.COSINE_EXCLUDE_TAGS = set()
            with self.assertRaisesRegex(SystemExit, "excluded from the CoSENT objective"):
                trainer.validate_objective_scope()

            trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
            trainer.COSINE_EXCLUDE_TAGS = {"antonym_mid"}
            with self.assertRaisesRegex(SystemExit, "remain in the cosine objective"):
                trainer.validate_objective_scope()
        finally:
            trainer.MIDPOINT_TAGS = previous_midpoint_tags
            trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
            trainer.COSENT_EXCLUDE_TAGS = previous_cosent_excluded

    def test_supervised_trainer_bucket_band_target_excludes_antonym_mid(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n"
                "飞机,轮船,same_category_but_far,22,1.0,review\n"
                "八面玲珑,同舟共济,same_category_mid,20,1.0,review\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive_bucket_band",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_angle_mode = trainer.ANGLE_MODE
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_bucket_tags = trainer.BUCKET_BAND_TAGS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.ANGLE_MODE = "none"
                trainer.COSINE_EXCLUDE_TAGS = set()
                trainer.BUCKET_BAND_TAGS = {
                    "antonym_mid",
                    "same_category_but_far",
                    "same_category_mid",
                }
                examples, _, _, _, _, bucket_band_examples, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.ANGLE_MODE = previous_angle_mode
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.BUCKET_BAND_TAGS = previous_bucket_tags

            self.assertEqual(stats["bucket_band_rows"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_rows"], 1)
            self.assertEqual(stats["bucket_band_hard_negative_examples_before_repeat"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_examples_after_repeat"], 4)
            self.assertEqual(stats["bucket_band_examples_after_repeat"], 6)
            self.assertEqual(len(bucket_band_examples), 6)
            self.assertFalse(any(abs(example.label - 0.5) < 1e-9 for example in bucket_band_examples))
            self.assertTrue(any(abs(example.label - 0.22) < 1e-9 for example in bucket_band_examples))
            self.assertTrue(any(abs(example.label - 0.2) < 1e-9 for example in bucket_band_examples))

    def test_bucket_band_loss_preserves_in_bucket_scores_and_repairs_violations(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_bucket_loss",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeModel:
            def __call__(self, features):
                return {"sentence_embedding": features["embedding"]}

        import torch

        left = torch.tensor([[1.0, 0.0]], dtype=torch.float32)
        score = 0.55
        right = torch.tensor([[score, (1.0 - score * score) ** 0.5]], dtype=torch.float32)
        sentence_features = [{"embedding": left}, {"embedding": right}]
        labels = torch.tensor([0.50], dtype=torch.float32)

        band_only = trainer.BucketBandLoss(FakeModel(), band_weight=0.5, center_weight=0.0)
        with_center = trainer.BucketBandLoss(FakeModel(), band_weight=0.5, center_weight=1.0)
        self.assertAlmostEqual(float(band_only(sentence_features, labels)), 0.0, places=6)
        self.assertAlmostEqual(float(with_center(sentence_features, labels)), 0.0, places=6)

        outside_score = 0.75
        outside_right = torch.tensor(
            [[outside_score, (1.0 - outside_score * outside_score) ** 0.5]],
            dtype=torch.float32,
        )
        outside_features = [{"embedding": left}, {"embedding": outside_right}]
        band_value = float(band_only(outside_features, labels))
        center_value = float(with_center(outside_features, labels))
        self.assertGreater(band_value, 0.0)
        self.assertGreater(center_value, band_value)
        noop_labels = torch.tensor([float("nan")], dtype=torch.float32)
        self.assertEqual(float(with_center(sentence_features, noop_labels)), 0.0)

    def test_bucket_band_loss_uses_base_guard_for_correct_and_wrong_base_buckets(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_base_bucket_guard_loss",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeModel:
            def __call__(self, features):
                return {"sentence_embedding": features["embedding"]}

        import torch

        left = torch.tensor([[1.0, 0.0]], dtype=torch.float32)
        guard = trainer.BucketBandLoss(
            FakeModel(),
            band_weight=0.0,
            center_weight=0.0,
            base_guard_weight=1.0,
            base_guard_margin=0.02,
        )

        def features(score):
            right = torch.tensor(
                [[score, (1.0 - score * score) ** 0.5]],
                dtype=torch.float32,
            )
            return [{"embedding": left}, {"embedding": right}]

        base_correct_labels = torch.tensor([[0.50, 0.55]], dtype=torch.float32)
        self.assertGreater(float(guard(features(0.59), base_correct_labels)), 0.0)
        self.assertAlmostEqual(float(guard(features(0.55), base_correct_labels)), 0.0, places=6)

        base_wrong_labels = torch.tensor([[0.50, 0.75]], dtype=torch.float32)
        self.assertAlmostEqual(float(guard(features(0.55), base_wrong_labels)), 0.0, places=6)
        self.assertAlmostEqual(float(guard(features(0.75), base_wrong_labels)), 0.0, places=6)
        self.assertGreater(float(guard(features(0.78), base_wrong_labels)), 0.0)

        base_wrong_low_labels = torch.tensor([[0.20, 0.10]], dtype=torch.float32)
        self.assertAlmostEqual(float(guard(features(0.15), base_wrong_low_labels)), 0.0, places=6)
        self.assertAlmostEqual(float(guard(features(0.10), base_wrong_low_labels)), 0.0, places=6)
        self.assertGreater(float(guard(features(0.05), base_wrong_low_labels)), 0.0)

    def test_base_bucket_guard_labels_survive_materialization_padding(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_base_bucket_guard_materialization",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        import torch

        class FakeModel:
            training = True

            def encode(self, texts, **kwargs):
                vectors = {
                    "a": [1.0, 0.0],
                    "b": [0.55, (1.0 - 0.55 * 0.55) ** 0.5],
                    "c": [1.0, 0.0],
                    "d": [0.10, (1.0 - 0.10 * 0.10) ** 0.5],
                }
                return torch.tensor([vectors[text] for text in texts], dtype=torch.float32)

            def train(self, mode=True):
                self.training = mode
                return self

        examples = [
            trainer.InputExample(texts=["a", "b"], label=0.50),
            trainer.InputExample(texts=["c", "d"], label=0.20),
        ]
        enriched, stats = trainer.attach_base_bucket_scores(FakeModel(), examples, batch_size=2)
        self.assertEqual(stats["bucket_band_base_guard_examples"], 2)
        self.assertEqual(stats["bucket_band_base_guard_protected_examples"], 1)
        self.assertEqual(len(enriched[0].label), 2)
        self.assertAlmostEqual(enriched[0].label[0], 0.50, places=6)
        self.assertAlmostEqual(enriched[0].label[1], 0.55, places=6)

        loader = trainer.DataLoader(enriched, batch_size=2, shuffle=False)
        materialized = trainer.materialize_padded_objectives(
            [(loader, trainer.BucketBandLoss(None, band_weight=1.0))],
            batch_size=2,
            protected_min_batches=2,
        )[0][0]
        self.assertEqual(len(materialized), 4)
        self.assertTrue(all(label[0] != label[0] and label[1] != label[1] for label in [
            example.label for example in materialized[2:]
        ]))
        self.assertIn(trainer.MidpointBandLoss, trainer.GUARDED_LOSS_TYPES)

        midpoint_loader = trainer.DataLoader(enriched, batch_size=2, shuffle=False)
        midpoint_materialized = trainer.materialize_padded_objectives(
            [(
                midpoint_loader,
                trainer.MidpointBandLoss(
                    None,
                    band_low=0.45,
                    band_high=0.55,
                    band_weight=1.0,
                    center_weight=1.0,
                ),
            )],
            batch_size=2,
            protected_min_batches=2,
        )[0][0]
        self.assertTrue(all(label[0] != label[0] and label[1] != label[1] for label in [
            example.label for example in midpoint_materialized[2:]
        ]))

    def test_base_bucket_guard_uses_the_matching_angle_view(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_multi_angle_base_guard",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        import torch

        class FakeModel:
            training = False

            def encode(self, texts, **kwargs):
                angle_scores = [0.25, 0.45, 0.55, 0.65, 0.75]
                vectors = {}
                for angle, score in zip(trainer.ANGLES, angle_scores):
                    vectors[f"{angle}a"] = [1.0, 0.0]
                    vectors[f"{angle}b"] = [score, (1.0 - score * score) ** 0.5]
                return torch.tensor([vectors[text] for text in texts], dtype=torch.float32)

            def train(self, mode=True):
                self.training = mode
                return self

        angle = trainer.ANGLES[0]
        middle_angle = trainer.ANGLES[2]
        examples = [
            trainer.InputExample(texts=[f"{angle}a", f"{angle}b"], label=0.50),
            trainer.InputExample(texts=[f"{middle_angle}a", f"{middle_angle}b"], label=0.50),
        ]
        enriched, stats = trainer.attach_base_bucket_scores(FakeModel(), examples, batch_size=5)

        self.assertEqual(stats["bucket_band_base_guard_multi_angle_examples"], 2)
        self.assertEqual(stats["bucket_band_base_guard_fallback_examples"], 0)
        self.assertEqual(stats["bucket_band_base_guard_protected_examples"], 1)
        self.assertAlmostEqual(enriched[0].label[1], 0.25, places=6)
        self.assertAlmostEqual(enriched[1].label[1], 0.55, places=6)

    def test_cosine_loss_uses_the_same_directional_base_guard(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_cosine_base_guard",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeModel:
            def __call__(self, features):
                return {"sentence_embedding": features["embedding"]}

        import torch

        left = torch.tensor([[1.0, 0.0]], dtype=torch.float32)

        def features(score):
            right = torch.tensor(
                [[score, (1.0 - score * score) ** 0.5]],
                dtype=torch.float32,
            )
            return [{"embedding": left}, {"embedding": right}]

        loss = trainer.BaseGuardedCosineLoss(
            FakeModel(),
            base_guard_weight=1.0,
            base_guard_margin=0.02,
        )
        unguarded = trainer.BaseGuardedCosineLoss(
            FakeModel(),
            base_guard_weight=0.0,
            base_guard_margin=0.02,
        )
        base_correct = torch.tensor([[0.50, 0.55]], dtype=torch.float32)
        self.assertGreater(
            float(loss(features(0.59), base_correct)),
            float(unguarded(features(0.59), base_correct)),
        )
        self.assertAlmostEqual(
            float(loss(features(0.55), base_correct)),
            float(unguarded(features(0.55), base_correct)),
            places=6,
        )

        base_wrong_high = torch.tensor([[0.50, 0.75]], dtype=torch.float32)
        self.assertAlmostEqual(
            float(loss(features(0.55), base_wrong_high)),
            float(unguarded(features(0.55), base_wrong_high)),
            places=6,
        )
        self.assertGreater(
            float(loss(features(0.78), base_wrong_high)),
            float(unguarded(features(0.78), base_wrong_high)),
        )

    def test_cosent_loss_uses_the_same_directional_base_guard(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_cosent_base_guard",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeModel:
            def __call__(self, features):
                return {"sentence_embedding": features["embedding"]}

        import torch

        left = torch.tensor([[1.0, 0.0], [1.0, 0.0]], dtype=torch.float32)

        def features(scores):
            right = torch.tensor(
                [[score, (1.0 - score * score) ** 0.5] for score in scores],
                dtype=torch.float32,
            )
            return [{"embedding": left}, {"embedding": right}]

        loss = trainer.BaseGuardedCoSENTLoss(
            FakeModel(),
            scale=20.0,
            base_guard_weight=1.0,
            base_guard_margin=0.02,
        )
        unguarded = trainer.BaseGuardedCoSENTLoss(
            FakeModel(),
            scale=20.0,
            base_guard_weight=0.0,
            base_guard_margin=0.02,
        )
        labels = torch.tensor([[0.20, 0.25], [0.80, 0.75]], dtype=torch.float32)
        self.assertGreater(
            float(loss(features([0.39, 0.79]), labels)),
            float(unguarded(features([0.39, 0.79]), labels)),
        )
        self.assertGreater(
            float(loss(features([0.30, 0.85]), labels)),
            float(unguarded(features([0.30, 0.85]), labels)),
        )

    def test_midpoint_loss_uses_the_same_directional_base_guard(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_midpoint_base_guard",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeModel:
            def __call__(self, features):
                return {"sentence_embedding": features["embedding"]}

        import torch

        left = torch.tensor([[1.0, 0.0]], dtype=torch.float32)

        def features(score):
            right = torch.tensor(
                [[score, (1.0 - score * score) ** 0.5]],
                dtype=torch.float32,
            )
            return [{"embedding": left}, {"embedding": right}]

        loss = trainer.MidpointBandLoss(
            FakeModel(),
            band_low=0.45,
            band_high=0.55,
            band_weight=0.0,
            center_weight=0.0,
            base_guard_weight=1.0,
            base_guard_margin=0.02,
        )
        unguarded = trainer.MidpointBandLoss(
            FakeModel(),
            band_low=0.45,
            band_high=0.55,
            band_weight=0.0,
            center_weight=0.0,
            base_guard_weight=0.0,
            base_guard_margin=0.02,
        )
        base_correct = torch.tensor([[0.50, 0.55]], dtype=torch.float32)
        self.assertGreater(
            float(loss(features(0.59), base_correct)),
            float(unguarded(features(0.59), base_correct)),
        )
        self.assertAlmostEqual(
            float(loss(features(0.55), base_correct)),
            float(unguarded(features(0.55), base_correct)),
            places=6,
        )

        base_wrong_high = torch.tensor([[0.50, 0.75]], dtype=torch.float32)
        self.assertAlmostEqual(
            float(loss(features(0.55), base_wrong_high)),
            float(unguarded(features(0.55), base_wrong_high)),
            places=6,
        )
        self.assertGreater(
            float(loss(features(0.78), base_wrong_high)),
            float(unguarded(features(0.78), base_wrong_high)),
        )

    def test_guarded_losses_ignore_nan_padding_labels(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive_guarded_loss_padding",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        class FakeModel:
            def __call__(self, features):
                return {"sentence_embedding": features["embedding"]}

        import torch

        left = torch.tensor([[1.0, 0.0], [1.0, 0.0]], dtype=torch.float32)

        def features(scores):
            right = torch.tensor(
                [[score, (1.0 - score * score) ** 0.5] for score in scores],
                dtype=torch.float32,
            )
            return [{"embedding": left[: len(scores)]}, {"embedding": right}]

        labels = torch.tensor(
            [[0.50, 0.55], [float("nan"), float("nan")]],
            dtype=torch.float32,
        )
        cosent = trainer.BaseGuardedCoSENTLoss(FakeModel(), base_guard_weight=1.0)
        midpoint = trainer.MidpointBandLoss(
            FakeModel(),
            band_low=0.45,
            band_high=0.55,
            band_weight=4.0,
            center_weight=1.0,
            base_guard_weight=1.0,
        )
        self.assertTrue(torch.isfinite(cosent(features([0.50, 0.40]), labels)))
        self.assertTrue(torch.isfinite(midpoint(features([0.50, 0.40]), labels)))

        all_padding = torch.tensor([[float("nan"), float("nan")]], dtype=torch.float32)
        self.assertAlmostEqual(float(cosent(features([0.50]), all_padding)), 0.0, places=6)
        self.assertAlmostEqual(float(midpoint(features([0.50]), all_padding)), 0.0, places=6)

    def test_supervised_trainer_bucket_band_covers_abstract_and_weak_category_negatives(self):
        with tempfile.TemporaryDirectory() as tmp:
            train_csv = Path(tmp) / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "星球,物理,abstract_confusion,15,1.0,review\n"
                "圣诞,万圣节,same_category_weak,30,1.0,review\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive_bucket_band_coverage",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_angle_mode = trainer.ANGLE_MODE
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_bucket_tags = trainer.BUCKET_BAND_TAGS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.ANGLE_MODE = "none"
                trainer.COSINE_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.BUCKET_BAND_TAGS = {
                    "abstract_confusion",
                    "same_category_weak",
                    "antonym_mid",
                }
                _, _, _, _, _, bucket_band_examples, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.ANGLE_MODE = previous_angle_mode
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.BUCKET_BAND_TAGS = previous_bucket_tags

            self.assertEqual(stats["bucket_band_rows"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_rows"], 1)
            self.assertEqual(stats["bucket_band_hard_negative_examples_before_repeat"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_examples_after_repeat"], 4)
            self.assertEqual(stats["bucket_band_examples_after_repeat"], 5)
            self.assertEqual(len(bucket_band_examples), 5)
            self.assertTrue(any(abs(example.label - 0.15) < 1e-9 for example in bucket_band_examples))
            self.assertTrue(any(abs(example.label - 0.3) < 1e-9 for example in bucket_band_examples))
            self.assertFalse(any(abs(example.label - 0.5) < 1e-9 for example in bucket_band_examples))

    def test_supervised_trainer_repeats_only_selected_hard_negative_bucket_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            train_csv = Path(tmp) / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "飞机,轮船,same_category_but_far,22,1.0,review\n"
                "圣诞,万圣节,same_category_weak,30,1.0,review\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive_bucket_band_repeat",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_angle_mode = trainer.ANGLE_MODE
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            previous_bucket_tags = trainer.BUCKET_BAND_TAGS
            previous_bucket_repeat = trainer.BUCKET_BAND_HARD_NEG_REPEAT
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.ANGLE_MODE = "none"
                trainer.COSINE_EXCLUDE_TAGS = set()
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                trainer.BUCKET_BAND_TAGS = {"same_category_but_far", "same_category_weak", "antonym_mid"}
                trainer.BUCKET_BAND_HARD_NEG_REPEAT = 2
                _, _, _, _, _, bucket_band_examples, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.ANGLE_MODE = previous_angle_mode
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.MIDPOINT_TAGS = previous_midpoint_tags
                trainer.BUCKET_BAND_TAGS = previous_bucket_tags
                trainer.BUCKET_BAND_HARD_NEG_REPEAT = previous_bucket_repeat

            labels = [round(example.label, 2) for example in bucket_band_examples]
            self.assertEqual(stats["bucket_band_rows"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_rows"], 1)
            self.assertEqual(stats["bucket_band_hard_negative_repeat"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_examples_before_repeat"], 2)
            self.assertEqual(stats["bucket_band_hard_negative_examples_after_repeat"], 4)
            self.assertEqual(stats["bucket_band_examples_after_repeat"], 5)
            self.assertEqual(labels.count(0.22), 4)
            self.assertEqual(labels.count(0.30), 1)
            self.assertNotIn(0.50, labels)

    def test_supervised_trainer_excludes_antonym_mid_from_cosent_and_adds_midpoint_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n"
                "医生,大夫,alias_synonym_high,90,1.0,review\n"
                "飞机,轮船,same_category_but_far,22,1.0,review\n"
                "风之谷,虹猫蓝兔,same_category_mid,50,1.0,review\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_excluded = trainer.COSENT_EXCLUDE_TAGS
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_bucket_only_tags = trainer.BUCKET_ONLY_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            previous_midpoint_boost = trainer.MIDPOINT_REPEAT_BOOST
            previous_priority_repeat = trainer.PRIORITY_ANTONYM_MIN_ANGLE_REPEAT
            previous_min_angle_repeat_tag_buckets = trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.COSINE_EXCLUDE_TAGS = set()
                trainer.BUCKET_ONLY_TAGS = {"same_category_but_far"}
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                trainer.MIDPOINT_REPEAT_BOOST = 2.0
                trainer.PRIORITY_ANTONYM_MIN_ANGLE_REPEAT = 0
                trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS = {}
                examples, cosent_examples, cosine_examples, contrastive_examples, midpoint_examples, bucket_band_examples, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.COSENT_EXCLUDE_TAGS = previous_excluded
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.BUCKET_ONLY_TAGS = previous_bucket_only_tags
                trainer.MIDPOINT_TAGS = previous_midpoint_tags
                trainer.MIDPOINT_REPEAT_BOOST = previous_midpoint_boost
                trainer.PRIORITY_ANTONYM_MIN_ANGLE_REPEAT = previous_priority_repeat
                trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS = previous_min_angle_repeat_tag_buckets

            self.assertEqual(stats["antonym_mid_rows"], 1)
            self.assertEqual(stats["antonym_mid_examples_after_repeat"], 3)
            self.assertEqual(stats["cosent_excluded_rows"], 1)
            self.assertEqual(stats["cosent_excluded_examples_after_repeat"], 3)
            self.assertEqual(stats["cosent_exclude_tags"], ["antonym_mid"])
            self.assertEqual(stats["cosine_excluded_rows"], 0)
            self.assertEqual(stats["cosine_excluded_examples_after_repeat"], 0)
            self.assertEqual(stats["cosine_exclude_tags"], [])
            self.assertEqual(stats["bucket_only_tags"], ["same_category_but_far"])
            self.assertEqual(stats["bucket_only_rows"], 1)
            self.assertEqual(stats["bucket_only_examples_after_repeat"], 2)
            self.assertEqual(stats["cosent_bucket_only_excluded_rows"], 1)
            self.assertEqual(stats["cosent_bucket_only_excluded_examples_after_repeat"], 2)
            self.assertEqual(stats["cosine_bucket_only_excluded_rows"], 1)
            self.assertEqual(stats["cosine_bucket_only_excluded_examples_after_repeat"], 2)
            self.assertEqual(stats["contrastive_bucket_only_excluded_rows"], 1)
            self.assertEqual(stats["contrastive_bucket_only_excluded_examples_after_repeat"], 2)
            self.assertEqual(stats["midpoint_tags"], ["antonym_mid"])
            self.assertEqual(stats["midpoint_repeat_boost"], 2.0)
            self.assertEqual(stats["midpoint_band_low"], 0.45)
            self.assertEqual(stats["midpoint_band_high"], 0.55)
            self.assertEqual(stats["midpoint_band_weight"], 4.0)
            self.assertEqual(stats["midpoint_center_weight"], 1.0)
            self.assertEqual(stats["midpoint_examples_after_repeat"], 6)
            self.assertEqual(len(examples), 9)
            self.assertEqual(len(cosent_examples), 4)
            self.assertEqual(len(cosine_examples), 7)
            self.assertEqual(len(contrastive_examples), 2)
            self.assertEqual(len(midpoint_examples), 6)
            self.assertEqual(len(bucket_band_examples), 6)
            self.assertFalse(any("飞机" in example.texts[0] for example in cosent_examples))
            self.assertFalse(any("飞机" in example.texts[0] for example in cosine_examples))
            self.assertTrue(any("风之谷" in example.texts[0] for example in cosent_examples))
            self.assertTrue(any("风之谷" in example.texts[0] for example in cosine_examples))
            self.assertTrue(any(abs(example.label - 0.22) < 1e-9 for example in bucket_band_examples))
            self.assertTrue(any(abs(example.label - 0.5) < 1e-9 for example in examples))
            self.assertFalse(any("高兴" in example.texts[0] for example in cosent_examples))
            self.assertTrue(any("高兴" in example.texts[0] for example in cosine_examples))
            self.assertTrue(all(abs(example.label - 0.5) < 1e-9 for example in midpoint_examples))

    def test_supervised_trainer_gives_priority_antonym_patch_rows_full_angle_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n"
                "医生,大夫,alias_synonym_high,90,1.0,review\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_priority_repeat = trainer.PRIORITY_ANTONYM_MIN_ANGLE_REPEAT
            previous_excluded = trainer.COSENT_EXCLUDE_TAGS
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.PRIORITY_ANTONYM_MIN_ANGLE_REPEAT = len(trainer.ANGLES)
                trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.COSINE_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                examples, cosent_examples, cosine_examples, _, midpoint_examples, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.PRIORITY_ANTONYM_MIN_ANGLE_REPEAT = previous_priority_repeat
                trainer.COSENT_EXCLUDE_TAGS = previous_excluded
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.MIDPOINT_TAGS = previous_midpoint_tags

            self.assertEqual(stats["priority_antonym_rows"], 1)
            self.assertEqual(stats["priority_antonym_examples_after_repeat"], len(trainer.ANGLES))
            self.assertEqual(stats["antonym_mid_examples_after_repeat"], len(trainer.ANGLES))
            self.assertGreaterEqual(stats["full_angle_coverage_rows"], 1)
            self.assertEqual(len(cosent_examples), 2)
            self.assertEqual(len(cosine_examples), 2)
            self.assertEqual(len(midpoint_examples), len(trainer.ANGLES) * 2)
            self.assertEqual(len(examples), len(trainer.ANGLES) + 2)

    def test_supervised_trainer_gives_holdout_family_proxy_rows_full_angle_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,伤心,antonym_mid,50,4.0,required_antonym_proxy_train\n"
                "医生,大夫,alias_synonym_high,90,1.0,review\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive_proxy",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_proxy_repeat = trainer.PROXY_ANTONYM_MIN_ANGLE_REPEAT
            previous_excluded = trainer.COSENT_EXCLUDE_TAGS
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.PROXY_ANTONYM_MIN_ANGLE_REPEAT = len(trainer.ANGLES)
                trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.COSINE_EXCLUDE_TAGS = set()
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                examples, cosent_examples, cosine_examples, contrastive_examples, midpoint_examples, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.PROXY_ANTONYM_MIN_ANGLE_REPEAT = previous_proxy_repeat
                trainer.COSENT_EXCLUDE_TAGS = previous_excluded
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.MIDPOINT_TAGS = previous_midpoint_tags

            proxy_examples = [
                example
                for example in examples
                if "高兴" in example.texts[0] and "伤心" in example.texts[1]
            ]
            covered_angles = {
                angle
                for angle in trainer.ANGLES
                if any(example.texts[0].startswith(angle) for example in proxy_examples)
            }
            self.assertEqual(stats["proxy_antonym_rows"], 1)
            self.assertEqual(stats["proxy_antonym_examples_after_repeat"], len(trainer.ANGLES))
            self.assertEqual(stats["proxy_antonym_min_angle_repeat"], len(trainer.ANGLES))
            self.assertEqual(stats["antonym_mid_rows"], 1)
            self.assertEqual(stats["antonym_mid_examples_after_repeat"], len(trainer.ANGLES))
            self.assertEqual(stats["cosent_excluded_rows"], 1)
            self.assertEqual(stats["cosent_excluded_examples_after_repeat"], len(trainer.ANGLES))
            self.assertEqual(len(proxy_examples), len(trainer.ANGLES))
            self.assertEqual(covered_angles, set(trainer.ANGLES))
            self.assertEqual(len(examples), len(trainer.ANGLES) + 2)
            self.assertEqual(len(cosent_examples), 2)
            self.assertEqual(len(cosine_examples), len(examples))
            self.assertEqual(len(contrastive_examples), 2)
            self.assertEqual(len(midpoint_examples), len(trainer.ANGLES) * 2)

    def test_supervised_trainer_gives_required_antonym_rows_full_angle_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "永恒,瞬间,antonym_mid,50,4.0,required_antonym_patch\n"
                "医生,大夫,alias_synonym_high,90,1.0,review\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_required_repeat = trainer.REQUIRED_ANTONYM_MIN_ANGLE_REPEAT
            previous_excluded = trainer.COSENT_EXCLUDE_TAGS
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.REQUIRED_ANTONYM_MIN_ANGLE_REPEAT = len(trainer.ANGLES)
                trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.COSINE_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                examples, cosent_examples, cosine_examples, _, midpoint_examples, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.REQUIRED_ANTONYM_MIN_ANGLE_REPEAT = previous_required_repeat
                trainer.COSENT_EXCLUDE_TAGS = previous_excluded
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.MIDPOINT_TAGS = previous_midpoint_tags

            self.assertEqual(stats["required_antonym_rows"], 1)
            self.assertEqual(stats["required_antonym_examples_after_repeat"], len(trainer.ANGLES))
            self.assertGreaterEqual(stats["full_angle_coverage_rows"], 1)
            self.assertEqual(stats["antonym_mid_examples_after_repeat"], len(trainer.ANGLES))
            self.assertEqual(len(cosent_examples), 2)
            self.assertEqual(len(cosine_examples), 2)
            self.assertEqual(len(midpoint_examples), len(trainer.ANGLES) * 2)
            self.assertEqual(len(examples), len(trainer.ANGLES) + 2)

    def test_supervised_trainer_pins_regression_pairs_during_max_row_sampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            rows = [
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer",
                "火影,海贼王,same_category_mid,45,1.0,category_graded_script",
                "海贼王,火影,same_category_mid,45,1.0,category_graded_script",
            ]
            for idx in range(30):
                rows.append(
                    f"填充词{idx},干扰词{idx},hard_negative_low,15,1.0,review"
                )
            train_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_regression_keys = trainer.REGRESSION_PAIR_KEYS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_excluded = trainer.COSENT_EXCLUDE_TAGS
            previous_cosine_excluded = trainer.COSINE_EXCLUDE_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            try:
                trainer.MAX_TRAIN_ROWS = 4
                trainer.MAX_REPEAT = 1
                trainer.REGRESSION_PAIR_KEYS = {("海贼王", "火影")}
                trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.COSINE_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                examples, _, _, _, _, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.REGRESSION_PAIR_KEYS = previous_regression_keys
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.COSENT_EXCLUDE_TAGS = previous_excluded
                trainer.COSINE_EXCLUDE_TAGS = previous_cosine_excluded
                trainer.MIDPOINT_TAGS = previous_midpoint_tags

            selected_examples = {
                tuple(text.split("：", 1)[-1] for text in example.texts)
                for example in examples
            }
            self.assertIn(("火影", "海贼王"), selected_examples)
            self.assertIn(("海贼王", "火影"), selected_examples)
            self.assertEqual(stats["source_rows"], 4)
            self.assertEqual(stats["regression_protected_rows"], 2)
            self.assertGreaterEqual(stats["pinned_high_value_rows"], 2)

    def test_supervised_trainer_parses_tag_bucket_min_rows(self):
        spec = importlib.util.spec_from_file_location(
            "train_v28c_mse_contrastive",
            REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
        )
        self.assertIsNotNone(spec)
        trainer = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
            spec.loader.exec_module(trainer)

        parsed = trainer.parse_min_tag_bucket_rows(
            "same_category_mid@40-59:12, hint_like_high@80-100:8, broken, antonym_mid@oops:5"
        )

        self.assertEqual(
            parsed,
            {
                ("same_category_mid", "40-59"): 12,
                ("hint_like_high", "80-100"): 8,
            },
        )

    def test_supervised_trainer_prioritizes_min_tag_bucket_rows_during_sampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            rows = ["answer,user_input,relation_tag,score_0_100,sample_weight,reviewer"]
            for idx in range(5):
                rows.append(f"低分同类{idx},干扰{idx},same_category_mid,30,1.0,review")
            for idx in range(2):
                rows.append(f"中分同类{idx},中分近义{idx},same_category_mid,55,1.0,review")
            for idx in range(2):
                rows.append(f"高分同类{idx},高分近义{idx},same_category_mid,70,1.0,review")
            for idx in range(6):
                rows.append(f"负样本{idx},反例{idx},hard_negative_low,10,1.0,review")
            train_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_angle_mode = trainer.ANGLE_MODE
            previous_min_tag_rows = trainer.MIN_TAG_ROWS
            previous_min_tag_bucket_rows = trainer.MIN_TAG_BUCKET_ROWS
            try:
                trainer.MAX_TRAIN_ROWS = 4
                trainer.MAX_REPEAT = 1
                trainer.ANGLE_MODE = "none"
                trainer.MIN_TAG_ROWS = {}
                trainer.MIN_TAG_BUCKET_ROWS = {
                    ("same_category_mid", "40-59"): 2,
                    ("same_category_mid", "60-79"): 2,
                }
                examples, _, _, _, _, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.ANGLE_MODE = previous_angle_mode
                trainer.MIN_TAG_ROWS = previous_min_tag_rows
                trainer.MIN_TAG_BUCKET_ROWS = previous_min_tag_bucket_rows

            label_counts = Counter(example.label for example in examples)
            self.assertEqual(stats["source_rows"], 4)
            self.assertEqual(
                stats["min_tag_bucket_rows"],
                {
                    "same_category_mid@40-59": 2,
                    "same_category_mid@60-79": 2,
                },
            )
            self.assertEqual(label_counts[0.55], 2)
            self.assertEqual(label_counts[0.7], 2)

    def test_supervised_trainer_enforces_min_angle_repeat_tag_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "副本,开荒,same_category_mid,70,1.0,review\n"
                "升级,组队,same_category_mid,60,1.0,review\n"
                "白露,地表湿,hint_like_high,80,1.0,review\n"
                "飞机,轮船,same_category_but_far,22,1.0,review\n",
                encoding="utf-8",
            )

            spec = importlib.util.spec_from_file_location(
                "train_v28c_mse_contrastive",
                REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
            )
            self.assertIsNotNone(spec)
            trainer = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                spec.loader.exec_module(trainer)

            previous_max_rows = trainer.MAX_TRAIN_ROWS
            previous_max_repeat = trainer.MAX_REPEAT
            previous_angle_mode = trainer.ANGLE_MODE
            previous_min_angle_repeat_for_high_value = trainer.MIN_ANGLE_REPEAT_FOR_HIGH_VALUE
            previous_min_angle_repeat_tag_buckets = trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.ANGLE_MODE = "cycle"
                trainer.MIN_ANGLE_REPEAT_FOR_HIGH_VALUE = 0
                trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS = {
                    ("same_category_mid", "60-79"): 4,
                }
                examples, _, _, _, _, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.ANGLE_MODE = previous_angle_mode
                trainer.MIN_ANGLE_REPEAT_FOR_HIGH_VALUE = previous_min_angle_repeat_for_high_value
                trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS = previous_min_angle_repeat_tag_buckets

            label_counts = Counter(example.label for example in examples)
            self.assertEqual(stats["source_rows"], 4)
            self.assertEqual(
                stats["min_angle_repeat_tag_buckets"],
                {"same_category_mid@60-79": 4},
            )
            self.assertEqual(
                stats["tag_bucket_angle_repeat_rows"],
                {"same_category_mid@60-79": 2},
            )
            self.assertEqual(
                stats["tag_bucket_angle_repeat_examples_after_repeat"],
                {"same_category_mid@60-79": 8},
            )
            self.assertEqual(label_counts[0.7], 4)
            self.assertEqual(label_counts[0.6], 4)
            self.assertEqual(label_counts[0.8], 2)
            self.assertEqual(label_counts[0.22], 2)

    def test_supervised_trainer_default_covers_eval_angles_for_category_boundary_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            train_csv = Path(tmp) / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "低分同类,低分近义,same_category_mid,30,1.0,review\n"
                "中分同类,中分近义,same_category_mid,55,1.0,review\n"
                "高分同类,高分近义,same_category_mid,70,1.0,review\n"
                "同类远负,同类远负对,same_category_but_far,22,1.0,review\n"
                "医生,大夫,alias_synonym_high,90,1.0,review\n",
                encoding="utf-8",
            )

            previous_env = os.environ.pop("SEM_MIN_ANGLE_REPEAT_TAG_BUCKETS", None)
            try:
                spec = importlib.util.spec_from_file_location(
                    "train_v28c_mse_contrastive_default_angle_coverage",
                    REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py",
                )
                self.assertIsNotNone(spec)
                trainer = importlib.util.module_from_spec(spec)
                self.assertIsNotNone(spec.loader)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=Warning, message="urllib3 v2 only supports OpenSSL")
                    spec.loader.exec_module(trainer)
            finally:
                if previous_env is not None:
                    os.environ["SEM_MIN_ANGLE_REPEAT_TAG_BUCKETS"] = previous_env

            previous_values = {
                "MAX_TRAIN_ROWS": trainer.MAX_TRAIN_ROWS,
                "MAX_REPEAT": trainer.MAX_REPEAT,
                "ANGLE_MODE": trainer.ANGLE_MODE,
                "MIN_ANGLE_REPEAT_FOR_HIGH_VALUE": trainer.MIN_ANGLE_REPEAT_FOR_HIGH_VALUE,
                "MIN_TAG_ROWS": trainer.MIN_TAG_ROWS,
                "MIN_TAG_BUCKET_ROWS": trainer.MIN_TAG_BUCKET_ROWS,
            }
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.ANGLE_MODE = "cycle"
                trainer.MIN_ANGLE_REPEAT_FOR_HIGH_VALUE = 0
                trainer.MIN_TAG_ROWS = {}
                trainer.MIN_TAG_BUCKET_ROWS = {}
                examples, _, _, _, _, _, stats = trainer.load_examples(train_csv, 123)
            finally:
                for name, value in previous_values.items():
                    setattr(trainer, name, value)

            self.assertEqual(
                trainer.MIN_ANGLE_REPEAT_TAG_BUCKETS,
                {
                    ("same_category_but_far", "20-39"): 5,
                    ("same_category_mid", "20-39"): 5,
                    ("same_category_mid", "40-59"): 5,
                    ("same_category_mid", "60-79"): 5,
                },
            )
            self.assertEqual(
                stats["tag_bucket_angle_repeat_rows"],
                {
                    "same_category_but_far@20-39": 1,
                    "same_category_mid@20-39": 1,
                    "same_category_mid@40-59": 1,
                    "same_category_mid@60-79": 1,
                },
            )
            self.assertEqual(
                stats["tag_bucket_angle_repeat_examples_after_repeat"],
                {
                    "same_category_but_far@20-39": 5,
                    "same_category_mid@20-39": 5,
                    "same_category_mid@40-59": 5,
                    "same_category_mid@60-79": 5,
                },
            )
            for answer, user_input in (
                ("低分同类", "低分近义"),
                ("中分同类", "中分近义"),
                ("高分同类", "高分近义"),
                ("同类远负", "同类远负对"),
            ):
                covered_angles = {
                    angle
                    for angle in trainer.ANGLES
                    if any(
                        example.texts[0] == f"{angle}{answer}"
                        and example.texts[1] == f"{angle}{user_input}"
                        for example in examples
                    )
                }
                self.assertEqual(covered_angles, set(trainer.ANGLES))

    def _prepare_fake_repo(self, root: Path) -> None:
        (root / "scripts").mkdir(parents=True)
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir(parents=True)
        (root / "models" / "bge-m3-finetuned-v27-semreal-anchor").mkdir(parents=True)
        (root / ".nightly" / "data" / "models" / "bge-m3-finetuned-v27-semreal-anchor").mkdir(parents=True)
        (root / ".nightly" / "data" / "calib").mkdir(parents=True)
        (root / ".nightly" / "data" / "tmp").mkdir(parents=True)
        (root / ".nightly" / "reports").mkdir(parents=True)
        (root / ".venv" / "bin").mkdir(parents=True)

        (root / "assets" / "puzzles.json").write_text("[]\n", encoding="utf-8")
        (root / "data" / "manual_similarity_overrides.json").write_text("{}\n", encoding="utf-8")
        (root / "data" / "semantic_scoring_user_input_template.csv").write_text(
            "answer,user_input,score_0_100\n猫,猫咪,95\n",
            encoding="utf-8",
        )
        (root / "data" / "train_v28c_balanced.csv").write_text(
            "id,answer,user_input,relation_tag,score_0_100,sample_weight\n1,猫,猫咪,alias_synonym_high,95,1.0\n",
            encoding="utf-8",
        )
        (root / "data" / "semantic_calibration_v27_semreal_anchor.json").write_text(
            '{"x_pred":[0,100],"y_calibrated":[0,100]}\n',
            encoding="utf-8",
        )
        (root / ".nightly" / "data" / "calib" / "semantic_calibration_v27_semreal_anchor.json").write_text(
            '{"x_pred":[0,100],"y_calibrated":[0,100]}\n',
            encoding="utf-8",
        )
        (root / "models" / "bge-m3-finetuned-v27-semreal-anchor" / "config_sentence_transformers.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (root / ".nightly" / "data" / "models" / "bge-m3-finetuned-v27-semreal-anchor" / "config_sentence_transformers.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (root / "models" / "bge-m3-finetuned-v27-semreal-anchor" / "round.txt").write_text(
            "project-base\n",
            encoding="utf-8",
        )
        (root / ".nightly" / "data" / "models" / "bge-m3-finetuned-v27-semreal-anchor" / "round.txt").write_text(
            "nightly-base\n",
            encoding="utf-8",
        )

    def _write_round_aware_python(self, path: Path) -> None:
        self._write_executable(
            path,
            textwrap.dedent(
                """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
env = os.environ
script = args[0] if args else ''

# Determine round number from env vars
round_num = '0'
for key in ('SEM_OUTPUT_MODEL', 'SEM_MODEL_PATH', 'SEM_OUTPUT_CALIB',
            'SEM_BASE_MODEL', 'BASE_METRICS_JSON', 'NIGHTLY_METRICS_JSON',
            'SEM_CALIB_JSON'):
    val = env.get(key, '')
    if '_r' in val:
        suffix = val.rsplit('_r', 1)[-1]
        digits = ''.join(ch for ch in suffix if ch.isdigit())
        if digits:
            round_num = digits
            break

if script.endswith('guard_hint_answer_overlap_v1.py'):
    print('{"input":"assets/puzzles.json","violations":0}')
    sys.exit(0)

if script.endswith('build_v26_gold_and_unsup.py') or script.endswith('build_nightly_semantic_sets.py'):
    gold_dir = pathlib.Path(env['SEM_UNSUP_PAIRS_JSONL']).parent
    gold_dir.mkdir(parents=True, exist_ok=True)
    pathlib.Path(env.get('SEM_GOLD_CALIB_CSV', gold_dir / 'gold_v26_calib.csv')).write_text('answer,user_input,relation_tag,score_0_100\\n猫,猫咪,alias_synonym_high,95\\n', encoding='utf-8')
    pathlib.Path(env.get('SEM_GOLD_EVAL_CSV', gold_dir / 'gold_v26_eval.csv')).write_text('answer,user_input,relation_tag,score_0_100\\n猫,猫咪,alias_synonym_high,95\\n', encoding='utf-8')
    pathlib.Path(env.get('SEM_GOLD_POOL_CSV', gold_dir / 'gold_v26_pool.csv')).write_text('answer,user_input,relation_tag,score_0_100\\n猫,猫咪,alias_synonym_high,95\\n', encoding='utf-8')
    if 'SEM_OUTPUT_TRAIN_CSV' in env:
        pathlib.Path(env['SEM_OUTPUT_TRAIN_CSV']).write_text('answer,user_input,relation_tag,score_0_100,sample_weight\\n猫,猫咪,alias_synonym_high,95,1.0\\n', encoding='utf-8')
    (gold_dir / 'gold_v26_manual_anchor.csv').write_text('text_a,text_b,label\\n猫,猫咪,0.95\\n', encoding='utf-8')
    pathlib.Path(env['SEM_UNSUP_PAIRS_JSONL']).write_text('{"text_a":"猫","text_b":"猫咪"}\\n', encoding='utf-8')
    if env.get('SEM_BUILD_STATS_JSON'):
        pathlib.Path(env['SEM_BUILD_STATS_JSON']).write_text(json.dumps({
            'train_rows': 1,
            'gold_pool': 1,
            'train_gold': 1,
            'calib': 1,
            'eval': 1,
            'fixed_holdout': 0,
            'unsup_pairs': 1,
            'gold_buckets': {'80-100': 1},
            'top_train_tags': {'alias_synonym_high': 1},
        }), encoding='utf-8')
    print('written=' + str(gold_dir))
    sys.exit(0)

if script.endswith('pretrain_v26_unsupervised.py') or script.endswith('finetune_v19_split.py') or script.endswith('train_v28c_mse_contrastive.py'):
    if script.endswith('train_v28c_mse_contrastive.py') and env.get('FAKE_FAIL_SUPERVISED_UNLESS_CPU') == '1' and env.get('SEM_DEVICE') != 'cpu':
        print('simulated MPS failure', file=sys.stderr)
        sys.exit(42)
    if script.endswith('train_v28c_mse_contrastive.py') and env.get('SEM_TRAIN_STATS_JSON'):
        pathlib.Path(env['SEM_TRAIN_STATS_JSON']).write_text(json.dumps({
            'source_rows': 300,
            'sample_seed': int(env.get('SEM_SAMPLE_SEED', '-1')),
            'train_examples_after_repeat': 579,
            'cosent_examples_after_repeat': 426,
            'cosent_exclude_tags': ['antonym_mid'],
            'cosent_excluded_rows': 51,
            'cosent_excluded_examples_after_repeat': 153,
            'cosent_base_guard_enabled': True,
            'cosent_base_guard_weight': 1.0,
            'cosent_base_guard_margin': 0.02,
            'cosent_base_guard_examples': 426,
            'cosent_base_guard_protected_examples': 180,
            'midpoint_base_guard_enabled': True,
            'midpoint_base_guard_weight': 1.0,
            'midpoint_base_guard_margin': 0.02,
            'midpoint_base_guard_examples': 306,
            'midpoint_base_guard_protected_examples': 180,
            'midpoint_tags': ['antonym_mid'],
            'midpoint_repeat_boost': 2.0,
            'midpoint_examples_after_repeat': 306,
            'contrastive_examples_after_repeat': 66,
            'hard_negative_rows': 66,
            'antonym_mid_rows': 51,
            'antonym_mid_examples_after_repeat': 153,
            'min_tag_rows': {'antonym_mid': 45},
            'min_tag_bucket_rows': {'same_category_mid@40-59': 20, 'same_category_mid@60-79': 12},
            'tag_counts': {'antonym_mid': 51, 'hard_negative_low': 66},
        }, ensure_ascii=False), encoding='utf-8')
    out_dir = pathlib.Path(env['SEM_OUTPUT_MODEL'])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'config_sentence_transformers.json').write_text('{}\\n', encoding='utf-8')
    (out_dir / 'round.txt').write_text(round_num + '\\n', encoding='utf-8')
    print('saved=' + str(out_dir))
    sys.exit(0)

if script.endswith('eval_v26_gold.py'):
    json_out = ''
    for i, arg in enumerate(args):
        if arg == '--json-out' and i + 1 < len(args):
            json_out = args[i + 1]
            break

    # Round-specific metrics to make round 2 the best
    metrics_by_round = {
        '1': {'raw_mae': 4.9, 'raw_bucket_acc': 80.0, 'cal_mae': 3.4, 'cal_bucket_acc': 83.0},
        '2': {'raw_mae': 4.7, 'raw_bucket_acc': 84.0, 'cal_mae': 3.1, 'cal_bucket_acc': 88.0},
        '3': {'raw_mae': 5.1, 'raw_bucket_acc': 79.0, 'cal_mae': 3.8, 'cal_bucket_acc': 82.0},
        '0': {'raw_mae': 4.8, 'raw_bucket_acc': 81.0, 'cal_mae': 3.5, 'cal_bucket_acc': 84.0},
    }
    payload = metrics_by_round.get(round_num, metrics_by_round['0']).copy()
    model_path = env.get('SEM_MODEL_PATH', '')
    if 'bge-m3-finetuned-v27-semreal-anchor' in model_path:
        payload['raw_mae'] += 0.5
        payload['cal_mae'] += 0.5
        payload['raw_bucket_acc'] -= 2.0
        payload['cal_bucket_acc'] -= 2.0
    payload.update({
        'eval_rows': 1,
        'support_positive_calibration_target_low': float(env.get('SEM_CALIB_SUPPORT_POSITIVE_TARGET_LOW', '40')),
        'group_metrics': {
            'hard_negative': {'count': 1, 'cal_mae': 2.0, 'cal_bucket_acc': 100.0, 'low_score_precision_at_30': 100.0},
            'synonym_alias': {'count': 1, 'cal_mae': 2.0, 'cal_bucket_acc': 100.0, 'recall_at_70': 100.0},
            'antonym': {
                'count': 1,
                'cal_mae': 2.0,
                'cal_bucket_acc': 100.0,
                'mid_score_recall_40_60': 100.0,
                'mid_score_recall_45_55': 100.0,
            },
        },
        'worst_cases': [],
        'bucket_confusion': [
            {
                'target_bucket': '80-100',
                'cal_bucket': '60-80',
                'count': 2,
                'avg_abs_error': 18.5,
                'max_abs_error': 22.0,
                'top_tags': [{'tag': 'alias_synonym_high', 'count': 2}],
                'top_groups': [{'group': 'synonym_alias', 'count': 2}],
                'examples': ['医生->大夫', '开心->快乐'],
            }
        ],
        'model_path': model_path,
        'calib_csv': env.get('SEM_CALIB_CSV', ''),
        'eval_csv': env.get('SEM_EVAL_CSV', ''),
        'calib_json': env.get('SEM_CALIB_JSON', ''),
    })

    calib_path = pathlib.Path(env['SEM_CALIB_JSON'])
    calib_path.parent.mkdir(parents=True, exist_ok=True)
    calib_path.write_text('{"x_pred":[0,100],"y_calibrated":[0,100]}\\n', encoding='utf-8')

    if json_out:
        out_path = pathlib.Path(json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    print('metrics_written=' + json_out)
    sys.exit(0)

if script.endswith('run_regression_pairs_v23.py'):
    print('summary:')
    print('total=35 passed=35 pass_rate=100.0%')
    sys.exit(0)

# Handle stdin gate evaluation (script == '-')
if script == '-' or script == '':
    if 'BUILD_STATS_TITLE' in env:
        out = pathlib.Path(env['BUILD_STATS_REPORT_OUT'])
        with out.open('a', encoding='utf-8') as f:
            f.write('\\n## ' + env['BUILD_STATS_TITLE'] + '\\n')
            f.write('| item | value |\\n')
            f.write('| train_rows | 1 |\\n')
            f.write('\\n### Top Train Tags\\n')
            f.write('| tag | count |\\n')
            f.write('| alias_synonym_high | 1 |\\n')
        sys.exit(0)

    if 'TRAIN_STATS_TITLE' in env:
        stats = json.loads(pathlib.Path(env['TRAIN_STATS_JSON']).read_text(encoding='utf-8'))
        out = pathlib.Path(env['TRAIN_STATS_REPORT_OUT'])
        with out.open('a', encoding='utf-8') as f:
            f.write('\\n## ' + env['TRAIN_STATS_TITLE'] + '\\n')
            f.write('| item | value |\\n')
            f.write('| antonym_mid_rows | ' + str(stats.get('antonym_mid_rows')) + ' |\\n')
            f.write('| antonym_mid_examples_after_repeat | ' + str(stats.get('antonym_mid_examples_after_repeat')) + ' |\\n')
            f.write('| cosent_excluded_examples_after_repeat | ' + str(stats.get('cosent_excluded_examples_after_repeat')) + ' |\\n')
            f.write('| cosent_base_guard_enabled | ' + str(stats.get('cosent_base_guard_enabled')) + ' |\\n')
            f.write('| cosent_base_guard_weight | ' + str(stats.get('cosent_base_guard_weight')) + ' |\\n')
            f.write('| cosent_base_guard_margin | ' + str(stats.get('cosent_base_guard_margin')) + ' |\\n')
            f.write('| cosent_base_guard_examples | ' + str(stats.get('cosent_base_guard_examples')) + ' |\\n')
            f.write('| cosent_base_guard_protected_examples | ' + str(stats.get('cosent_base_guard_protected_examples')) + ' |\\n')
            f.write('| midpoint_base_guard_enabled | ' + str(stats.get('midpoint_base_guard_enabled')) + ' |\\n')
            f.write('| midpoint_base_guard_weight | ' + str(stats.get('midpoint_base_guard_weight')) + ' |\\n')
            f.write('| midpoint_base_guard_margin | ' + str(stats.get('midpoint_base_guard_margin')) + ' |\\n')
            f.write('| midpoint_base_guard_examples | ' + str(stats.get('midpoint_base_guard_examples')) + ' |\\n')
            f.write('| midpoint_base_guard_protected_examples | ' + str(stats.get('midpoint_base_guard_protected_examples')) + ' |\\n')
            f.write('| min_tag_rows | ' + json.dumps(stats.get('min_tag_rows'), ensure_ascii=False, sort_keys=True) + ' |\\n')
            f.write('| min_tag_bucket_rows | ' + json.dumps(stats.get('min_tag_bucket_rows'), ensure_ascii=False, sort_keys=True) + ' |\\n')
            f.write('\\n### Selected Tag Counts\\n')
            f.write('| tag | count |\\n')
            f.write('| antonym_mid | ' + str((stats.get('tag_counts') or {}).get('antonym_mid')) + ' |\\n')
        sys.exit(0)

    if 'DIAG_TITLE' in env:
        out = pathlib.Path(env['METRICS_REPORT_OUT'])
        with out.open('a', encoding='utf-8') as f:
            f.write('\\n## ' + env['DIAG_TITLE'] + '\\n')
            f.write('| group | base_mae | cand_mae | base_acc | cand_acc | extra |\\n')
            f.write('| hard_negative | 2.0 | 2.0 | 100.0 | 100.0 | low@30 100.0 -> 100.0 |\\n')
            f.write('| synonym_alias | 2.0 | 2.0 | 100.0 | 100.0 | recall@70 100.0 -> 100.0 |\\n')
            f.write('| antonym | 2.0 | 2.0 | 100.0 | 100.0 | mid@40-60 100.0 -> 100.0; strict@45-55 100.0 -> 100.0 |\\n')
            f.write('\\n### 候选最差样本\\n')
            f.write('| answer | input | target | candidate | error | group | tag |\\n')
            f.write('\\n### 校准桶错分 Top\\n')
            f.write('| target_bucket | predicted_bucket | base_count | cand_count | cand_avg_error | top_tags | top_groups | examples |\\n')
            f.write('| 80-100 | 60-80 | 1 | 2 | 18.5 | alias_synonym_high:2 | synonym_alias:2 | 医生->大夫, 开心->快乐 |\\n')
        sys.exit(0)

    # Determine round number from env vars (check various paths)
    round_num = '0'
    for key in ('SEM_OUTPUT_MODEL', 'SEM_MODEL_PATH', 'SEM_OUTPUT_CALIB',
                'SEM_BASE_MODEL', 'BASE_METRICS_JSON', 'NIGHTLY_METRICS_JSON',
                'SEM_CALIB_JSON'):
        val = env.get(key, '')
        if '_r' in val:
            suffix = val.rsplit('_r', 1)[-1]
            digits = ''.join(ch for ch in suffix if ch.isdigit())
            if digits:
                round_num = digits
                break

    metrics_by_round = {
        '1': {'cal_mae': 4.3, 'cal_bucket_acc': 82.0, 'raw_mae': 4.9, 'raw_bucket_acc': 80.0},
        '2': {'cal_mae': 3.6, 'cal_bucket_acc': 87.0, 'raw_mae': 4.7, 'raw_bucket_acc': 84.0},
        '3': {'cal_mae': 4.7, 'cal_bucket_acc': 81.0, 'raw_mae': 5.1, 'raw_bucket_acc': 79.0},
        '0': {'cal_mae': 4.1, 'cal_bucket_acc': 83.0, 'raw_mae': 4.8, 'raw_bucket_acc': 81.0},
    }
    m = metrics_by_round.get(round_num, metrics_by_round['0'])

    # Anchor selection gate
    if 'PRETRAIN_METRICS_JSON' in env:
        print('use_anchor=False')
        sys.exit(0)

    # Metric gate (round or best-round)
# Round gate: base_mae + base_acc side is slightly worse so cand wins
# Best-round gate: project_cal_mae / best_cal_mae format
base_mae = m['cal_mae'] + 0.5  # base/project side is slightly worse
cand_mae = m['cal_mae']
base_acc = m['cal_bucket_acc'] - 2.0
cand_acc = m['cal_bucket_acc']
base_raw_mae = m['raw_mae'] + 0.5
cand_raw_mae = m['raw_mae']
base_raw_acc = m['raw_bucket_acc'] - 2.0
cand_raw_acc = m['raw_bucket_acc']

min_mae = float(env.get('MIN_MAE_IMPROVEMENT', '0.0'))
min_acc = float(env.get('MIN_ACC_IMPROVEMENT', '0.0'))
mae_ok = cand_mae <= (base_mae - min_mae)
acc_ok = cand_acc >= (base_acc + min_acc)
raw_mae_no_degrade = cand_raw_mae <= base_raw_mae
raw_acc_no_degrade = cand_raw_acc >= base_raw_acc
cal_mae_no_degrade = cand_mae <= base_mae
cal_acc_no_degrade = cand_acc >= base_acc
no_degrade_all = raw_mae_no_degrade and raw_acc_no_degrade and cal_mae_no_degrade and cal_acc_no_degrade
strict_improve = (cand_mae < base_mae or cand_acc > base_acc or cand_raw_mae < base_raw_mae or cand_raw_acc > base_raw_acc)
reg_ok = True
accepted = mae_ok and acc_ok and reg_ok and strict_improve

# Detect best-round gate (BASE_METRICS_JSON path doesn't have _r<N>, so round_num='0')
# Output both formats so both round gate and best-round gate awk extraction work
print(f'base_cal_mae={base_mae:.4f}')
print(f'base_cal_bucket_acc={base_acc:.2f}')
print(f'cand_cal_mae={cand_mae:.4f}')
print(f'cand_cal_bucket_acc={cand_acc:.2f}')
print(f'base_raw_mae={base_raw_mae:.4f}')
print(f'base_raw_bucket_acc={base_raw_acc:.2f}')
print(f'cand_raw_mae={cand_raw_mae:.4f}')
print(f'cand_raw_bucket_acc={cand_raw_acc:.2f}')
# Best-round gate format
print(f'project_cal_mae={base_mae:.4f}')
print(f'project_cal_bucket_acc={base_acc:.2f}')
print(f'best_cal_mae={cand_mae:.4f}')
print(f'best_cal_bucket_acc={cand_acc:.2f}')
print(f'project_raw_mae={base_raw_mae:.4f}')
print(f'project_raw_bucket_acc={base_raw_acc:.2f}')
print(f'best_raw_mae={cand_raw_mae:.4f}')
print(f'best_raw_bucket_acc={cand_raw_acc:.2f}')
print('project_antonym_mid_recall_45_55=100.00')
print('best_antonym_mid_recall_45_55=100.00')
print(f'mae_ok={mae_ok}')
print(f'acc_ok={acc_ok}')
print(f'raw_mae_no_degrade={raw_mae_no_degrade}')
print(f'raw_acc_no_degrade={raw_acc_no_degrade}')
print(f'cal_mae_no_degrade={cal_mae_no_degrade}')
print(f'cal_acc_no_degrade={cal_acc_no_degrade}')
print(f'no_degrade_all={no_degrade_all}')
print(f'strict_improve={strict_improve}')
print(f'regression_ok={reg_ok}')
print(f'accepted={accepted}')
sys.exit(0)

print('stubbed_python ' + ' '.join(args))
sys.exit(0)
"""
            ),
        )

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
