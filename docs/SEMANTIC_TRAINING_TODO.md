# Semantic Training Goal TODO

Last updated: 2026-09-28 CST

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

Overall status: not complete. Real nightlies are running stably again, but no candidate has passed the strict promotion gate yet.

The current blocker is overall no-degrade quality, especially raw bucket accuracy and same-category accuracy. The latest 2026-09-27 real MPS report still failed `acc_ok`, `raw_acc_no_degrade`, and `no_degrade_all`; antonym strict 45-55 remained at `100%`, the eval partition contained no non-holdout antonyms, and regression passed `35/35`.

The 2026-08-21 real run proved that fixed train/calib/eval partitions and fixed capped-row sampling are active across all three MPS rounds. The 2026-09-13 real run then validated the fixed partition (`eval_non_holdout_antonym_rows=0`, `unexpected_train_calib_symmetric_overlap=0`) and the bucket-aware auxiliary objective on all three MPS rounds (`bucket_band_hard_negative_repeat=2`), without changing any promotion threshold or antonym path. The objective improved hard-negative calibration but still allowed raw bucket accuracy and same-category quality to regress. The trainer-side boundary tag set covers evaluator-only `abstract_confusion` and `same_category_weak` families, while keeping `antonym_mid` excluded. Rejected runs retain their small calibration JSON artifacts for curve-level diagnosis while still deleting rejected model directories.

The local promotion-chain audit fixed the best-round recheck so it reads and reports the same strict 45-55 antonym metric as the per-round gate; the 2026-09-13 report showed `100.0 -> 100.0` for both antonym bands. Thresholds and gate predicates are unchanged. The report metadata now also records the top-level relation-calibration profile and interval instead of silently omitting them from the antonym diagnostic.

## Latest Evidence

### 2026-09-15 Real Three-Round MPS Run

Report: `.nightly/reports/nightly_promotion_20260915_230006.md`

The run completed `3/3` supervised v28c rounds on MPS with the fixed partition, `antonym_mid` CoSENT exclusion, midpoint relation calibration, and bucket hard-negative repeat `2`. `eval_non_holdout_antonym_rows=0` in every round, antonym `40-60` plus strict `45-55` stayed `100.0 -> 100.0`, and all three fixed regression runs passed `35/35`. The candidate was still rejected because overall/raw bucket accuracy and the all-group no-degrade gate were not satisfied; `same_category` remained the dominant quality regression while hard-negative MAE improved.

### 2026-09-16 Objective Materialization Audit

The real report records `bucket_band_examples_after_repeat=421`, while the protected round-robin budget consumes only `47 * 8 = 376` examples from that objective. A read-only replay showed that the old materialization path used the global PyTorch RNG, so different model seeds could select different truncated prefixes and drop different `same_category_mid`/hard-negative examples. `materialize_padded_objectives` now uses a dedicated generator derived from the fixed `SEM_SAMPLE_SEED`; local replay confirmed identical effective prefixes for model seeds `20260303`, `20260304`, and `20260305`, without changing the optimizer seed, objective count, steps, or gates. This is a training-side stability fix and still requires the next real MPS report; no local training was started.

### 2026-09-16 Bucket Boundary Preservation Audit

The previous `BucketBandLoss` applied its exact-label center term even when a score was already inside the target bucket. That could move a base-model score across a neighboring boundary while improving pointwise error, which is incompatible with the raw bucket no-degrade gate. The center term now activates only for scores outside the target bucket; in-bucket scores are left to the ordinary cosine objective, while out-of-bucket hard negatives and same-category rows still receive both correction terms. A local unit test covers both paths; this change still needs a real MPS report and does not relax any gate.

### 2026-09-16 Base-Bucket Guard Audit

Read-only baseline inference showed that several fixed-eval same-category pairs started in the correct `40-60` bucket but the rejected candidate moved them below `20`, while hard-negative corrections remained useful. Both the bucket objective and the general cosine objective now record frozen pre-optimization scores for their exact angle-prefixed examples. They add an interior guard when the base score already shares the target bucket; for a base-wrong row, the directional guard only rejects movement farther from the reviewed target bucket, so correction toward the target remains unblocked. `antonym_mid` remains excluded from CoSENT and stays on its dedicated midpoint path. The guard keeps the same five-objective round-robin schedule and all promotion predicates unchanged, and still requires the next real MPS report for validation.

### 2026-09-17 CoSENT Base-Bucket Guard Audit

The 2026-09-16 real run proved that the bucket and cosine guards were active, but the candidate still fell from `68.36%` to `60.94%` raw bucket accuracy and degraded `same_category` calibrated MAE/accuracy from `4.923/76.60%` to `6.893/61.70%`. The remaining mixed schedule included an unguarded CoSENT ranking objective, so its batch-wise ordering could move already-correct base buckets even while the two pointwise objectives were protected. `BaseGuardedCoSENTLoss` now applies the same interior/directional frozen-base guard to that ranking path; `antonym_mid` remains excluded from CoSENT and continues through cosine plus the dedicated midpoint objective. This changes no gate, seed, round, device, or objective budget, and requires the next real MPS report for validation; no local training was started.

### 2026-09-17 Midpoint Materialization Audit

The same real run had `midpoint_examples_after_repeat=370` but a protected budget of `47 * 8 = 376`, so the old unguarded midpoint objective copied 12 real antonym examples to fill its final batch (`round_robin_padded_examples=12`, `round_robin_noop_padded_examples=0`). `MidpointBandLoss` now carries the frozen-base interior/directional guard and is included in the guarded objective set, making those synthetic labels `[NaN, NaN]` no-ops while keeping the same objective count, steps, seeds, device, gates, and midpoint examples. The report chain records midpoint guard counts, and the next real MPS report is required to validate the effect; no local training was started.

### 2026-09-18 Targeted Multi-Angle Coverage Audit

The first real report after the CoSENT and midpoint guards proved those guards were active and kept antonym `40-60`/strict `45-55` at `100%`, but raw bucket accuracy remained `60.94%` versus the base `68.36%`, with the largest same-category misses in the `40-60` and `60-80` target buckets. A read-only replay of the exact capped selection found that every selected `same_category_mid` row in those buckets had only two angle-prefixed copies, while evaluation averages five angle scores. The nightly shell and direct trainer defaults now require `same_category_mid@40-59:5,same_category_mid@60-79:5`; this is targeted coverage, not the disabled global high-value five-angle mode, and does not change the round-robin budget or any gate. The next real MPS report is required to validate the effect; no local training was started.

### 2026-09-20 Same-Category Boundary Follow-Up

The 2026-09-19 real report confirmed that the preceding two-bucket fix was active (`tag_bucket_angle_repeat_rows=24/14`) but did not remove the remaining candidate failures: `same_category` calibrated MAE/accuracy regressed from `4.923/76.60%` to `6.792/61.70%`, and the largest bucket miss cluster was still `same_category_mid` in the `20-40` target bucket. The same report also retained high-score `same_category_but_far` false positives (`飞机->轮船`, `猫->狗`, `医生->老师`). The daily and direct trainer defaults now add five-angle coverage for `same_category_mid@20-39` and `same_category_but_far@20-39`, without changing the three-round MPS path, fixed partition, antonym exclusion, objective budget, or promotion gates. The report still proves `eval_non_holdout_antonym_rows=0`, antonym `40-60`/strict `45-55` at `100%`, and regression `35/35`; the next real report is required, and no local training was started.

### 2026-09-23 Real Report and Evaluator-Aligned Guard

The complete 2026-09-22 real report completed all three MPS rounds with `NIGHTLY_SUP_COSENT_EXCLUDE_TAGS=antonym_mid`, `eval_non_holdout_antonym_rows=0`, antonym `40-60`/strict `45-55` at `100%`, and regression `35/35`. The remaining failures were `acc_ok`, `raw_acc_no_degrade`, and `no_degrade_all`; the candidate improved calibrated MAE and hard-negative metrics but still moved same-category and raw bucket scores across boundaries. The trainer guard previously classified each angle independently even though evaluation uses a five-angle trimmed mean. The local fix now freezes that evaluator-aligned aggregate and adds a small teacher anchor only for base-correct buckets, while preserving directional movement for base-wrong rows and all existing gates, seeds, rounds, MPS path, and holdout partition. No local training was started; the next complete real report is required to validate the change.
### 2026-09-24 Local Same-Category Isolation

The latest available real report, `.nightly/reports/nightly_promotion_20260923_230005.md`,
completed all three MPS rounds with `antonym_mid` CoSENT exclusion, no non-holdout
eval antonyms, antonym `40-60`/strict `45-55` at `100.0`, and regression `35/35`.
The remaining failures were `acc_ok`, `raw_acc_no_degrade`, and `no_degrade_all`.
A read-only replay showed that `same_category_but_far` was entering the CoSENT,
absolute cosine, and bucket paths together. The local fix makes it bucket-only by
default (`NIGHTLY_SUP_BUCKET_ONLY_TAGS=same_category_but_far`) and adds explicit
per-objective exclusion counts. This changes no gate, partition, round count,
device policy, or antonym path. No local training was started; the next real
MPS report is required before judging whether the candidate can pass.

### 2026-09-25 Real Report and Triage Accounting

Report: `.nightly/reports/nightly_promotion_20260924_230004.md`

The scheduled run completed all three supervised v28c rounds on MPS. Each round
reported `same_category_but_far` as bucket-only: 13 rows / 65 repeated examples,
excluded from CoSENT, cosine regression, and contrastive mining while retained
in the bucket objective. Partition evidence remained clean
(`eval_non_holdout_antonym_rows=0`), antonym `40-60` and strict `45-55` remained
at `100.0`, and regression passed `35/35`.

The candidate improved calibrated MAE by `1.254` and calibrated bucket accuracy
by `1.172` points, below the unchanged `2.0`-point requirement. Raw bucket
accuracy fell `7.422` points. `same_category` calibrated accuracy fell `10.64`
points and MAE worsened by `1.688`; `hard_negative` calibrated accuracy improved
`5.217` points and MAE improved by `3.459`. `synonym_alias` accuracy and recall
stayed at `100%`, but calibrated MAE worsened by `0.0049`. The remaining gates
are real quality failures, not a partition or reporting artifact.

The first triage pass exposed a separate accounting bug: objective sample totals
did not include the new bucket-only exclusions. The validator now reconciles
objective examples, explicit tag exclusions, and bucket-only exclusions, and the
recent-report comparison shows the bucket-only counts. These diagnostics pass on
the latest report; candidate promotion gates remain unchanged and still fail.
No training was started locally. The next scheduled MPS report is needed to
evaluate any further trainer change.

### 2026-09-27 Persistent Same-Category Regression

Report: `.nightly/reports/nightly_promotion_20260926_230005.md`

The latest report again completed all three supervised v28c rounds on MPS.
`same_category_but_far` remained isolated at 13 rows / 65 repeated examples,
but the candidate still failed `acc_ok`, `raw_acc_no_degrade`, and
`no_degrade_all`; calibrated bucket accuracy improved only 1.172 points against
the unchanged 2.0-point requirement, and raw bucket accuracy fell 7.422 points.
Same-category calibrated accuracy fell 10.64 points and MAE worsened by 1.688.
Hard-negative MAE/accuracy improved. Synonym/alias recall and accuracy stayed at
`100%`, while calibrated MAE worsened slightly (`0.010582` to `0.015504`);
antonym `40-60` and strict `45-55` stayed at `100%`, and the fixed regression
set passed (`35/35`). Eval still contained only the fixed holdout antonym
(`eval_non_holdout_antonym_rows=0`).

The report lists 44 selected `same_category_mid` rows, while the configured
bucket-only set still contained only `same_category_but_far`; source inspection
confirmed mid-band rows therefore continued into CoSENT/cosine as well as the
bucket objective. The local follow-up now makes both same-category tags
bucket-only, retaining them in the evaluator-aligned bucket objective and
excluding them from CoSENT, cosine regression, and contrastive mining. This
does not change any gate, partition, round count, device policy, or antonym
path. No training was started; a later real MPS report is required to validate
quality, and the strict gates remain pending.

### 2026-09-28 Real Report and Mid-Band Isolation Rollback

Report: `.nightly/reports/nightly_promotion_20260927_230004.md`

The scheduled candidate used `same_category_but_far,same_category_mid` as
bucket-only and completed all three rounds on MPS without CPU fallback. The
antonym split remained correct (`eval_non_holdout_antonym_rows=0` in every
round), strict `45-55` and `40-60` recall stayed at `100%`, and regression
passed `35/35`. The candidate still failed `acc_ok`, `raw_acc_no_degrade`, and
`no_degrade_all`.

Compared with the preceding three reports on identical fixed data/seeds,
excluding `same_category_mid` from continuous objectives reduced CoSENT examples
from `556` to `342` and cosine examples from `741` to `527`. Same-category
calibrated accuracy fell further from `65.96%` to `61.70%`, while its MAE
worsened from `6.611` to `7.111`. Synonym/alias calibrated MAE increased from
`0.0155` to `0.0833` despite recall and bucket accuracy remaining `100%`.
Hard-negative MAE/accuracy improved, but the gains did not compensate for the
same-category and overall bucket regressions. The mid-band bucket-only default
has therefore been rolled back; those rows again retain CoSENT/cosine pointwise
supervision in addition to the bucket objective. This is evidence against the
broader routing change, not proof that the strict global gates now pass. No
training was started locally; the next scheduled real MPS report must test the
rollback before any further adjustment.

### 2026-09-13 Real Three-Round MPS Run

Report: `.nightly/reports/nightly_promotion_20260913_230005.md`

The run completed `3/3` supervised v28c rounds on MPS with `NIGHTLY_SUP_COSENT_EXCLUDE_TAGS=antonym_mid`. The fixed holdout was the only eval antonym row in every round, and antonym `40-60` plus strict `45-55` recall stayed `100.0 -> 100.0`. The candidate still failed strict promotion because raw bucket accuracy/no-degrade and one round's regression gate were not yet stable; the current evaluator recheck makes the saved r1/r2 regression artifacts `35/35` after the related-midband continuity fix.

The subsequent 2026-09-14 run produced only a partial r3 artifact and no promotion report. No local training is to be started while waiting for the next complete real report.

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

Root cause for the wrong scale: the real 23:00 launchd job was still executing the stale copied script at `~/.guess_nightly/nightly_train_v26.sh`, whose daily default was `sup_rows=2500`, `sup_batch=16`. Manual dry-run from the repo had already shown the new `300/8` defaults, but launchd was not using that repo script.

### 2026-06-05 and 2026-06-06 Launchd Attempts

No real nightly promotion reports were produced after the 2026-06-04 run. The launchd stderr log shows:

```text
/bin/bash: /Volumes/新/work/flutter/guess/.nightly/nightly_launcher.sh: Operation not permitted
```

Result: no training started. The installed job was pointed at a wrapper under the external project volume's `.nightly/` directory, which launchd could not execute. The installer now writes the launchd wrapper to `$HOME/.guess_nightly/nightly_launcher.sh`; that wrapper `cd`s into `/Volumes/新/work/flutter/guess` and execs the current repo script, avoiding the stale copied training script and the external-volume wrapper restriction.

### 2026-07-17 through 2026-07-19 Real Nightlies

Reports:

- `.nightly/reports/nightly_promotion_20260717_230005.md`
- `.nightly/reports/nightly_promotion_20260718_230000.md`
- `.nightly/reports/nightly_promotion_20260719_230005.md`

All three real runs completed `3/3` rounds on `device=mps`, used `antonym_mid:45`, and proved the current supervised strategy in the report output: `sup_cosent_exclude_tags=antonym_mid`, `sup_midpoint_tags=antonym_mid`, `calib_support_low=60`.

Antonym strict behavior is now stable again in real runs:

| report | antonym cal_mae | antonym acc | strict 45-55 |
|--------|------------------|-------------|--------------|
| 20260717_230005 | 0.9645 -> 3.9364 | 100.0 -> 100.0 | 100.0 -> 100.0 |
| 20260718_230000 | 0.9645 -> 2.8240 | 100.0 -> 100.0 | 100.0 -> 100.0 |
| 20260719_230005 | 0.9645 -> 3.2784 | 100.0 -> 100.0 | 100.0 -> 100.0 |

Result: rejected. The remaining failures moved to global gates and bucket-shift quality, not antonym rollback. The latest real report (`20260719_230005`) failed:

- `mae_ok`
- `acc_ok`
- `raw_mae_no_degrade`
- `raw_acc_no_degrade`
- `cal_acc_no_degrade`
- `no_degrade_all`

The repeated error families in the latest real report are:

- `same_category`: `74.42 -> 58.14` bucket accuracy
- `hard_negative`: many `0-20 -> 40-60` and `20-40 -> 60-80` overshoots such as `飞机->轮船`, `老虎->大象`
- `synonym_alias`: many `80-100 -> 60-80` under-shoots such as `诸葛亮->卧龙`, `孔明->诸葛亮`

## Active TODO

- [x] Fix CPU fallback so `SEM_DEVICE=cpu` does not accidentally use MPS through Trainer/Accelerate.
- [x] Verify explicit CPU Trainer with a tiny CPU-only training probe.
- [x] Run `mixed_contrastive` micro-smoke to test hard-negative direction.
- [x] Add selective contrastive scope so hard-negative margin training avoids ambiguous same-category rows by default.
- [x] Re-run selective `mixed_contrastive` micro-smoke to check whether bucket accuracy damage is reduced.
- [x] Read the 2026-06-11 nightly report and analyze gates/device/three-round stability.
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
- [x] Add strict nightly promotion gate for antonym 45-55 recall no-degrade.
- [x] Boost normalized antonym training rows so the 50% policy is represented under the 300-row daily cap.
- [x] Add trainer stats for antonym row/repeat coverage.
- [x] Add minimum daily sampling quota for `antonym_mid` so strict 45-55 examples are not underrepresented.
- [x] Write per-round trainer sampling stats into nightly promotion reports so `antonym_mid:45` can be verified without digging through launchd logs.
- [x] Parse and display trainer sampling stats in next-morning triage so antonym quota evidence appears in the one-command report.
- [x] Add nightly report sections for run config, gate thresholds, regression gate, and device log excerpt.
- [x] Add `scripts/analyze_nightly_report_v26.py` to summarize the latest real report, skipping dry-runs by default.
- [x] Extend nightly report analysis to list failed gates and regressed metric groups for faster next-day tuning.
- [x] Add `scripts/extract_nightly_worst_case_review_candidates.py` so rejected-report worst cases become pending review rows for the next high-value training patch.
- [x] Diagnose why 2026-06-05 and 2026-06-06 did not produce reports: launchd could not execute the `.nightly/` wrapper due `Operation not permitted`.
- [x] Change launchd install/uninstall scripts to use `$HOME/.guess_nightly/nightly_launcher.sh`, while the wrapper still execs the current repo `scripts/nightly_train_v26.sh`.
- [x] Reinstall launchd with the HOME wrapper and verify the loaded plist plus HOME-wrapper dry-run.
- [x] Add `scripts/check_nightly_launchd_v26.py` to distinguish current launchd install health from historical stderr failures.
- [x] Extend launchd health check with latest-scheduled-run detection so missed 23:00 runs are visible the next morning.
- [x] Treat a post-23:00 `nightly_train_v26_*.log` as an in-progress/started run so long three-round nightlies are not mislabeled as missed before the report is written.
- [x] Add `scripts/nightly_next_morning_triage_v26.py` as the one-command next-morning check for launchd health, missed schedules, report analysis, device status, failed gates, and optional worst-case review CSV generation.
- [x] Flag fatal-looking launchd stderr written after the current install, while keeping older stderr as historical warnings.
- [x] Add optional Markdown output to next-morning triage for saved report comparisons.
- [x] Archive existing launchd stdout/stderr logs during install so tonight's logs start clean while old failure evidence is preserved as `.bak`.
- [x] Add calibrated bucket-confusion summaries to nightly diagnostics so repeated bucket-boundary failures are visible without manually reading metric JSON.
- [x] Add `relation_tag` and group summaries to bucket-confusion diagnostics so repeated bucket shifts point at a fixable data family.
- [x] Convert bucket-confusion examples into pending review candidates, with bucket-midpoint temporary scores and no training consumption until review approval.
- [x] Add review queue source/status/severity summaries to next-morning triage so high-priority pending rows are visible immediately.
- [x] Add review candidate validation so approved/merged rows cannot silently enter training with invalid scores, invalid statuses, duplicate pairs, or non-50 antonyms.
- [x] Run review candidate validation from next-morning triage so unsafe approved/merged rows are visible before the next training build.
- [x] Verify the 2026-06-11 real nightly used the 300-row, three-round daily default on MPS.
- [x] Consolidate the maintained semantic/nightly script entrypoints in `scripts/README.md` so daily operation does not depend on guessing among legacy scripts.
- [x] Add `scripts/semantic_script_manifest.json` and tests so the maintained semantic script inventory is machine-checkable before future cleanup.
- [x] Add `scripts/validate_semantic_script_manifest.py` so the semantic script inventory can be checked without remembering a unit-test name.
- [x] Run the semantic script inventory validator from `scripts/preflight_v26.sh` so deployment checks cover script cleanup drift.
- [x] Read the 2026-06-12 through 2026-06-14 real nightly reports and verify they ran three MPS/GPU rounds with `antonym_mid:45` actually sampled.
- [x] Change the default mixed supervised objective so `antonym_mid` stays in cosine regression but is excluded from CoSENT ranking.
- [x] Show CoSENT exclusion counts in analyzer and next-morning triage so the next report proves the new antonym objective path.
- [x] Add a behavior test proving `antonym_mid` remains in overall/cosine training examples but is removed from CoSENT examples.
- [x] Add next-morning strategy checks so reports after the new install must prove `antonym_mid` was excluded from CoSENT.
- [x] Make next-morning triage fail with `semantic_strategy_failed` if a fresh report does not prove the CoSENT antonym exclusion strategy.
- [x] Add a recent-report comparison command so several real nightlies can be checked together for GPU/MPS, three-round stability, failed gates, antonym 50% behavior, and CoSENT exclusion evidence.
- [x] Isolate `same_category_but_far` to the evaluator-aligned bucket/base-guard path without weakening gates; wait for the next real MPS report before marking the quality blocker complete.
- [x] Make next-morning triage report `waiting_for_next_real_strategy_report` when the latest real report predates the newly installed strategy.
- [x] Keep train/calib/eval data partitioning fixed across multi-round nightly seeds while preserving each round's independent training seed.
- [x] Keep the supervised capped-row sample fixed across rounds via `SEM_SAMPLE_SEED`, while preserving per-round model/training randomness via `SEM_SEED`.
- [x] Reject non-holdout `antonym_mid` rows in eval and report holdout/non-holdout antonym counts explicitly.
- [x] Validate the fixed-partition change against the 2026-09-13 real nightly report; do not start a local training run.
- [x] Wait for the next real nightly report to verify `NIGHTLY_SUP_MIDPOINT_TAGS=antonym_mid` plus CoSENT exclusion recovers strict 45-55 antonym behavior.
- [x] Add a bucket-aware boundary loss for selected hard-negative and same-category rows while excluding `antonym_mid`.
- [x] Align the bucket-aware trainer tags with evaluator hard-negative families (`abstract_confusion` and `same_category_weak`).
- [x] Retain rejected candidate calibration artifacts so regression/calibration coupling can be audited after the nightly cleanup.
- [x] Make the best-round promotion recheck read/report strict antonym 45-55 metrics instead of relying on an undefined local value.
- [ ] Isolate and reduce the latest real-nightly bucket regressions in `same_category`, `hard_negative`, and `synonym_alias` without weakening the promotion gates.
- [x] Reconcile bucket-only exclusions in next-morning strategy accounting and display their counts in recent-report comparisons.
- [x] Validate the bucket-aware objective against the 2026-09-13 real three-round MPS report; it improved hard-negative calibration but did not satisfy the strict global gates; do not start a local training run.
- [ ] Re-run smoke after tuning.
- [ ] If smoke passes, run daily/full profile with multiple seeds.
- [ ] Promote only after strict gates pass.

## Next Candidate Ideas

1. Reduce contrastive strength.
   Current implementation: `SEM_CONTRASTIVE_SCOPE=selective` applies contrastive positives only to clear high-positive tags and negatives only to hard-negative tags. Next experiment should compare it against the rejected all-scope run.

2. Preserve raw bucket quality while keeping the bucket-aware objective.
   `BucketBandLoss` was validated in the 2026-09-13 three-round MPS run and improved hard-negative calibration, but raw bucket accuracy and same-category no-degrade are not stable yet. The next change must be validated by another real report.

3. Improve calibration/reporting further.
   Per-bucket confusion summaries now include top `relation_tag`/group counts and can be converted into pending review candidates. Next reporting step, if needed, is to auto-cluster repeated pairs across multiple rejected reports.

4. Keep default nightly on `mixed`.
   `mixed_contrastive` is not safe as the daily default yet.
