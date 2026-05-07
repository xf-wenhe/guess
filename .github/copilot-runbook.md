# Copilot Runbook (Resume Quickly)

## 1) Verify Current Default
- Model directory expected: `models/bge-m3-finetuned-v27-semreal-anchor`
- Calibration expected: `data/semantic_calibration_v27_semreal_anchor.json`

## 2) Evaluate Baseline
- Gold eval:
  - `SEM_MODEL_PATH=models/bge-m3-finetuned-v27-semreal-anchor SEM_CALIB_CSV=data/gold_v26_calib.csv SEM_EVAL_CSV=data/gold_v26_eval.csv SEM_CALIB_JSON=data/semantic_calibration_v27_semreal_anchor.json .venv/bin/python scripts/eval_v26_gold.py --json-out tmp/eval_current.json`
- Regression:
  - `SEM_MODEL_PATH=models/bge-m3-finetuned-v27-semreal-anchor SEM_CALIB_PATH=data/semantic_calibration_v27_semreal_anchor.json .venv/bin/python scripts/run_regression_pairs_v23.py`

## 3) Train Candidate (Safe Pattern)
- Build training CSV first (semreal/hard-mining script as needed).
- Use small sample + conservative params on MPS.
- Example env guards:
  - `TOKENIZERS_PARALLELISM=false`
  - `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`

## 4) Candidate Acceptance Rule
- Accept only if:
  - candidate cal_mae <= baseline cal_mae
  - candidate cal_bucket_acc >= baseline cal_bucket_acc
  - regression 30/30 pass
- Otherwise delete candidate artifacts.

## 5) Nightly
- Installer script: `scripts/install_nightly_10pm_launchd.sh`
- Uninstaller: `scripts/uninstall_nightly_10pm_launchd.sh`
- Service id: `com.guess.nightly-train-v26`
- Quick status:
  - `launchctl print gui/$(id -u)/com.guess.nightly-train-v26`

## 6) Session Bootstrap Prompt (for new Copilot chat)
Use this as first message:

"Read `.github/copilot-memory.md` and `.github/copilot-runbook.md` first. Continue training from current production default `v27-semreal-anchor`. Never promote a candidate unless MAE improves, bucket accuracy improves, and regression is 30/30."
