import csv
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_nightly_10pm_launchd.sh"
NIGHTLY_SCRIPT = REPO_ROOT / "scripts" / "nightly_train_v26.sh"
TRACE_EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "extract_score_trace_review_candidates.py"
WORST_CASE_EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "extract_nightly_worst_case_review_candidates.py"
BUILD_NIGHTLY_SETS_SCRIPT = REPO_ROOT / "scripts" / "build_nightly_semantic_sets.py"
REGRESSION_PAIRS_PATH = REPO_ROOT / "data" / "regression_pairs_v23.json"
ANALYZE_NIGHTLY_REPORT_SCRIPT = REPO_ROOT / "scripts" / "analyze_nightly_report_v26.py"


class NightlyScriptsTest(unittest.TestCase):
    def test_install_script_generates_project_local_daily_launchd_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home_dir = tmp_path / "home"
            fake_bin = tmp_path / "fake-bin"
            home_dir.mkdir(parents=True)
            fake_bin.mkdir(parents=True)

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
            self.assertIn("<key>NIGHTLY_ENABLE_ANCHOR_FINETUNE</key>", plist)
            self.assertIn("<key>NIGHTLY_MIN_MAE_IMPROVEMENT</key>", plist)
            self.assertIn("<string>0.3</string>", plist)
            self.assertIn("<key>NIGHTLY_MIN_ACC_IMPROVEMENT</key>", plist)
            self.assertIn("<string>2.0</string>", plist)
            self.assertIn("<key>NIGHTLY_REQUIRE_NO_DEGRADE_ALL</key>", plist)
            self.assertNotIn("workspaces/guess_runtime", plist)
            self.assertIn(f"<string>{REPO_ROOT}/.nightly</string>", plist)

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
                    | antonym | 10.0 | 8.0 | 20.0 | 60.0 | mid@40-60 20.0 -> 60.0 |
                    | same_category | 7.0 | 8.5 | 55.0 | 50.0 |  |
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
            self.assertIn("## 运行配置", promotion_text)
            self.assertIn("| requested_device | auto |", promotion_text)
            self.assertIn("| sup_rows | 300 |", promotion_text)
            self.assertIn("## 晋升门控", promotion_text)
            self.assertIn("| min_antonym_mid_recall_improvement | 0.0 |", promotion_text)
            self.assertIn("| regression_gate | passed == total |", promotion_text)

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
            self.assertIn("拒绝诊断 Round 1", promotion_text)
            self.assertIn("hard_negative", promotion_text)
            self.assertIn("synonym_alias", promotion_text)

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
            self.assertEqual(len(rows), 2)
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
            required_antonym_row = next(row for row in train_rows if (row["answer"], row["user_input"]) == ("古代", "现代"))
            self.assertEqual(required_antonym_row["reviewer"], "required_antonym_patch")
            self.assertEqual(required_antonym_row["relation_tag"], "antonym_mid")
            self.assertEqual(required_antonym_row["score_0_100"], "50")
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
        self.assertIn("protected_positive_rows", source)
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
            'antonym': {'count': 1, 'cal_mae': 2.0, 'cal_bucket_acc': 100.0, 'mid_score_recall_40_60': 100.0},
        },
        'worst_cases': [],
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

    if 'DIAG_TITLE' in env:
        out = pathlib.Path(env['METRICS_REPORT_OUT'])
        with out.open('a', encoding='utf-8') as f:
            f.write('\\n## ' + env['DIAG_TITLE'] + '\\n')
            f.write('| group | base_mae | cand_mae | base_acc | cand_acc | extra |\\n')
            f.write('| hard_negative | 2.0 | 2.0 | 100.0 | 100.0 | low@30 100.0 -> 100.0 |\\n')
            f.write('| synonym_alias | 2.0 | 2.0 | 100.0 | 100.0 | recall@70 100.0 -> 100.0 |\\n')
            f.write('| antonym | 2.0 | 2.0 | 100.0 | 100.0 | mid@40-60 100.0 -> 100.0 |\\n')
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
