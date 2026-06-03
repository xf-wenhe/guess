# 词语猜谜（Flutter）

中文猜词小游戏，支持 2-5 个中文字的有效词语输入。

## 规则
- 每局随机一个有意义的词语（答案长度 2-5 个字）。
- 共 6 次猜测机会。
- 开局展示两条提示，符合度分别为 30% 和 40%。
- 每次猜错都会新增一条提示，符合度依次增加 10%，最高 90%。
- 每次猜测失败都会显示“当前猜测与正确答案的符合度”百分比。
- 猜对显示恭喜界面，6 次全错显示爆炸效果。

## 运行
```bash
flutter run
```

可在支持的任意平台（移动、Web、桌面）直接运行。若需重新开局，在游戏界面点击”再来一局”或”再试一次”。

---

## 多平台发布

一键构建 Android、macOS 发布包并上传到 GitHub Release。

### 前置条件

| 依赖 | 安装方式 | 用途 |
|:-----|:---------|:-----|
| Flutter SDK | [官网](https://flutter.dev) | 构建应用 |
| GitHub CLI | `brew install gh` | 创建 Release |
| Java JDK 17 | `brew install openjdk@17` | Android 构建 |
| gh 登录 | `gh auth login` | 访问 GitHub |

### 执行发布

```bash
# 设置 Java 路径
export PATH=”/opt/homebrew/opt/openjdk@17/bin:$PATH”

# 执行发布脚本
bash scripts/release_build.sh
```

脚本自动执行以下步骤：

1. 从 `pubspec.yaml` 读取版本号
2. 运行 `flutter analyze` 检查代码
3. 构建 Android APK、macOS ZIP
4. 创建 GitHub Release 并上传附件

### 输出产物

| 平台 | 文件名 | 安装方式 |
|:-----|:-------|:---------|
| Android | `guess-{version}-android.apk` | 直接安装 |
| macOS | `guess-{version}-macos.zip` | 解压打开 `guess.app` |

### 平台限制

| 平台 | 构建要求 |
|:-----|:---------|
| Android | 需要 Java JDK 17+ |
| macOS | 仅限 macOS 主机 |
| Windows | 仅限 Windows 主机（当前脚本跳过） |

### 注意事项

- macOS 首次运行需在「系统偏好设置 → 安全性与隐私」中允许
- 游戏需运行 embedding server 才能正常游玩
- 发布新版本前需更新 `pubspec.yaml` 中的版本号

---

### 资源包要求（首次拉代码必看）

运行前请确认以下反馈动图已放置到固定目录：

- `assets/images/feedback/success.gif`：猜中答案时的动图
- `assets/images/feedback/fail.gif`：本轮失败时的动图

说明：
- 文件名和路径需与上面完全一致。
- 若缺失，程序会自动回退到内置向量动画（可运行，但视觉效果会降级）。
- 资源目录说明见 `assets/images/feedback/README.md`。

## 环境对齐（一键）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

说明：在 macOS 系统 Python 使用 LibreSSL 的环境中，依赖已固定 `urllib3<2`，用于避免启动服务时的 OpenSSL 兼容告警。

快速验证（版本与回归）：

```bash
python - <<'PY'
import sentence_transformers, transformers, tokenizers
print('sentence-transformers', sentence_transformers.__version__)
print('transformers', transformers.__version__)
print('tokenizers', tokenizers.__version__)
PY

python scripts/run_regression_pairs_v23.py | tail -n 8
```

## 模型文件获取 & Embedding Server 配置 {#embedding-server-setup}

### 自动下载（推荐，首次运行）

模型文件（约 2 GB）未随代码一同提交。首次运行 embedding server 时会**自动从 HuggingFace 下载**基础模型：

```bash
python embedding_server.py
```

默认下载 [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3)，存放至 `models/bge-m3-finetuned-v27-semreal-anchor/`。

下载进度显示在终端：

```
[embedding_server] Model not found at 'models/...'. Downloading 'BAAI/bge-m3' from HuggingFace...
```

### 使用微调版模型（可选，精度更高）

若你已有本地微调模型，指定路径后启动：

```bash
EMBED_MODEL_DIR=/path/to/bge-m3-finetuned-v27-semreal-anchor python embedding_server.py
```

若微调模型已发布到 HuggingFace，可通过以下方式自动下载：

```bash
EMBED_HF_REPO=your-username/bge-m3-finetuned-v27 python embedding_server.py
```

### 无本地服务时的回退行为

若 embedding server 未运行，Flutter 应用会降级为**纯词形相似度**评分（仍可游玩，但语义反馈精度下降）。
应用界面会提示"未连接到语义模型服务"，并显示启动方法。

### 代理 / 离线环境

HuggingFace 下载需要网络访问。如在受限网络中，可手动下载后放置到项目根目录：

```
models/
  bge-m3-finetuned-v27-semreal-anchor/
    config.json
    tokenizer_config.json
    tokenizer.json
    model.safetensors     ← 主权重文件（约 2 GB）
    ...
```

放置完成后重新启动 `python embedding_server.py`，无需联网。

---

## 上线前检查清单

一键执行（推荐）：

```bash
bash scripts/preflight_v26.sh
```

1) 启动 embedding 服务（保持该终端运行）：

```bash
python embedding_server.py
```

2) 新开终端做健康检查：

```bash
curl -sS http://127.0.0.1:8000/health
```

说明：`/health` 默认会触发一次后台语义预热（`EMBED_WARMUP_ON_HEALTH=1`），可显著降低首个 `/embed` 请求耗时。
若希望客户端在首个语义请求前等待预热完成，可调用 `/ready`（返回 `ready: true/false`）。
批量评分使用 `/embed_batch`，用于一次请求多个语义角度，减少 Flutter 端往返次数。
如需关闭可设置：

```bash
EMBED_WARMUP_ON_HEALTH=0 python embedding_server.py
```

3) 运行语义回归（应为 30/30）：

```bash
python scripts/run_regression_pairs_v23.py | tail -n 8
```

4) 启动 Flutter（macOS 示例）：

```bash
flutter run -d macos
```

如需监控每次用户输入的打分拆解（语义/词面/校准/规则命中），可开启：

```bash
flutter run -d macos --dart-define=SCORE_TRACE=true
```

开启后会在日志输出以 `[score_trace]` 开头的 JSON。

## 语义模型离线迭代（v25 当前流程）

按下面顺序执行，避免训练/校准/评估数据泄漏：

```bash
python3 scripts/build_v25_hint_distill_dataset.py
SEM_INPUT_CSV=data/semantic_scoring_v25_hintdistill.csv SEM_OUTPUT_DIR=data/splits_v25 python3 scripts/split_semantic_dataset.py
SEM_TRAIN_CSV=data/splits_v25/semantic_train.csv SEM_BASE_MODEL=models/bge-m3-finetuned-v24-patch SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v25-hintdistill SEM_BATCH_SIZE=8 SEM_EPOCHS=1 SEM_WARMUP_STEPS=80 SEM_LEARNING_RATE=8e-6 python3 scripts/finetune_v19_split.py
SEM_CALIB_CSV=data/splits_v25/semantic_calib.csv SEM_MODEL_PATH=models/bge-m3-finetuned-v25-hintdistill SEM_CALIB_OUTPUT_JSON=data/semantic_calibration_v25_hintdistill.json python3 scripts/build_v19_calibration_split.py
SEM_HOLDOUT_CSV=data/splits_v25/semantic_holdout.csv SEM_MODEL_PATH=models/bge-m3-finetuned-v25-hintdistill SEM_CALIB_PATH=data/semantic_calibration_v25_hintdistill.json python3 scripts/eval_v19_holdout.py
```

输出文件：
- `data/semantic_scoring_v25_hintdistill.csv`
- `data/splits_v25/semantic_train.csv`
- `data/splits_v25/semantic_calib.csv`
- `data/splits_v25/semantic_holdout.csv`
- `data/semantic_calibration_v25_hintdistill.json`

## v26：保留小批人工金标 + 无标注自监督预训练

目标：仅保留小批人工金标用于校准与验收；主训练改为无标注自监督。

```bash
python3 scripts/build_v26_gold_and_unsup.py
TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
	SEM_UNSUP_PAIRS_JSONL=data/unsupervised_pairs_v26.jsonl \
	SEM_BASE_MODEL=models/bge-m3-finetuned-v25-hintdistill \
	SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v26-unsup \
	SEM_MAX_PAIRS=5000 SEM_BATCH_SIZE=8 SEM_EPOCHS=1 SEM_WARMUP_STEPS=50 SEM_LEARNING_RATE=6e-6 \
	python3 scripts/pretrain_v26_unsupervised.py
SEM_MODEL_PATH=models/bge-m3-finetuned-v26-unsup \
	SEM_CALIB_CSV=data/gold_v26_calib.csv \
	SEM_EVAL_CSV=data/gold_v26_eval.csv \
	SEM_CALIB_JSON=data/semantic_calibration_v26_gold.json \
	python3 scripts/eval_v26_gold.py
```

输出文件：
- `data/gold_v26_pool.csv`（冻结人工金标池）
- `data/gold_v26_calib.csv`（金标校准集）
- `data/gold_v26_eval.csv`（金标验收集）
- `data/unsupervised_pairs_v26.jsonl`（无标注自监督训练对）
- `models/bge-m3-finetuned-v26-unsup`
- `data/semantic_calibration_v26_gold.json`

## 每晚 23:00 自动训练（macOS）

推荐（不依赖登录会话，不易漏跑）：

```bash
sudo bash scripts/install_nightly_10pm_daemon.sh
```

查看 daemon 状态：

```bash
sudo launchctl print system/com.guess.nightly-train-v26.daemon | egrep 'state =|last exit code =|runs ='
```

卸载 daemon：

```bash
sudo bash scripts/uninstall_nightly_10pm_daemon.sh
```

兼容方案（LaunchAgent，依赖用户会话）：

已提供脚本：
- `scripts/nightly_train_v26.sh`：执行一轮夜间训练（v28c 监督训练 + 大 holdout 校准验收 + 分组门控 + 回归检查 + 达标才晋升默认）。详见 `docs/SEMANTIC_NIGHTLY_TRAINING.md`。
- `scripts/install_nightly_10pm_launchd.sh`：安装 `launchd` 定时任务（每天 23:00）
- `scripts/uninstall_nightly_10pm_launchd.sh`：卸载定时任务
- `scripts/verify_nightly_outcome_v26.sh`：一键验收夜训结果（晋升、模型回写、校准回写、候选清理）

安装定时任务：

```bash
bash scripts/install_nightly_10pm_launchd.sh
```

查看任务状态：

```bash
launchctl list | grep com.guess.nightly-train-v26
```

手动触发一次（不等到 23:00）：

```bash
bash scripts/nightly_train_v26.sh
```

仅演练流程（不真正训练）：

```bash
NIGHTLY_DRY_RUN=1 bash scripts/nightly_train_v26.sh
```

验收与自动晋升参数（可选）：
- `NIGHTLY_AUTO_PROMOTE=1`：达标后自动覆盖默认模型与默认校准（默认开启）
- `NIGHTLY_DELETE_OLD_ON_PROMOTE=1`：达标晋升时删除旧默认模型并切换到最新模型（默认开启）
- `NIGHTLY_DELETE_REJECTED_CANDIDATE=1`：未达标时自动删除候选模型与候选校准（默认开启）
- `NIGHTLY_MIN_MAE_IMPROVEMENT=0.01`：默认要求 `cal_mae` 至少下降 0.01 才算达标
- `NIGHTLY_MIN_ACC_IMPROVEMENT=0.3`：默认要求 `cal_bucket_acc` 至少上升 0.3 才算达标
- `NIGHTLY_TOTAL_RUNS=1`：默认每晚执行 1 轮训练（单链路、单候选名）

训练节奏与稳定性参数（建议）：
- `NIGHTLY_PROMOTE_WEEKDAYS=6,7`：仅周末执行晋升判定（工作日只训练候选）
- `SEM_MAX_PAIRS=3000`、`SEM_LEARNING_RATE=4e-6`：收紧自监督步长，降低漂移
- `NIGHTLY_ENABLE_ANCHOR_FINETUNE=1`：自监督后使用 `data/gold_v26_manual_anchor.csv` 做低学习率锚点回灌

扩容金标（默认已开启）：
- `scripts/build_v26_gold_and_unsup.py` 会把 `data/semantic_scoring_user_input_template.csv` 分层抽样并与人工覆盖合并
- 默认 `SEM_GOLD_TARGET_TOTAL=260`，在 `SEM_GOLD_CALIB_RATIO=0.55` 下，通常可得到 100+ 的 `gold_eval`

示例（更严格门槛）：

```bash
NIGHTLY_MIN_MAE_IMPROVEMENT=0.2 NIGHTLY_MIN_ACC_IMPROVEMENT=2.0 bash scripts/nightly_train_v26.sh
```

日志位置：
- `.nightly/data/tmp/nightly_train_v26_*.log`
- `.nightly/logs/launchd_nightly_v26.out.log`
- `.nightly/logs/launchd_nightly_v26.err.log`
- `.nightly/data/tmp/nightly_round_summary_*.txt`（逐轮汇总：round、mae、acc、是否通过回归、是否晋升）

夜训后验收（默认严格要求本轮晋升成功）：

```bash
bash scripts/verify_nightly_outcome_v26.sh
```

如只检查流程完整性、允许本轮未晋升：

```bash
bash scripts/verify_nightly_outcome_v26.sh --allow-reject
```

## 生产默认与回滚

- 当前默认模型：`models/bge-m3-finetuned-v27-semreal-anchor`
- 当前默认校准：`data/semantic_calibration_v27_semreal_anchor.json`
- 当前默认配置索引：`config/current_model.json`

### 跨电脑携带本地模型

- 需要一并拷贝：`models/bge-m3-finetuned-v27-semreal-anchor` 与 `data/semantic_calibration_v27_semreal_anchor.json`
- 新电脑建议直接保持同样目录结构（项目根目录下 `models/` 与 `data/`）
- 若模型不在默认路径，可启动时指定环境变量：
	- `EMBED_MODEL_DIR=/你的路径/bge-m3-finetuned-v27-semreal-anchor`
- 校准文件由 Flutter 从项目 `data/` 目录读取；跨电脑时保持同名文件即可。
- 本地服务验证：
	- `bash scripts/preflight_v26.sh`
	- `curl http://127.0.0.1:8000/health`
- Flutter 在新电脑中本地加载模型时，优先读取 `EMBED_MODEL_DIR`，未设置时使用默认 `models/bge-m3-finetuned-v27-semreal-anchor`
- 人工覆盖：`data/manual_similarity_overrides.json`
- 回滚模型：`models/bge-m3-finetuned-v21-refine`

## 提示自然化收敛（2026-03-02）

- 数据文件：`assets/puzzles.json`
- 运行时清洗策略：`lib/services/puzzle_repository.dart`（保留机制，重写表已精简为空兜底）
- 对比报告脚本：`tmp/puzzle_naturalness_diff_report.py`
- 最新结果：受影响词条数为 0，替换 Top 为无，过滤原因统计为无。

复验命令：

```bash
python -c "import json;json.load(open('assets/puzzles.json','r',encoding='utf-8'));print('puzzles ok')"
python tmp/puzzle_naturalness_diff_report.py
```

快速查看结果摘要：

```bash
python - <<'PY'
from pathlib import Path
print('\n'.join(Path('tmp/puzzle_naturalness_report.md').read_text(encoding='utf-8').splitlines()[:20]))
PY
```
