# Engineering Entrypoints

This document is the current map for production, candidate, and cleanup paths.
It is intentionally conservative: historical scripts stay in place until a file
is proven unused by the active app, validation, or training workflows.

## Production Defaults

- App puzzle source: `assets/puzzles.json`
- Production model: `models/bge-m3-finetuned-v27-semreal-anchor`
- Production calibration: `data/semantic_calibration_v27_semreal_anchor.json`
- Manual overrides: `data/manual_similarity_overrides.json`
- Config index: `config/current_model.json`
- Embedding server: `embedding_server.py`

## Required Gates

- Flutter/code sanity: `flutter analyze` and `flutter test`
- Embedding regression: `python3 scripts/run_regression_pairs_v23.py`
- Puzzle structure: `python3 scripts/validate_puzzle_data.py`
- Global hint policy: `python3 scripts/validate_global_hint_rules_v1.py`
- Xuanheng single-answer hard gate: `python3 scripts/xuanheng_check_answer_strict.py <答案>`
- Full local preflight: `bash scripts/preflight_v26.sh`

`scripts/preflight_v26.sh` now includes the global hint policy gate. The current
`assets/puzzles.json` is expected to fail that gate until the hint cleanup pass
is completed.

## Candidate Model Workflow

- Candidate training data builder: `scripts/build_v28c_balanced_train.py`
- Candidate train script: `scripts/train_v28c_mse_contrastive.py`
- Candidate nightly wrapper: `scripts/nightly_train_v28.sh`
- Candidate calibration/eval: `scripts/eval_v26_gold.py` with v28 gold CSV env vars

Puzzle hints remain available to v28c training, but the builder now labels
low-quality hint pairs as `puzzle_hint_low_quality` and emits `sample_weight` so
training can reduce their influence instead of treating every hint equally.

## Shared Helper Modules

- Semantic and calibration utilities: `scripts/semantic_common.py`
- Hint policy and training hint quality utilities: `scripts/hint_policy_common.py`
- Flutter scoring data models: `lib/services/scoring_models.dart`
- Flutter semantic post-processing rules: `lib/services/semantic_score_rules.dart`

## Cleanup Rule

Only delete a script or generated data file when all of the following are true:

- It is not referenced by app code, preflight, nightly training, or this document.
- It is not needed to reproduce the current production model or v28c candidate.
- It is not the latest report for a current gate.
- The deletion list is reviewed before removal.

Otherwise, mark it as historical or move it to an archive in a dedicated cleanup
pass.
