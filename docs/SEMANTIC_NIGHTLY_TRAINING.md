# Semantic Nightly Training

This document describes the current local semantic model training pipeline for the Chinese guessing game.

For the live completion checklist, see `docs/SEMANTIC_TRAINING_TODO.md`.

## Primary Entrypoints

- `scripts/nightly_train_v26.sh`
  Runs the full nightly loop: build training/eval sets, train candidates, evaluate, gate, optionally promote.
- `scripts/build_nightly_semantic_sets.py`
  Builds the nightly supervised train CSV, larger gold pool, calibration split, holdout split, and optional unsupervised pairs under `.nightly/`.
- `scripts/extract_score_trace_review_candidates.py`
  Converts Flutter `[score_trace]` logs into a review CSV so real high-score false positives and low-score false negatives can be approved into the nightly training pool.
- `scripts/train_v28c_mse_contrastive.py`
  Current supervised trainer. Despite the historical filename, it now uses SentenceTransformers standard losses; sample weights and hard negatives are represented by bounded repeat sampling.
- `scripts/eval_v26_gold.py`
  Evaluates a model with multi-angle scoring, writes calibration, and reports overall metrics, group metrics, and worst cases.
- `scripts/run_regression_pairs_v23.py`
  Runs the fixed regression suite used as a promotion gate, including required antonym pairs checked at semantic 45-55.
- `scripts/analyze_nightly_report_v26.py`
  Reads the latest non-dry-run report and matching log, then summarizes three-round status, device/GPU evidence, best round, failed gates, regressed metric groups, and antonym behavior.
- `scripts/extract_nightly_worst_case_review_candidates.py`
  Converts the report's worst-case table into a pending review CSV. Approved rows are consumed by the next nightly build.

## Default Nightly Behavior

By default, nightly training uses automatic device selection. If CUDA is available it will use CUDA; on Apple Silicon it will use MPS; otherwise it falls back to CPU.

If supervised training fails while device selection is `auto`, the nightly script retries that training stage once with `SEM_DEVICE=cpu`. This keeps unattended runs from losing the whole night to transient MPS/Metal failures.

The CPU path also sets `ACCELERATE_USE_CPU=true` and the supervised trainer uses an explicit CPU `SentenceTransformerTrainer` path. This is required because `SentenceTransformer.fit()` / Accelerate can otherwise still touch MPS even when `SEM_DEVICE=cpu`.

Override device selection when needed:

```bash
NIGHTLY_SEM_DEVICE=cpu bash scripts/nightly_train_v26.sh
NIGHTLY_SEM_DEVICE=mps bash scripts/nightly_train_v26.sh
SEM_DEVICE=cpu bash scripts/nightly_train_v26.sh
```

The default training path is supervised v28c:

```bash
NIGHTLY_TRAIN_PROFILE=daily
NIGHTLY_ENABLE_SUPERVISED_FINETUNE=1
NIGHTLY_ENABLE_UNSUP_PRETRAIN=0
NIGHTLY_ENABLE_ANCHOR_FINETUNE=0
```

The daily profile is designed to finish reliably on local GPU/MPS by using a stratified high-signal subset:

```bash
NIGHTLY_TOTAL_RUNS=3
NIGHTLY_SUP_MAX_TRAIN_ROWS=300
NIGHTLY_SUP_EPOCHS=1
NIGHTLY_SUP_BATCH_SIZE=8
NIGHTLY_SUP_LEARNING_RATE=2e-6
NIGHTLY_SUP_MAX_REPEAT=3
NIGHTLY_SUP_ANGLE_MODE=cycle
NIGHTLY_SUP_LOSS_MODE=mixed
```

The daily row cap intentionally matches the high-signal smoke scale. The daily profile now runs three seeds every night. If a future change requires a faster local check, use `NIGHTLY_TRAIN_PROFILE=smoke` or `NIGHTLY_TOTAL_RUNS=1` explicitly for that manual run only. The 2026-06-03 23:00 nightly used the previous 2500-row daily default, took 306.5 minutes on MPS, and regressed to `cal_mae=7.7946`, `cal_bucket_acc=65.93`. Keep larger row-count runs in `full` or explicit experiments until they beat the fixed gates.

The 2026-06-04 23:00 launchd run also used the stale 2500-row daily default because the installed job was still executing a copied script under `~/.guess_nightly/`. Reinstalling with `bash scripts/install_nightly_10pm_launchd.sh` fixes the job to execute `$HOME/.guess_nightly/nightly_launcher.sh`, which then execs the current repo script at `scripts/nightly_train_v26.sh`. The 2026-06-05 and 2026-06-06 launchd attempts failed before training with `Operation not permitted` when launchd tried to execute a wrapper directly from `.nightly/` on the external project volume; the installer now keeps the wrapper under `$HOME/.guess_nightly/` to avoid that launchd restriction while still running the current repo script.

Verify the installed entrypoint after changing nightly defaults:

```bash
launchctl print gui/$(id -u)/com.guess.nightly-train-v26 | sed -n '1,80p'
NIGHTLY_DRY_RUN=1 NIGHTLY_ENFORCE_FREE_SPACE_CHECK=0 bash scripts/nightly_train_v26.sh | sed -n '1,70p'
```

The dry-run config line should include:

```text
TOTAL_RUNS=3 sup_rows=300 sup_epochs=1 sup_batch=8
```

`NIGHTLY_SUP_ANGLE_MODE=cycle` trains examples with the same semantic-angle prefixes used by production scoring. This avoids fine-tuning on bare word pairs while evaluating on prefixed text pairs.

`NIGHTLY_SUP_LOSS_MODE` controls the supervised objective:

- `mixed`: default; trains both ranking and absolute cosine objectives. The 2026-06-02 smoke run improved calibrated MAE, hard negatives, hint-like rows, same-category rows, synonym rows, and raw MAE, while keeping strict gates in place.
- `cosent`: ranking objective; faster and strong for bucket accuracy, but the verified smoke runs showed raw MAE degradation.
- `cosine`: absolute cosine/label regression objective; useful for investigating raw MAE degradation.
- `mixed_contrastive`: experimental; adds `OnlineContrastiveLoss` to push selected hard negatives farther apart while protecting clear high positives. Use this for targeted hard-negative experiments before making it the daily default.

Antonym pairs are treated as semantically related but opposite in direction, not as unrelated hard negatives. The normalized training/check target is `antonym_mid`, `score_0_100=50`, `expected_range=45-55`. The nightly builder rewrites older `antonym_low` and `antonym_or_conflict` rows to this policy before they enter train/calib/eval/holdout splits, and the trainer excludes antonyms from contrastive hard-negative mining.

Because `data/*.csv` and `data/*.json` are ignored local data files, the code also carries required antonym fallbacks. `scripts/run_regression_pairs_v23.py` appends the fixed antonym regression checks if the local JSON is missing them. `scripts/build_nightly_semantic_sets.py` injects the corresponding high-weight train-only antonym patch rows, then applies the usual holdout/calib/eval exclusion so frozen holdout pairs still do not leak into training.

`mixed_contrastive` supports a scope knob:

```bash
NIGHTLY_SUP_CONTRASTIVE_SCOPE=selective
NIGHTLY_SUP_CONTRASTIVE_MARGIN=0.5
NIGHTLY_SUP_CONTRASTIVE_POS_THRESHOLD=0.7
NIGHTLY_SUP_CONTRASTIVE_NEG_THRESHOLD=0.3
```

`selective` is the default. It applies contrastive positives only to clear high-positive tags such as `alias_synonym_high`, `near_synonym_high`, and `hint_like_high`, and contrastive negatives only to hard-negative tags. `all` is available for comparison but the 2026-06-02 micro-smoke showed it improved hard-negative MAE while damaging bucket accuracy and same-category behavior.

The trainer also pins high-value rows before filling the remaining daily subset. Rows with `sample_weight >= 3.0` or reviewers starting with `nightly_patch` are kept in the capped subset first, then the rest is filled by stratified sampling. This makes yesterday's reviewed failures visible to the next daily run even when the full training pool is much larger than `NIGHTLY_SUP_MAX_TRAIN_ROWS`.

Current hard-negative boost tags include the recurring real failure patterns from recent reports:

- `same_category_but_far`
- `collocation_not_equivalent`
- `hard_negative_low`
- `cross_category_negative`
- function-word and nonsense lows

The trainer also applies a smaller protective repeat boost to `alias_synonym_high`, `near_synonym_high`, `hint_like_high`, `same_category_mid`, `same_category_strong`, and `related_mid`. This keeps daily hard-negative fixes from collapsing legitimate same-category and synonym scores.

For high-value rows, the trainer can optionally enforce multi-angle coverage. Rows pinned by review/patch weight and protected positive rows can be repeated across up to all five production semantic angles:

```bash
SEM_MIN_ANGLE_REPEAT_FOR_HIGH_VALUE=5
```

This is intentionally off by default. The 2026-06-02 smoke run showed stronger hard-negative MAE but worse overall accuracy and slower MPS training when forced to five angles. Keep it as an experiment knob rather than the daily default.

Use the full profile for slower multi-seed evidence runs:

```bash
NIGHTLY_TRAIN_PROFILE=full NIGHTLY_AUTO_PROMOTE=0 bash scripts/nightly_train_v26.sh
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

Run the daily evidence-producing nightly after the smoke succeeds:

```bash
NIGHTLY_AUTO_PROMOTE=0 bash scripts/nightly_train_v26.sh
```

Run the slower three-seed full profile when you want stronger promotion evidence:

```bash
NIGHTLY_TRAIN_PROFILE=full NIGHTLY_AUTO_PROMOTE=0 bash scripts/nightly_train_v26.sh
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
   - `data/semantic_train_patch_v1.csv` as train-only high-value patches when present
   - `data/score_trace_review_candidates.csv` when present
   - reviewed error/holdout CSVs when present
   - fixed holdout CSVs from `SEM_HOLDOUT_CSVS`, defaulting to `data/semantic_holdout_v1.csv`
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

Fixed holdout rows are excluded from training and calibration, including if the same pair appears in the base train CSV. This keeps promotion evidence from leaking into the candidate.

Train-only patch rows are filtered against holdout/calibration/evaluation pairs, then added only to training. Use this for small reviewed hard-negative or synonym patches that should not become part of the promotion test. If a train-only patch duplicates an older base-train pair, the patch row wins so reviewed labels and higher sample weights are not hidden by historical data.

The remaining supervised gold rows are split by score bucket into train/calibration/evaluation subsets. Defaults:

```bash
SEM_GOLD_CALIB_RATIO=0.35
SEM_GOLD_EVAL_RATIO=0.25
```

## Promotion Gates

Defaults:

- calibrated MAE improves by at least `0.3`
- bucket accuracy improves by at least `2.0` points
- raw and calibrated metrics do not degrade
- hard-negative group MAE does not degrade
- synonym/alias recall does not degrade
- antonym mid-score recall at 40-60 does not degrade
- fixed regression passes

Useful overrides:

```bash
NIGHTLY_MIN_MAE_IMPROVEMENT=0.2
NIGHTLY_MIN_ACC_IMPROVEMENT=1.0
NIGHTLY_MIN_ANTONYM_MID_RECALL_IMPROVEMENT=0.0
NIGHTLY_REQUIRE_NO_DEGRADE_ALL=0
NIGHTLY_AUTO_PROMOTE=0
```

## Calibration

`eval_v26_gold.py` now builds a monotonic isotonic calibration curve by default. The JSON remains compatible with the app and embedding server because it still writes `x_pred` and `y_calibrated`.

Use the legacy quantile-mean calibrator only for comparison:

```bash
SEM_CALIBRATION_METHOD=legacy python3 scripts/eval_v26_gold.py
```

The 2026-06-02 verification run showed that isotonic calibration improved the current production baseline on the fixed nightly eval split from `cal_mae=7.7257, cal_bucket_acc=67.03` to `cal_mae=7.4838, cal_bucket_acc=68.13`. This is a calibration-only scoring improvement; model promotion still requires the candidate to beat the recalibrated baseline gates.

## Reports

Nightly reports are written to:

```text
.nightly/reports/nightly_promotion_*.md
```

Reports include per-round metrics, project-vs-candidate metrics, group metrics, the candidate's largest holdout errors, and calibrated bucket-confusion summaries. Review the worst cases and repeated bucket shifts first when adding new labels or tuning the next objective.

Rejected candidates also write diagnostics. A failed nightly is still useful: use the rejected candidate's worst cases to add or correct labels before the next run.

Each non-dry-run report also includes per-round training data distribution: train rows, supervised gold split sizes, fixed holdout count, gold score buckets, and top training tags.

Run the next-morning triage without touching models:

```bash
python3 scripts/nightly_next_morning_triage_v26.py
```

It combines launchd health, missed-schedule detection, latest real-report analysis, device inference, failed gates, regressed metric groups, bucket-confusion summaries, and the live goal TODO progress from `docs/SEMANTIC_TRAINING_TODO.md`. The missed-schedule check also looks for a non-dry-run `.nightly/data/tmp/nightly_train_v26_*.log` whose timestamp falls within the latest scheduled 23:00 start window; if a three-round run has started but has not written a report yet, triage reports `nightly_started_waiting_for_report` instead of `missed_schedule`. Use `--markdown-output tmp/nightly_triage.md` when you want a saved summary, and `--write-review-csv` when you also want it to refresh `data/nightly_worst_case_review_candidates.csv` from the latest real report's worst cases.

Check live goal progress from the repo:

```bash
python3 scripts/semantic_training_todo_status.py
```

Use `--json` when another script or a morning report needs the same checklist state.

Individual checks remain available:

```bash
python3 scripts/check_nightly_launchd_v26.py
python3 scripts/analyze_nightly_report_v26.py
bash scripts/verify_nightly_outcome_v26.sh --allow-reject
```

Use `--include-dry-run` only when you intentionally want to inspect the latest manual dry-run instead of the latest launchd run.

`check_nightly_launchd_v26.py` validates that launchd is pointed at `$HOME/.guess_nightly/nightly_launcher.sh`, the wrapper still execs the current repo `scripts/nightly_train_v26.sh`, `NIGHTLY_TOTAL_RUNS=3` is loaded, and the latest real report or run log is newer than the latest scheduled run. Historical stderr errors are reported as warnings when they predate the current plist install; fatal-looking stderr lines written after the current install are reported as problems.

The install script archives existing launchd stdout/stderr logs to `*.bak` before reloading the job. This keeps old failures from being mistaken for tonight's run while preserving the evidence for later inspection.

The analyzer prints `失败门控` from the nightly gate output (`mae_ok`, `acc_ok`, no-degrade checks, regression, synonym, antonym, and so on) and `退化分组` from report group metrics. Use those two lines as the first triage signal before reading the full report.

Create a review queue from the latest real report's worst cases and bucket-confusion examples:

```bash
python3 scripts/extract_nightly_worst_case_review_candidates.py
```

This writes `data/nightly_worst_case_review_candidates.csv` with `review_status=pending`. The nightly builder reads this file, but it only consumes rows after you review `corrected_score` / `error_type` and set `review_status=approved` or `merged`. Antonym rows are normalized to `antonym_mid` with `corrected_score=50` during extraction. Bucket-confusion rows use the target/predicted bucket midpoints as temporary scores and keep `source=nightly_bucket_confusion` so they are easy to audit before approval. When `nightly_next_morning_triage_v26.py --write-review-csv` writes this file, its output also includes source/status/severity counts so worst-case rows, bucket-confusion rows, pending rows, and high-severity rows are distinguishable at a glance.

Before changing rows to `approved` or `merged`, validate the queue:

```bash
python3 scripts/validate_review_candidates.py
```

The validator fails approved/merged rows with invalid score ranges, invalid status/source/severity values, duplicate pairs, or antonym rows that are not normalized to `antonym_mid` and `corrected_score=50`. Use `--strict-pending` when you also want pending drafts to be fully clean. The next-morning triage runs the non-strict validation automatically and prints `review_validation_ok` / `review_validation_issues`.

## Real Failure Sample Loop

Run the Flutter app with score tracing enabled:

```bash
flutter run -d macos --dart-define=SCORE_TRACE=true
```

Save the console output, then extract review candidates:

```bash
python3 scripts/extract_score_trace_review_candidates.py tmp/score_trace.log \
  --output data/score_trace_review_candidates.csv
```

Review the generated CSV before it affects training:

- fill `corrected_score`
- set `review_status` to `approved`
- keep uncertain rows as `pending`

The nightly builder automatically consumes approved or merged rows from `data/score_trace_review_candidates.csv`.

## Script Cleanup Notes

The old Phoenix trainers `train_v28_phoenix_finetune.py` and `train_v28b_phoenix_finetune.py` were removed because the nightly flow now uses `train_v28c_mse_contrastive.py`.

Retained legacy/data-builder scripts are still useful for rebuilding source datasets:

- `scripts/build_v28_phoenix_train_csv.py`
- `scripts/build_v28c_balanced_train.py`
- `scripts/build_v28_*`
- older `finetune_v*` scripts used as historical references

Do not delete these unless their generated datasets are replaced and references in docs/tests are updated.
