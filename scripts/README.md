# Scripts Guide

This directory contains both current operational scripts and older experiment/build helpers. Prefer the entrypoints below unless you are rebuilding a historical dataset.

The maintained semantic-training inventory is also recorded in `semantic_script_manifest.json`. Tests verify that every script in that manifest still exists and that the current entrypoints remain documented here.

## Current One-Command Entrypoints

Use these first; they are the maintained path for the local semantic model loop.

| task | command |
|------|---------|
| Morning status, latest report, gates, GPU/MPS evidence, review queue | `python3 scripts/nightly_next_morning_triage_v26.py --write-review-csv --markdown-output .nightly/reports/next_morning_triage_$(date +%Y%m%d).md` |
| LaunchAgent health only | `python3 scripts/check_nightly_launchd_v26.py` |
| Latest promotion report only | `python3 scripts/analyze_nightly_report_v26.py` |
| Recent promotion report trend | `python3 scripts/compare_recent_nightly_reports_v26.py --limit 7` |
| Live goal checklist | `python3 scripts/semantic_training_todo_status.py` |
| Semantic script inventory check | `python3 scripts/validate_semantic_script_manifest.py` |
| Manual dry-run of nightly wiring | `NIGHTLY_DRY_RUN=1 NIGHTLY_ENFORCE_FREE_SPACE_CHECK=0 bash scripts/nightly_train_v26.sh` |
| Deployment preflight after promotion | `bash scripts/preflight_v26.sh` |

The normal unattended route is the user LaunchAgent installed by `install_nightly_10pm_launchd.sh`. It runs `nightly_train_v26.sh` at 23:00 with three daily rounds, default GPU/MPS auto selection, supervised v28c training, and CPU retry if auto-device supervised training fails.

## Daily Semantic Model Loop

- `nightly_train_v26.sh`
  Main nightly training loop. Builds data, trains three daily candidate seeds by default, evaluates strict gates, and optionally promotes. The default device mode is `auto` so local GPU/MPS is used when available, with CPU retry for supervised training failures. Promotion reports include per-round actual training sampling stats, including `antonym_mid_rows` and `antonym_mid_examples_after_repeat`.
- `build_nightly_semantic_sets.py`
  Builds the nightly supervised train/eval/calibration files under `.nightly/data/gold/`. Fixed holdout rows are excluded from training and calibration. Antonym rows are normalized to `antonym_mid`, score `50`, range `45-55`, with protected sample weights.
- `train_v28c_mse_contrastive.py`
  Current supervised trainer. The filename is historical; the implementation supports `CoSENTLoss`, `CosineSimilarityLoss`, experimental `OnlineContrastiveLoss` mixed mode, hard-negative boost tags, protected positive/antonym tag boosts, pinned high-value review rows, dedicated midpoint anchors plus a midpoint band loss for `antonym_mid`, and optional multi-angle coverage for high-value rows.
- `eval_v26_gold.py`
  Evaluates model/calibration metrics and emits group metrics plus worst cases, including antonym 40-60 and stricter 45-55 mid-score recall.
- `run_regression_pairs_v23.py`
  Fixed semantic regression gate, including antonym/opposite pairs that must score in the 45-55 semantic range.
- `analyze_nightly_report_v26.py`
  Summarizes the latest non-dry-run promotion report, GPU/MPS evidence, failed gates, regressed groups, and antonym behavior.
- `compare_recent_nightly_reports_v26.py`
  Compares the latest non-dry-run reports in one view so multi-night trends are visible: three-round status, GPU/MPS evidence, best candidate metrics, failed gates, antonym 50% behavior, and CoSENT exclusion sampling.
- `check_nightly_launchd_v26.py`
  Verifies the active macOS LaunchAgent wrapper, three-run config, antonym gate env, current stderr health, and latest scheduled-run/report status.
- `nightly_next_morning_triage_v26.py`
  Preferred next-morning entrypoint. Combines launchd health, latest real-report analysis, device status, failed gates, actual train sampling stats, and optional worst-case review CSV generation.
- `semantic_training_todo_status.py`
  Prints the live goal checklist from `docs/SEMANTIC_TRAINING_TODO.md`, including completed/pending counts and the remaining blocking items.
- `validate_semantic_script_manifest.py`
  Validates `semantic_script_manifest.json`: maintained scripts must exist, removed obsolete trainers must stay absent, and current entrypoints must remain documented in this guide.
- `preflight_v26.sh`
  End-to-end deployment preflight for script inventory, server, regression, and puzzle data.

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

## Cleanup Policy

Do not delete scripts simply because they are not part of the current nightly command. Many older builders and repair scripts are provenance for CSVs that still feed the current training pool. A script is safe to remove only when all of these are true:

- It is not referenced by docs, tests, launchd wrappers, or other scripts.
- Its generated artifacts are not inputs to `build_nightly_semantic_sets.py`.
- It is not needed to reproduce a historical dataset referenced by the current model docs.
- The removal is covered by `python3 -m unittest test.nightly_scripts_test` and the relevant preflight or dry-run command.
