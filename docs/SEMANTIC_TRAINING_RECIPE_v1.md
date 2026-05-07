# Semantic Training Recipe v1

## Target
- Goal: improve semantic quality with measurable gains, not just more epochs.
- Baseline fields to track each round:
  - `cal_mae`
  - `cal_bucket_acc`
  - regression pass/fail
  - anime guessability pass ratio
  - quality audit summary (`banned_hits`, `cross_domain_hits`, `monotonic_items`)

## Pre-work (must finish first)
1. Build hard negatives from current failures.
2. Add label quality checks (conflict and duplicate checks).
3. Ensure eval split is frozen and never mixed with training.

## Data Pipeline
1. Current core data:
  - `data/gold_v26_pool.csv`
  - `data/gold_v26_calib.csv`
  - `data/gold_v26_eval.csv`
  - `data/gold_v26_manual_anchor.csv`
  - `data/unsupervised_pairs_v26.jsonl`
2. New hard negatives:
  - run `scripts/build_hard_negatives_from_guessability_v1.py`
  - output: `data/hard_negatives_from_guessability_v1.csv`
3. Merge strategy:
  - keep existing manual anchor rows high priority
  - append hard negatives with controlled ratio (start at 20% of gold pool)

## Training Strategy
1. Stage A: unsupervised pretrain (coverage)
2. Stage B: anchor finetune (boundary)
3. Stage C: calibration eval (trustworthy scores)

Use the existing nightly entry:
- `scripts/nightly_train_v26.sh`

Suggested initial params for stable gains:
- `SEM_MAX_PAIRS=1800`
- `SEM_LEARNING_RATE=2.5e-6`
- `NIGHTLY_ENABLE_ANCHOR_FINETUNE=1`
- `NIGHTLY_ANCHOR_LEARNING_RATE=1.0e-6`
- `NIGHTLY_TOTAL_RUNS=3`

## Gating Rules (promotion)
Promote only if all pass:
1. `cal_mae` improved by >= 0.10
2. `cal_bucket_acc` improved by >= 0.50
3. regression check passes
4. anime guessability ratio does not decrease
5. `banned_hits=0` and `cross_domain_hits=0`

## 7-Day Execution Plan
Day 1:
- run hard-negative miner
- inspect and clean duplicates

Day 2:
- merge hard negatives into training pool (small ratio)
- dry run nightly

Day 3:
- run full nightly with 3 rounds
- collect `tmp/nightly_round_summary_*.txt`

Day 4:
- compare best candidate vs baseline using eval metrics + anime guessability

Day 5:
- expand hard negatives by another 10%
- rerun nightly

Day 6:
- lock improved model/calibration if gates pass

Day 7:
- write postmortem: what improved, what regressed, next iteration focus

## Anti-patterns to avoid
1. Increasing epochs first without fixing hard negatives.
2. Mixing eval samples into training pool.
3. Applying large hint rewrites and model update in the same experiment.
4. Accepting gains on one metric while regression or cross-domain errors rise.
