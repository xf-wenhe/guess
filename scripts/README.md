# Scripts Guide

This directory contains both current operational scripts and older experiment/build helpers. Prefer the entrypoints below unless you are rebuilding a historical dataset.

## Daily Semantic Model Loop

- `nightly_train_v26.sh`
  Main nightly training loop. Builds data, trains three daily candidate seeds by default, evaluates strict gates, and optionally promotes. The default device mode is `auto` so local GPU/MPS is used when available, with CPU retry for supervised training failures.
- `build_nightly_semantic_sets.py`
  Builds the nightly supervised train/eval/calibration files under `.nightly/data/gold/`. Fixed holdout rows are excluded from training and calibration.
- `train_v28c_mse_contrastive.py`
  Current supervised trainer. The filename is historical; the implementation supports `CoSENTLoss`, `CosineSimilarityLoss`, experimental `OnlineContrastiveLoss` mixed mode, hard-negative boost tags, protected positive tag boosts, pinned high-value review rows, and optional multi-angle coverage for high-value rows.
- `eval_v26_gold.py`
  Evaluates model/calibration metrics and emits group metrics plus worst cases.
- `run_regression_pairs_v23.py`
  Fixed semantic regression gate, including antonym/opposite pairs that must score in the 45-55 semantic range.
- `analyze_nightly_report_v26.py`
  Summarizes the latest non-dry-run promotion report, GPU/MPS evidence, failed gates, regressed groups, and antonym behavior.
- `check_nightly_launchd_v26.py`
  Verifies the active macOS LaunchAgent wrapper, three-run config, antonym gate env, current stderr health, and latest scheduled-run/report status.
- `nightly_next_morning_triage_v26.py`
  Preferred next-morning entrypoint. Combines launchd health, latest real-report analysis, device status, failed gates, and optional worst-case review CSV generation.
- `semantic_training_todo_status.py`
  Prints the live goal checklist from `docs/SEMANTIC_TRAINING_TODO.md`, including completed/pending counts and the remaining blocking items.
- `preflight_v26.sh`
  End-to-end deployment preflight for server, regression, and puzzle data.

## Data Quality And Review

- `extract_score_trace_review_candidates.py`
  Converts Flutter `SCORE_TRACE=true` logs into `data/score_trace_review_candidates.csv` for human review.
- `extract_nightly_worst_case_review_candidates.py`
  Converts rejected nightly worst cases into pending review rows. The nightly builder only consumes rows after review status becomes `approved` or `merged`.
- `validate_review_candidates.py`
  Validates review CSVs before approved/merged rows can safely feed training: score ranges, status/source/severity enums, duplicate pairs, and antonym rows fixed at 50.
- `guard_hint_answer_overlap_v1.py`
  Prevents hint/answer leakage before training.
- `preflight_training_noise_guard_v1.py`
  Checks label noise and duplicate/conflicting pairs.
- `merge_error_review_into_gold_v1.py`
  Merges approved human-reviewed error rows.
- `build_relabel_candidates_from_review_v1.py`
  Creates relabel candidates from reviewed failures.
- `apply_suggested_relabels_by_bucket_v1.py`
  Applies reviewed relabel suggestions.

## Dataset Builders Still Used As Sources

These scripts generate source CSVs that feed the nightly builder or document prior dataset versions:

- `build_v26_gold_and_unsup.py`
- `build_v27_hard_mining_csv.py`
- `build_v27_semreal_train_csv.py`
- `build_v28_*`
- `build_v28c_balanced_train.py`

## Historical Or Manual-Only Entrypoints

- `install_nightly_10pm_daemon.sh` / `uninstall_nightly_10pm_daemon.sh`
  Historical system-daemon installer. The current local unattended path is the user LaunchAgent installed by `install_nightly_10pm_launchd.sh`; use the daemon path only for a deliberate sudo/system deployment.
- `build_v26_gold_and_unsup.py` and `pretrain_v26_unsupervised.py`
  Still used as source-data/optional pretrain helpers, but no longer the main nightly objective. Daily promotion is decided by supervised v28c training plus fixed holdout/regression gates.

## Legacy Experiment Scripts

Older `finetune_v*`, `eval_v1*`, and one-off repair/rewrite scripts are retained as historical references or dataset regeneration tools. Do not use them for nightly promotion unless the model plan explicitly says so.

Removed obsolete Phoenix trainers:

- `train_v28_phoenix_finetune.py`
- `train_v28b_phoenix_finetune.py`
