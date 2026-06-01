# Semantic Nightly Training

This document describes the current local semantic model training pipeline for the Chinese guessing game.

## Primary Entrypoints

- `scripts/nightly_train_v26.sh`
  Runs the full nightly loop: build training/eval sets, train candidates, evaluate, gate, optionally promote.
- `scripts/build_nightly_semantic_sets.py`
  Builds the nightly supervised train CSV, larger gold pool, calibration split, holdout split, and optional unsupervised pairs under `.nightly/`.
- `scripts/train_v28c_mse_contrastive.py`
  Current supervised trainer. Despite the historical filename, it now uses SentenceTransformers `CoSENTLoss`; sample weights and hard negatives are represented by bounded repeat sampling.
- `scripts/eval_v26_gold.py`
  Evaluates a model with multi-angle scoring, writes calibration, and reports overall metrics, group metrics, and worst cases.
- `scripts/run_regression_pairs_v23.py`
  Runs the fixed 30-pair regression suite used as a promotion gate.

## Default Nightly Behavior

By default, nightly training uses automatic device selection. If CUDA is available it will use CUDA; on Apple Silicon it will use MPS; otherwise it falls back to CPU.

Override device selection when needed:

```bash
NIGHTLY_SEM_DEVICE=cpu bash scripts/nightly_train_v26.sh
NIGHTLY_SEM_DEVICE=mps bash scripts/nightly_train_v26.sh
SEM_DEVICE=cpu bash scripts/nightly_train_v26.sh
```

The default training path is supervised v28c:

```bash
NIGHTLY_ENABLE_SUPERVISED_FINETUNE=1
NIGHTLY_ENABLE_UNSUP_PRETRAIN=0
NIGHTLY_ENABLE_ANCHOR_FINETUNE=0
```

Unsupervised pretraining remains available as an optional stage:

```bash
NIGHTLY_ENABLE_UNSUP_PRETRAIN=1 bash scripts/nightly_train_v26.sh
```

## Recommended Commands

Use a small real smoke before changing defaults or labels. This exercises the actual model, GPU/auto device selection, training, evaluation, gates, and report generation without promoting:

```bash
NIGHTLY_AUTO_PROMOTE=0 \
NIGHTLY_TOTAL_RUNS=1 \
NIGHTLY_ENFORCE_FREE_SPACE_CHECK=0 \
NIGHTLY_SUP_MAX_TRAIN_ROWS=300 \
NIGHTLY_SUP_EPOCHS=1 \
bash scripts/nightly_train_v26.sh
```

Run the full evidence-producing nightly after the smoke succeeds:

```bash
NIGHTLY_AUTO_PROMOTE=0 bash scripts/nightly_train_v26.sh
```

Turn promotion back on only after the report shows real holdout improvement:

```bash
NIGHTLY_AUTO_PROMOTE=1 bash scripts/nightly_train_v26.sh
```

## Data Flow

1. `build_nightly_semantic_sets.py` reads:
   - `data/train_v28c_balanced.csv`
   - `data/manual_similarity_overrides.json`
   - `data/semantic_scoring_user_input_template.csv`
   - reviewed error/holdout CSVs when present
   - `assets/puzzles.json`
2. It writes nightly artifacts under `.nightly/data/gold/`:
   - `train_v28c_nightly.csv`
   - `gold_v26_pool.csv`
   - `gold_v26_calib.csv`
   - `gold_v26_eval.csv`
   - `unsupervised_pairs_v26.jsonl`
3. `train_v28c_mse_contrastive.py` trains a candidate from the current project model.
4. `eval_v26_gold.py` evaluates baseline and candidate on the same nightly holdout.
5. `nightly_train_v26.sh` promotes only if all gates pass.

## Promotion Gates

Defaults:

- calibrated MAE improves by at least `0.3`
- bucket accuracy improves by at least `2.0` points
- raw and calibrated metrics do not degrade
- hard-negative group MAE does not degrade
- synonym/alias recall does not degrade
- 30-pair regression passes

Useful overrides:

```bash
NIGHTLY_MIN_MAE_IMPROVEMENT=0.2
NIGHTLY_MIN_ACC_IMPROVEMENT=1.0
NIGHTLY_REQUIRE_NO_DEGRADE_ALL=0
NIGHTLY_AUTO_PROMOTE=0
```

## Reports

Nightly reports are written to:

```text
.nightly/reports/nightly_promotion_*.md
```

Reports include per-round metrics, project-vs-candidate metrics, group metrics, and the candidate's largest holdout errors. Review the worst cases first when adding new labels.

Rejected candidates also write diagnostics. A failed nightly is still useful: use the rejected candidate's worst cases to add or correct labels before the next run.

## Script Cleanup Notes

The old Phoenix trainers `train_v28_phoenix_finetune.py` and `train_v28b_phoenix_finetune.py` were removed because the nightly flow now uses `train_v28c_mse_contrastive.py`.

Retained legacy/data-builder scripts are still useful for rebuilding source datasets:

- `scripts/build_v28_phoenix_train_csv.py`
- `scripts/build_v28c_balanced_train.py`
- `scripts/build_v28_*`
- older `finetune_v*` scripts used as historical references

Do not delete these unless their generated datasets are replaced and references in docs/tests are updated.
