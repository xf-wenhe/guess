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
        self.assertIn("Wait for the next real nightly report", pending_text)

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
            "sup_midpoint_tags": "antonym_mid",
        }
        analysis = {
            "train_sampling": [
                {
                    "round": "1",
                    "antonym_mid_examples_after_repeat": "153",
                    "cosent_exclude_tags": '["antonym_mid"]',
                    "cosent_excluded_examples_after_repeat": "153",
                    "midpoint_tags": '["antonym_mid"]',
                    "midpoint_examples_after_repeat": "306",
                }
            ]
        }
        ok = triage.semantic_strategy_checks(health, analysis)
        self.assertTrue(ok["ok"])
        self.assertFalse(ok["skipped"])

        analysis["train_sampling"][0]["cosent_excluded_examples_after_repeat"] = "10"
        bad = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad["ok"])
        self.assertIn("cosent_excluded_examples_after_repeat", bad["issues"][0])
        analysis["train_sampling"][0]["cosent_excluded_examples_after_repeat"] = "153"
        analysis["train_sampling"][0]["midpoint_examples_after_repeat"] = "10"
        bad_midpoint = triage.semantic_strategy_checks(health, analysis)
        self.assertFalse(bad_midpoint["ok"])
        self.assertIn("midpoint_examples_after_repeat", bad_midpoint["issues"][0])
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
        skipped = triage.semantic_strategy_checks(
            {
                "warnings": ["latest real report predates current launchd install; wait for next 23:00 run"],
                "sup_cosent_exclude_tags": "antonym_mid",
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
            self.assertIn("<key>NIGHTLY_SUP_COSENT_EXCLUDE_TAGS</key>", plist)
            self.assertIn("<string>antonym_mid</string>", plist)
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
                    | hard_negative_rows | 66 |
                    | antonym_mid_rows | 51 |
                    | antonym_mid_examples_after_repeat | 153 |
                    | cosent_exclude_tags | ["antonym_mid"] |
                    | cosent_excluded_examples_after_repeat | 153 |
                    | midpoint_tags | ["antonym_mid"] |
                    | midpoint_examples_after_repeat | 306 |
                    | min_tag_rows | {"antonym_mid": 45} |
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
            self.assertEqual(payload["analysis"]["failed_gates"], ["mae_ok"])
            self.assertEqual(payload["analysis"]["bucket_confusions"][0]["target_bucket"], "80-100")
            self.assertEqual(payload["analysis"]["bucket_confusions"][0]["top_tags"], "alias_synonym_high:3")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["antonym_mid_rows"], "51")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["antonym_mid_examples_after_repeat"], "153")
            self.assertEqual(payload["analysis"]["train_sampling"][0]["cosent_excluded_examples_after_repeat"], "153")
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
            self.assertIn("## Strategy Checks", md)
            self.assertIn("expected_cosent_exclude_tags: `antonym_mid`", md)
            self.assertIn("expected_midpoint_tags: `antonym_mid`", md)
            self.assertIn("alias_synonym_high:3", md)
            self.assertIn("source_counts:", md)
            self.assertIn("status_counts:", md)
            self.assertIn("severity_counts:", md)
            self.assertIn("validation_ok:", md)
            self.assertIn("`mae_ok`", md)
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
                    | min_tag_rows | {"antonym_mid": 45} |
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
            self.assertEqual(payload["antonym_group"]["group"], "antonym")
            self.assertEqual(payload["failed_gates"], ["mae_ok"])
            self.assertEqual(payload["group_regressions"][0]["group"], "same_category")
            self.assertEqual(payload["bucket_confusions"][0]["target_bucket"], "80-100")
            self.assertEqual(payload["bucket_confusions"][0]["predicted_bucket"], "60-80")
            self.assertEqual(payload["bucket_confusions"][0]["top_groups"], "synonym_alias:3")
            self.assertEqual(payload["train_sampling"][0]["round"], "1")
            self.assertEqual(payload["train_sampling"][0]["antonym_mid_rows"], "51")
            self.assertEqual(payload["train_sampling"][0]["antonym_mid_examples_after_repeat"], "153")
            self.assertEqual(payload["train_sampling"][0]["cosent_excluded_examples_after_repeat"], "153")

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
                    | sup_cosent_exclude_tags | antonym_mid |

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

                    ## 实际训练抽样 Round 2

                    | item | value |
                    |------|-------|
                    | antonym_mid_rows | 50 |
                    | antonym_mid_examples_after_repeat | 150 |
                    | cosent_exclude_tags | ["antonym_mid"] |
                    | cosent_excluded_examples_after_repeat | 150 |
                    | min_tag_rows | {"antonym_mid": 45} |
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
            self.assertEqual(rows[0]["antonym_mid_rows"], "50")
            self.assertEqual(rows[0]["cosent_excluded_examples_after_repeat"], "150")
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
            self.assertIn("拒绝诊断 Round 1", promotion_text)
            self.assertIn("hard_negative", promotion_text)
            self.assertIn("synonym_alias", promotion_text)
            self.assertIn("校准桶错分 Top", promotion_text)
            self.assertIn("| 80-100 | 60-80 |", promotion_text)

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
                "香蕉,苹果,same_category_mid,55,1.0\n",
                encoding="utf-8",
            )
            train_patch_path.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight\n"
                "香蕉,苹果,same_category_but_far,25,4.0\n"
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
            self.assertNotIn(holdout_pair, read_pairs(train_out))
            self.assertNotIn(holdout_pair, read_pairs(calib_out))
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
            stats = json.loads(stats_out.read_text(encoding="utf-8"))
            self.assertEqual(stats["fixed_holdout"], 1)
            self.assertEqual(stats["train_patch"], 7)
            self.assertGreaterEqual(stats["train_gold"], 1)

    def test_supervised_trainer_boosts_real_failure_hard_negative_tags_without_antonyms(self):
        source = (REPO_ROOT / "scripts" / "train_v28c_mse_contrastive.py").read_text(encoding="utf-8")

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
        self.assertIn('SEM_COSENT_EXCLUDE_TAGS", "antonym_mid"', source)
        self.assertIn("cosent_excluded_examples_after_repeat", source)
        self.assertIn("SEM_TRAIN_STATS_JSON", source)
        self.assertIn("SEM_MIN_ANGLE_REPEAT_FOR_HIGH_VALUE", source)
        self.assertIn("full_angle_coverage_rows", source)
        self.assertIn("SEM_LOSS_MODE", source)
        self.assertIn("CosineSimilarityLoss", source)
        self.assertIn("OnlineContrastiveLoss", source)
        self.assertIn("mixed_contrastive", source)
        self.assertIn("SEM_CONTRASTIVE_MARGIN", source)
        self.assertIn("SEM_CONTRASTIVE_SCOPE", source)
        self.assertIn("CONTRASTIVE_POSITIVE_TAGS", source)
        self.assertIn("contrastive_label_counts", source)
        self.assertIn("SEM_MIDPOINT_TAGS", source)
        self.assertIn("midpoint_examples_after_repeat", source)
        self.assertIn("MidpointBandLoss", source)
        self.assertIn('SEM_MIDPOINT_BAND_LOW", "0.45"', source)
        self.assertIn('SEM_MIDPOINT_BAND_HIGH", "0.55"', source)
        self.assertIn('SEM_MIDPOINT_BAND_WEIGHT", "4.0"', source)
        self.assertIn('SEM_MIDPOINT_CENTER_WEIGHT", "1.0"', source)

    def test_supervised_trainer_excludes_antonym_mid_from_cosent_and_adds_midpoint_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_csv = tmp_path / "train.csv"
            train_csv.write_text(
                "answer,user_input,relation_tag,score_0_100,sample_weight,reviewer\n"
                "高兴,难过,antonym_mid,50,4.0,nightly_patch_v2\n"
                "医生,大夫,alias_synonym_high,90,1.0,review\n"
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
            previous_excluded = trainer.COSENT_EXCLUDE_TAGS
            previous_midpoint_tags = trainer.MIDPOINT_TAGS
            previous_midpoint_boost = trainer.MIDPOINT_REPEAT_BOOST
            try:
                trainer.MAX_TRAIN_ROWS = 0
                trainer.MAX_REPEAT = 3
                trainer.COSENT_EXCLUDE_TAGS = {"antonym_mid"}
                trainer.MIDPOINT_TAGS = {"antonym_mid"}
                trainer.MIDPOINT_REPEAT_BOOST = 2.0
                examples, cosent_examples, contrastive_examples, midpoint_examples, stats = trainer.load_examples(train_csv, 123)
            finally:
                trainer.MAX_TRAIN_ROWS = previous_max_rows
                trainer.MAX_REPEAT = previous_max_repeat
                trainer.COSENT_EXCLUDE_TAGS = previous_excluded
                trainer.MIDPOINT_TAGS = previous_midpoint_tags
                trainer.MIDPOINT_REPEAT_BOOST = previous_midpoint_boost

            self.assertEqual(stats["antonym_mid_rows"], 1)
            self.assertEqual(stats["antonym_mid_examples_after_repeat"], 3)
            self.assertEqual(stats["cosent_excluded_rows"], 1)
            self.assertEqual(stats["cosent_excluded_examples_after_repeat"], 3)
            self.assertEqual(stats["cosent_exclude_tags"], ["antonym_mid"])
            self.assertEqual(stats["midpoint_tags"], ["antonym_mid"])
            self.assertEqual(stats["midpoint_repeat_boost"], 2.0)
            self.assertEqual(stats["midpoint_band_low"], 0.45)
            self.assertEqual(stats["midpoint_band_high"], 0.55)
            self.assertEqual(stats["midpoint_band_weight"], 4.0)
            self.assertEqual(stats["midpoint_center_weight"], 1.0)
            self.assertEqual(stats["midpoint_examples_after_repeat"], 6)
            self.assertEqual(len(examples), 7)
            self.assertEqual(len(cosent_examples), 4)
            self.assertEqual(len(contrastive_examples), 4)
            self.assertEqual(len(midpoint_examples), 6)
            self.assertTrue(any(abs(example.label - 0.5) < 1e-9 for example in examples))
            self.assertFalse(any(abs(example.label - 0.5) < 1e-9 for example in cosent_examples))
            self.assertTrue(all(abs(example.label - 0.5) < 1e-9 for example in midpoint_examples))

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
            'train_examples_after_repeat': 579,
            'cosent_examples_after_repeat': 426,
            'cosent_exclude_tags': ['antonym_mid'],
            'cosent_excluded_rows': 51,
            'cosent_excluded_examples_after_repeat': 153,
            'midpoint_tags': ['antonym_mid'],
            'midpoint_repeat_boost': 2.0,
            'midpoint_examples_after_repeat': 306,
            'contrastive_examples_after_repeat': 66,
            'hard_negative_rows': 66,
            'antonym_mid_rows': 51,
            'antonym_mid_examples_after_repeat': 153,
            'min_tag_rows': {'antonym_mid': 45},
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
            f.write('| min_tag_rows | ' + json.dumps(stats.get('min_tag_rows'), ensure_ascii=False, sort_keys=True) + ' |\\n')
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
