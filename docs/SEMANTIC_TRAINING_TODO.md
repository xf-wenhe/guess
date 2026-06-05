# Semantic Training Goal TODO

Last updated: 2026-06-05 10:44 CST

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
- [x] Nightly daily runs use three seeds by default.
- [x] Antonym/opposite pairs train and check as 50% semantic relatedness, not low-score hard negatives.
- [ ] At least one real candidate passes strict gates:
  - calibrated MAE improves enough
  - calibrated bucket accuracy improves enough
  - hard-negative subset does not degrade
  - synonym/alias recall does not degrade
  - antonym mid-score recall does not degrade
  - fixed regression pairs all pass, including antonym pairs at 45-55
- [ ] A multi-seed or daily/full profile run proves the improvement is stable.
- [ ] The passing candidate is promoted only after gates pass.
- [ ] `bash scripts/preflight_v26.sh` passes after promotion.

## Current Status

Overall status: not complete. Waiting for the next real nightly run after fixing the launchd entrypoint.

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
| regression | - | 30/30 legacy |

Result: rejected. Improvement was too small, and hard-negative MAE slightly degraded.

### Mixed Contrastive Experiment

Report: `.nightly/reports/nightly_promotion_20260602_151414.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.2732 |
| cal_bucket_acc | 68.13 | 65.93 |
| hard_negative_cal_mae | 9.4009 | 8.8575 |
| regression | - | 30/30 legacy |

Result: rejected. `mixed_contrastive` improves MAE and hard negatives, but hurts bucket accuracy, same-category, and synonym bucket accuracy. It should remain experimental until the contrastive objective is weakened or made more selective.

### Selective Mixed Contrastive Experiment

Report: `.nightly/reports/nightly_promotion_20260602_153608.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.3945 |
| cal_bucket_acc | 68.13 | 66.67 |
| hard_negative_cal_mae | 9.4009 | 8.6388 |
| regression | - | 30/30 legacy |

Result: rejected. Selective contrastive reduced the all-scope bucket damage (`65.93 -> 66.67`) and improved hard negatives further, but still hurt bucket accuracy, same-category, and synonym bucket accuracy. It should stay experimental.

### 2026-06-03 Nightly Daily Run

Report: `.nightly/reports/nightly_promotion_20260603_230006.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.7946 |
| cal_bucket_acc | 68.13 | 65.93 |
| hard_negative_cal_mae | 9.4009 | 9.6486 |
| synonym_recall_at70 | 93.22 | 89.83 |
| regression | - | 30/30 legacy |

Result: rejected. The previous daily default used 2500 rows, batch 16, `mixed` loss, and MPS. It took 306.5 minutes and degraded key gates. Daily has been changed to a high-signal 300-row cap with batch 8; larger runs should stay in `full` or explicit experiments until proven.

### 2026-06-04 Nightly Daily Run

Report: `.nightly/reports/nightly_promotion_20260604_230005.md`

| metric | baseline | candidate |
|--------|----------|-----------|
| cal_mae | 7.4838 | 7.5320 |
| cal_bucket_acc | 68.13 | 66.67 |
| hard_negative_cal_mae | 9.4009 | 9.2043 |
| synonym_recall_at70 | 93.22 | 94.92 |
| same_category_cal_mae | 7.3649 | 8.3971 |
| regression | - | 30/30 legacy |

Result: rejected. It ran on `device=mps` and used only 1 round, not the three-seed `full` profile. The failure was global quality: calibrated MAE worsened by `0.0481`, bucket accuracy fell by `1.46` points, and same-category cases degraded even though hard negatives and synonym recall improved.

Root cause for the wrong scale: the real 23:00 launchd job was still executing the stale copied script at `~/.guess_nightly/nightly_train_v26.sh`, whose daily default was `sup_rows=2500`, `sup_batch=16`. Manual dry-run from the repo had already shown the new `300/8` defaults, but launchd was not using that repo script. The launchd job has been reinstalled and now points to `.nightly/nightly_launcher.sh`, which execs `/Volumes/新/work/flutter/guess/scripts/nightly_train_v26.sh`.

## Active TODO

- [x] Fix CPU fallback so `SEM_DEVICE=cpu` does not accidentally use MPS through Trainer/Accelerate.
- [x] Verify explicit CPU Trainer with a tiny CPU-only training probe.
- [x] Run `mixed_contrastive` micro-smoke to test hard-negative direction.
- [x] Add selective contrastive scope so hard-negative margin training avoids ambiguous same-category rows by default.
- [x] Re-run selective `mixed_contrastive` micro-smoke to check whether bucket accuracy damage is reduced.
- [ ] User reviews the latest reports and chooses the next experiment direction.
- [x] Read the 2026-06-03 nightly report and change daily defaults away from the regressing 2500-row run.
- [x] Read the 2026-06-04 nightly report and confirm it still used the stale 2500-row launchd script.
- [x] Reinstall launchd so the 23:00 job executes the current repo script.
- [x] Dry-run the updated launchd wrapper and confirm `sup_rows=300`, `sup_batch=8`.
- [x] Change daily nightly default and launchd install config to three rounds.
- [x] Normalize antonym training/check rows to `antonym_mid`, `45-55`, `50`.
- [x] Verify generated nightly train/calib/eval/pool files contain only normalized antonym rows.
- [x] Add fixed regression antonym pairs with target range `45-55`.
- [x] Record current production regression baseline after antonym checks: `31/35`, antonym `1/5`.
- [x] Fix nightly promotion gates to require `passed == total`, not the old hard-coded `30`.
- [x] Add code-level fallback for required antonym regression pairs and train patches so ignored local data files cannot silently drop the new policy.
- [x] Add nightly promotion gate for antonym 40-60 recall no-degrade.
- [x] Add nightly report sections for run config, gate thresholds, regression gate, and device log excerpt.
- [x] Add `scripts/analyze_nightly_report_v26.py` to summarize the latest real report, skipping dry-runs by default.
- [x] Extend nightly report analysis to list failed gates and regressed metric groups for faster next-day tuning.
- [x] Add `scripts/extract_nightly_worst_case_review_candidates.py` so rejected-report worst cases become pending review rows for the next high-value training patch.
- [ ] Wait for the next real nightly report to verify the new 300-row, three-round daily default.
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
