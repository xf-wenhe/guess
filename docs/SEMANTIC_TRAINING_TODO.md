# Semantic Training Goal TODO

Last updated: 2026-06-02 15:49 CST

Goal: make the local semantic model's daily/nightly training produce substantial, verified improvements for the Chinese guessing game.

## Completion Criteria

This goal is complete only when all items below are proven by current repo state and command output:

- [x] Nightly training defaults to GPU/auto when available.
- [x] MPS/CUDA failures have an automated CPU fallback path.
- [x] Supervised v28c training is the main nightly path, not weak unsupervised hint-pair training.
- [x] Real reviewed failures can enter the train-only pool.
- [x] Train-only patches are excluded from calib/eval/holdout.
- [x] Fixed eval, group metrics, bucket miss diagnostics, regression checks, and reports are generated.
- [x] Isotonic calibration is implemented and verified against the production baseline.
- [ ] At least one real candidate passes strict gates:
  - calibrated MAE improves enough
  - calibrated bucket accuracy improves enough
  - hard-negative subset does not degrade
  - synonym/alias recall does not degrade
  - 30 regression pairs pass
- [ ] A multi-seed or daily/full profile run proves the improvement is stable.
- [ ] The passing candidate is promoted only after gates pass.
- [ ] `bash scripts/preflight_v26.sh` passes after promotion.

## Current Status

Overall status: not complete. Paused for user analysis before any further experiments.

The pipeline is much stronger and safer than before, but no candidate has passed the strict promotion gate yet.

## Latest Evidence

### Isotonic Calibration

Production baseline on the fixed nightly eval split improved from the old quantile-mean calibration:

| calibration | cal_mae | cal_bucket_acc |
|-------------|---------|----------------|
| legacy quantile mean | 7.7257 | 67.03 |
| isotonic | 7.4838 | 68.13 |

This is a scoring/calibration improvement, not a model promotion.

### Best Mixed-Loss Candidate So Far

Report: `.nightly/reports/nightly_promotion_20260602_130457.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.4432 |
| cal_bucket_acc | 68.13 | 68.50 |
| regression | - | 30/30 |

Result: rejected. Improvement was too small, and hard-negative MAE slightly degraded.

### Mixed Contrastive Experiment

Report: `.nightly/reports/nightly_promotion_20260602_151414.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.2732 |
| cal_bucket_acc | 68.13 | 65.93 |
| hard_negative_cal_mae | 9.4009 | 8.8575 |
| regression | - | 30/30 |

Result: rejected. `mixed_contrastive` improves MAE and hard negatives, but hurts bucket accuracy, same-category, and synonym bucket accuracy. It should remain experimental until the contrastive objective is weakened or made more selective.

### Selective Mixed Contrastive Experiment

Report: `.nightly/reports/nightly_promotion_20260602_153608.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.3945 |
| cal_bucket_acc | 68.13 | 66.67 |
| hard_negative_cal_mae | 9.4009 | 8.6388 |
| regression | - | 30/30 |

Result: rejected. Selective contrastive reduced the all-scope bucket damage (`65.93 -> 66.67`) and improved hard negatives further, but still hurt bucket accuracy, same-category, and synonym bucket accuracy. It should stay experimental.

## Active TODO

- [x] Fix CPU fallback so `SEM_DEVICE=cpu` does not accidentally use MPS through Trainer/Accelerate.
- [x] Verify explicit CPU Trainer with a tiny CPU-only training probe.
- [x] Run `mixed_contrastive` micro-smoke to test hard-negative direction.
- [x] Add selective contrastive scope so hard-negative margin training avoids ambiguous same-category rows by default.
- [x] Re-run selective `mixed_contrastive` micro-smoke to check whether bucket accuracy damage is reduced.
- [ ] User reviews the latest reports and chooses the next experiment direction.
- [ ] Re-run smoke after tuning.
- [ ] If smoke passes, run daily/full profile with multiple seeds.
- [ ] Promote only after strict gates pass.

## Next Candidate Ideas

1. Reduce contrastive strength.
   Current implementation: `SEM_CONTRASTIVE_SCOPE=selective` applies contrastive positives only to clear high-positive tags and negatives only to hard-negative tags. Next experiment should compare it against the rejected all-scope run.

2. Add a bucket-aware objective.
   The current losses improve continuous MAE but can move samples across bucket boundaries in the wrong direction.

3. Improve calibration/reporting further.
   Add per-bucket confusion summaries so the next patches target bucket-boundary errors instead of only largest absolute errors.

4. Keep default nightly on `mixed`.
   `mixed_contrastive` is not safe as the daily default yet.
