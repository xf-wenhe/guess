# Scripts Guide

This directory contains both current operational scripts and older experiment/build helpers. Prefer the entrypoints below unless you are rebuilding a historical dataset.

## Daily Semantic Model Loop

- `nightly_train_v26.sh`
  Main nightly training loop. Builds data, trains candidates, evaluates gates, and optionally promotes. Default profile is `daily`; use `NIGHTLY_TRAIN_PROFILE=full` for slower three-seed evidence runs.
- `build_nightly_semantic_sets.py`
  Builds the nightly supervised train/eval/calibration files under `.nightly/data/gold/`. Fixed holdout rows are excluded from training and calibration.
- `extract_score_trace_review_candidates.py`
  Converts Flutter `SCORE_TRACE=true` logs into `data/score_trace_review_candidates.csv` for human review.
- `train_v28c_mse_contrastive.py`
  Current supervised trainer. The filename is historical; the implementation supports `CoSENTLoss`, `CosineSimilarityLoss`, experimental `OnlineContrastiveLoss` mixed mode, hard-negative boost tags, protected positive tag boosts, pinned high-value review rows, and optional multi-angle coverage for high-value rows.
- `eval_v26_gold.py`
  Evaluates model/calibration metrics and emits group metrics plus worst cases.
- `run_regression_pairs_v23.py`
  Fixed semantic regression gate.
- `preflight_v26.sh`
  End-to-end deployment preflight for server, regression, and puzzle data.

## Data Quality And Review

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

## Legacy Experiment Scripts

Older `finetune_v*`, `eval_v1*`, and one-off repair/rewrite scripts are retained as historical references or dataset regeneration tools. Do not use them for nightly promotion unless the model plan explicitly says so.

Removed obsolete Phoenix trainers:

- `train_v28_phoenix_finetune.py`
- `train_v28b_phoenix_finetune.py`
