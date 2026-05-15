# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**词语猜谜 (Guess Game)** is a Chinese word guessing game built with Flutter. Players have 6 attempts to guess 2-5 character Chinese words, receiving semantic similarity feedback based on a fine-tuned BGE-M3 embedding model.

## Common Development Commands

### Flutter Development

```bash
# Run the app (macOS example)
flutter run -d macos

# Run with score tracing enabled (logs semantic scoring breakdown)
flutter run -d macos --dart-define=SCORE_TRACE=true

# Run tests
flutter test

# Analyze code
flutter analyze

# Get dependencies
flutter pub get
```

### Python Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify versions
python - <<'PY'
import sentence_transformers, transformers, tokenizers
print('sentence-transformers', sentence_transformers.__version__)
print('transformers', transformers.__version__)
print('tokenizers', tokenizers.__version__)
PY
```

### Embedding Server

```bash
# Start embedding server (must be running for gameplay)
python embedding_server.py

# Health check
curl -sS http://127.0.0.1:8000/health

# Check if model is ready (after warmup)
curl -sS http://127.0.0.1:8000/ready

# Custom model/calibration paths (optional)
EMBED_MODEL_DIR=/path/to/model EMBED_CALIB_PATH=/path/to/calibration.json python embedding_server.py
```

### Pre-flight Checks

```bash
# One-command validation (recommended before deployment)
bash scripts/preflight_v26.sh
```

This script:
1. Starts the embedding server
2. Runs health checks
3. Runs semantic regression tests (expects 30/30 pass)
4. Validates puzzle data integrity

### Model Training & Evaluation

**Current production model**: `models/bge-m3-finetuned-v27-semreal-anchor`  
**Current calibration**: `data/semantic_calibration_v27_semreal_anchor.json`

#### v26 Training Pipeline (Gold + Unsupervised)

```bash
# 1. Build gold standard + unsupervised pairs
python3 scripts/build_v26_gold_and_unsup.py

# 2. Unsupervised pretraining
TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  SEM_UNSUP_PAIRS_JSONL=data/unsupervised_pairs_v26.jsonl \
  SEM_BASE_MODEL=models/bge-m3-finetuned-v25-hintdistill \
  SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v26-unsup \
  SEM_MAX_PAIRS=5000 SEM_BATCH_SIZE=8 SEM_EPOCHS=1 \
  python3 scripts/pretrain_v26_unsupervised.py

# 3. Calibration + Evaluation on gold set
SEM_MODEL_PATH=models/bge-m3-finetuned-v26-unsup \
  SEM_CALIB_CSV=data/gold_v26_calib.csv \
  SEM_EVAL_CSV=data/gold_v26_eval.csv \
  SEM_CALIB_JSON=data/semantic_calibration_v26_gold.json \
  python3 scripts/eval_v26_gold.py
```

#### Nightly Training (Automated)

```bash
# Install nightly training (runs at 22:00 daily)
bash scripts/install_nightly_10pm_launchd.sh

# Check status
launchctl list | grep com.guess.nightly-train-v26

# Manual trigger
bash scripts/nightly_train_v26.sh

# Dry run (no actual training)
NIGHTLY_DRY_RUN=1 bash scripts/nightly_train_v26.sh

# Uninstall
bash scripts/uninstall_nightly_10pm_launchd.sh
```

**Key nightly parameters**:
- `NIGHTLY_AUTO_PROMOTE=1`: Auto-promote if passing thresholds (default: on)
- `NIGHTLY_DELETE_OLD_ON_PROMOTE=1`: Delete old model on promotion (default: on)
- `NIGHTLY_MIN_MAE_IMPROVEMENT=0.0`: Minimum MAE improvement required
- `NIGHTLY_MIN_ACC_IMPROVEMENT=0.0`: Minimum accuracy improvement required
- `NIGHTLY_PROMOTE_WEEKDAYS=6,7`: Only promote on weekends

Logs: `tmp/nightly_train_v26_*.log`, `tmp/launchd_nightly_v26.{out,err}.log`

### Regression Testing

```bash
# Semantic regression (expects 30/30)
python scripts/run_regression_pairs_v23.py | tail -n 8

# Puzzle data validation
python -c "import json;json.load(open('assets/puzzles.json','r',encoding='utf-8'));print('puzzles ok')"
python tmp/puzzle_naturalness_diff_report.py
```

## Architecture

### High-Level Flow

1. **Flutter App** (`lib/`) - Game UI and orchestration
2. **Embedding Server** (`embedding_server.py`) - Python FastAPI server providing semantic embeddings
3. **Semantic Scoring** - Multi-angle cosine similarity with isotonic calibration
4. **Manual Overrides** - Hardcoded corrections in `data/manual_similarity_overrides.json`

### Key Components

#### Game Controller (`lib/controllers/guess_game_controller.dart`)

Central state manager coordinating:
- Puzzle lifecycle (loading from `assets/puzzles.json`)
- User input validation and scoring
- Semantic + lexical similarity fusion
- Calibration curve application
- Manual override lookups

**Scoring Pipeline**:
1. Check exact match → 100%
2. Check manual overrides → 0-95%
3. Fetch embeddings from server with 5 semantic angles:
   - "从含义角度看："
   - "从用途角度看："
   - "从场景角度看："
   - "从特征角度看："
   - "从关联角度看："
4. Compute cosine similarity, trim outliers, average
5. Apply isotonic calibration curve
6. Blend with lexical similarity (80% semantic + 20% lexical)
7. Apply business rules:
   - Cap unrelated (<20% semantic) to 10%
   - Cap zero-lexical low-semantic to 10%
   - Floor near-synonyms (lex≥40 & sem≥70) to 30%
   - Penalize function words (你/我/他/的/了) by 30%

#### Embedding Service (`lib/services/embedding_service.dart`)

HTTP client managing:
- Fallback: online endpoint → local endpoint (http://127.0.0.1:8000/embed)
- `/ready` endpoint polling (waits for model warmup)
- Response caching (keyed by endpoint + text)
- Probe for endpoint availability

#### Puzzle Repository (`lib/services/puzzle_repository.dart`)

Loads and validates puzzles:
- Filters by length (2-5 chars)
- Normalizes hints (removes duplicates, filters unusable)
- Pads to 7 hints with generic fallbacks
- Applies hint rewrites (currently empty, preserved for future use)

#### Embedding Server (`embedding_server.py`)

FastAPI server:
- Loads `bge-m3-finetuned-v27-semreal-anchor` (or `EMBED_MODEL_DIR`)
- `/health`: Returns status, optionally triggers background warmup
- `/ready`: Returns warmup completion status
- `/embed`: Returns normalized embeddings
- Warmup: `EMBED_WARMUP_ON_HEALTH=1` (default) triggers lazy warmup on first health check

### Data Files

- `assets/puzzles.json` - 1000+ word puzzles with hints, category, POS
- `data/semantic_calibration_v27_semreal_anchor.json` - Isotonic regression curve (x_pred → y_calibrated)
- `data/manual_similarity_overrides.json` - Hardcoded similarity overrides
- `data/gold_v26_*.csv` - Human-labeled gold standard for calibration/eval
- `data/semantic_scoring_user_input_template.csv` - User input samples for augmentation

### Model Versioning

- **v27** (current): Semi-supervised real user data + manual anchors
- **v26**: Gold standard + unsupervised pretraining
- **v25**: Hint distillation dataset
- **v21**: Refine (fallback model)

See `V7_DEPLOYMENT.md` for historical context on early model iterations.

## Important Notes

### Embedding Server Must Run

The game **requires** the embedding server to provide semantic similarity. Without it, the game falls back to lexical-only scoring (poor UX).

### Score Tracing

Enable with `--dart-define=SCORE_TRACE=true` to log JSON scoring breakdowns:
```json
{
  "event": "semantic_mix",
  "guess": "猫咪",
  "answer": "猫",
  "semantic_raw_cosine": "0.9872",
  "semantic_percent_raw": "98.72",
  "semantic_percent_calibrated": "95.00",
  "lexical": 50,
  "combined": 86,
  "final": 85,
  "notes": ["near_synonym_floor30"]
}
```

### Model Portability

To use on a new machine:
1. Copy `models/bge-m3-finetuned-v27-semreal-anchor/`
2. Copy `data/semantic_calibration_v27_semreal_anchor.json`
3. Copy `data/manual_similarity_overrides.json`
4. Run `bash scripts/preflight_v26.sh` to verify

Or set custom paths:
```bash
EMBED_MODEL_DIR=/custom/path/model python embedding_server.py
```

### Nightly Training Philosophy

- **Weekday**: Train candidate model, do NOT promote
- **Weekend**: Promote only if MAE/accuracy improve
- **Safety**: Old models auto-deleted on promotion, failed candidates auto-deleted
- **Rollback**: Manual overrides in `data/manual_similarity_overrides.json` always respected

### Calibration Curve

The isotonic regression curve maps raw semantic percentages to calibrated scores. This corrects for model bias (e.g., over-confident predictions). Stored in JSON as:
```json
{
  "x_pred": [0, 10, 20, ..., 100],
  "y_calibrated": [0, 5, 15, ..., 95]
}
```

Linear interpolation applied at runtime in `_calibrateSemanticPercent()`.
