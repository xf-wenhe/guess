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


class NightlyScriptsTest(unittest.TestCase):
    def test_install_script_generates_project_local_three_round_launchd_job(self):
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
            self.assertIn("<string>3</string>", plist)
            self.assertNotIn("workspaces/guess_runtime", plist)
            self.assertIn(f"<string>{REPO_ROOT}/.nightly</string>", plist)

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
            self.assertIn("拒绝诊断 Round 1", promotion_text)
            self.assertIn("hard_negative", promotion_text)
            self.assertIn("synonym_alias", promotion_text)

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
    print('written=' + str(gold_dir))
    sys.exit(0)

if script.endswith('pretrain_v26_unsupervised.py') or script.endswith('finetune_v19_split.py') or script.endswith('train_v28c_mse_contrastive.py'):
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
    print('total=30 passed=30 pass_rate=100.0%')
    sys.exit(0)

# Handle stdin gate evaluation (script == '-')
if script == '-' or script == '':
    if 'DIAG_TITLE' in env:
        out = pathlib.Path(env['METRICS_REPORT_OUT'])
        with out.open('a', encoding='utf-8') as f:
            f.write('\\n## ' + env['DIAG_TITLE'] + '\\n')
            f.write('| group | base_mae | cand_mae | base_acc | cand_acc | extra |\\n')
            f.write('| hard_negative | 2.0 | 2.0 | 100.0 | 100.0 | low@30 100.0 -> 100.0 |\\n')
            f.write('| synonym_alias | 2.0 | 2.0 | 100.0 | 100.0 | recall@70 100.0 -> 100.0 |\\n')
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
