# Copilot Memory (Project Handoff)

Last updated: 2026-03-05
Project: guess (Flutter + local semantic model)

## Current Production Defaults
- Model: `models/bge-m3-finetuned-v27-semreal-anchor`
- Calibration: `data/semantic_calibration_v27_semreal_anchor.json`
- Embedding server default path is switched to v27 semreal anchor.
- App-side calibration loading default is switched to v27 semreal anchor.

## Quality Gate Policy (Must Keep)
- Promote a new candidate only when BOTH:
  - calibrated MAE decreases (better), and
  - calibrated bucket accuracy increases (better)
- And regression must pass 30/30 (`scripts/run_regression_pairs_v23.py`).
- If candidate is worse, do not promote; delete candidate model/calibration.

## Recent Training Outcomes
- `v27-semreal-anchor` beat previous baseline (`v26-unsup`):
  - cal_mae: 5.006 -> 4.265
  - cal_bucket_acc: 75.21% -> 82.05%
- Subsequent hard-mining candidates (`hm1`, `hm2`) regressed on gold metrics; both rejected and cleaned.

## Nightly Automation Status
- launchd job: `com.guess.nightly-train-v26`
- Schedule: daily 22:00
- Historical 2026-03-04 22:00 run failed due to incorrect `cd` quoting in launchd command.
- Fix applied in `scripts/install_nightly_10pm_launchd.sh` and job reinstalled.
- Manual kickstart preflight confirms job can start and enter training pipeline.

## Data / Hints Status
- `assets/puzzles.json` completed multi-pass repair and structural validation:
  - items=892
  - each item has exactly 7 hints
  - no duplicate hints within item
- Audit and repair scripts exist for strict global checks.

## Xuanheng Workflow Trigger
- In this repo, if the user says `玄衡`, treat it as a request to use the strict Xuanheng workflow rather than a casual nickname.
- Route by task type:
  - score anomaly / unreasonable percentage / calibration suspicion -> diagnose manual overrides, calibration, and controller post-processing before touching `assets/puzzles.json`
  - category or hint optimization -> use per-answer closure inside the requested category, then report only after the full category closes
- Stable hard gates:
  - front 6 hints + known category must not directly lock the answer
  - slot 7 is the strongest anchor
  - 7 hints should use 7 distinct main dimensions
  - hints must not share characters with the answer
  - no duplicate hints within item / category / globally
  - no meta/template/filler fragments; natural semantics beats forced uniform wording
- Durable validation tools:
  - per-answer: `xuanheng_check_answer.py`
  - category-level: `xuanheng_check_detailed.py`
  - global rules: `scripts/validate_global_hint_rules_v1.py`
- Do not treat `tmp/xuanheng_*` trial scripts as authoritative workflow sources.

## Operational Constraints Learned
- On Apple MPS, training can hit OOM; use:
  - `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`
  - smaller sample / batch size
- Disk can become bottleneck during `model.save`; keep free space before long runs.

## Important Note
- Raw Copilot chat history itself is not exported by project files.
- This document is the persisted memory summary for future sessions.
