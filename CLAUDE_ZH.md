# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

**词语猜谜（Guess Game）** 是一款基于 Flutter 构建的中文词语猜谜游戏。玩家有 6 次机会猜测 2-5 个汉字的词语，并基于微调的 BGE-M3 嵌入模型获得语义相似度反馈。

## 常用开发命令

### Flutter 开发

```bash
# 运行应用（macOS 示例）
flutter run -d macos

# 启用分数追踪运行（记录语义评分详情）
flutter run -d macos --dart-define=SCORE_TRACE=true

# 运行测试
flutter test

# 代码分析
flutter analyze

# 获取依赖
flutter pub get
```

### Python 环境设置

```bash
# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 验证版本
python - <<'PY'
import sentence_transformers, transformers, tokenizers
print('sentence-transformers', sentence_transformers.__version__)
print('transformers', transformers.__version__)
print('tokenizers', tokenizers.__version__)
PY
```

### 嵌入服务

```bash
# 启动嵌入服务（游戏运行必需）
python embedding_server.py

# 健康检查
curl -sS http://127.0.0.1:8000/health

# 检查模型是否就绪（预热后）
curl -sS http://127.0.0.1:8000/ready

# 自定义模型路径（可选；校准文件由 Flutter 从 data/ 读取）
EMBED_MODEL_DIR=/path/to/model python embedding_server.py
```

### 上线前检查

```bash
# 一键验证（部署前推荐）
bash scripts/preflight_v26.sh
```

此脚本执行：
1. 启动嵌入服务
2. 运行健康检查
3. 运行语义回归测试（期望 30/30 通过）
4. 验证谜题数据完整性

### 模型训练与评估

**当前生产模型**：`models/bge-m3-finetuned-v27-semreal-anchor`  
**当前校准文件**：`data/semantic_calibration_v27_semreal_anchor.json`

#### v26 训练流程（金标 + 无监督）

```bash
# 1. 构建金标准 + 无监督对
python3 scripts/build_v26_gold_and_unsup.py

# 2. 无监督预训练
TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  SEM_UNSUP_PAIRS_JSONL=data/unsupervised_pairs_v26.jsonl \
  SEM_BASE_MODEL=models/bge-m3-finetuned-v25-hintdistill \
  SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v26-unsup \
  SEM_MAX_PAIRS=5000 SEM_BATCH_SIZE=8 SEM_EPOCHS=1 \
  python3 scripts/pretrain_v26_unsupervised.py

# 3. 在金标集上校准 + 评估
SEM_MODEL_PATH=models/bge-m3-finetuned-v26-unsup \
  SEM_CALIB_CSV=data/gold_v26_calib.csv \
  SEM_EVAL_CSV=data/gold_v26_eval.csv \
  SEM_CALIB_JSON=data/semantic_calibration_v26_gold.json \
  python3 scripts/eval_v26_gold.py
```

#### 夜间训练（自动化）

```bash
# 安装夜间训练（每天 23:00 执行）
bash scripts/install_nightly_10pm_launchd.sh

# 检查状态
launchctl list | grep com.guess.nightly-train-v26

# 手动触发
bash scripts/nightly_train_v26.sh

# 演练模式（不实际训练）
NIGHTLY_DRY_RUN=1 bash scripts/nightly_train_v26.sh

# 卸载
bash scripts/uninstall_nightly_10pm_launchd.sh
```

**关键夜间参数**：
- `NIGHTLY_AUTO_PROMOTE=1`：达标后自动晋升（默认开启）
- `NIGHTLY_DELETE_OLD_ON_PROMOTE=1`：晋升时删除旧模型（默认开启）
- `NIGHTLY_MIN_MAE_IMPROVEMENT=0.0`：要求的最小 MAE 改进
- `NIGHTLY_MIN_ACC_IMPROVEMENT=0.0`：要求的最小准确率改进
- `NIGHTLY_PROMOTE_WEEKDAYS=6,7`：仅周末晋升

日志位置：`tmp/nightly_train_v26_*.log`、`tmp/launchd_nightly_v26.{out,err}.log`

### 回归测试

```bash
# 语义回归（期望 30/30）
python scripts/run_regression_pairs_v23.py | tail -n 8

# 谜题数据验证
python -c "import json;json.load(open('assets/puzzles.json','r',encoding='utf-8'));print('puzzles ok')"
python tmp/puzzle_naturalness_diff_report.py
```

## 架构说明

### 高层流程

1. **Flutter 应用**（`lib/`）- 游戏界面与编排
2. **嵌入服务**（`embedding_server.py`）- Python FastAPI 服务提供语义嵌入
3. **语义评分** - 多角度余弦相似度 + 保序回归校准
4. **人工覆盖** - 硬编码修正在 `data/manual_similarity_overrides.json`

### 关键组件

#### 游戏控制器（`lib/controllers/guess_game_controller.dart`）

核心状态管理器，协调：
- 谜题生命周期（从 `assets/puzzles.json` 加载）
- 用户输入验证与评分
- 语义 + 词面相似度融合
- 校准曲线应用
- 人工覆盖查找

**评分流程**：
1. 检查精确匹配 → 100%
2. 检查人工覆盖 → 0-95%
3. 从服务器获取嵌入，使用 5 个语义角度：
   - "从含义角度看："
   - "从用途角度看："
   - "从场景角度看："
   - "从特征角度看："
   - "从关联角度看："
4. 计算余弦相似度，去除极值，取平均
5. 应用保序回归校准曲线
6. 与词面相似度混合（80% 语义 + 20% 词面）
7. 应用业务规则：
   - 不相关（<20% 语义）限制在 10%
   - 零词面低语义限制在 10%
   - 近义词（词面≥40 且 语义≥70）下限 30%
   - 虚词（你/我/他/的/了）惩罚 30%

#### 嵌入服务（`lib/services/embedding_service.dart`）

HTTP 客户端管理：
- 回退策略：在线端点 → 本地端点（http://127.0.0.1:8000/embed）
- `/ready` 端点轮询（等待模型预热）
- 响应缓存（按端点 + 文本分组）
- 端点可用性探测

#### 谜题仓库（`lib/services/puzzle_repository.dart`）

加载并验证谜题：
- 按长度过滤（2-5 字）
- 归一化提示（去重、过滤不可用）
- 填充至 7 条提示（使用通用兜底）
- 应用提示重写（当前为空，保留供未来使用）

#### 嵌入服务器（`embedding_server.py`）

FastAPI 服务：
- 加载 `bge-m3-finetuned-v27-semreal-anchor`（或 `EMBED_MODEL_DIR`）
- `/health`：返回状态，可选触发后台预热
- `/ready`：返回预热完成状态
- `/embed`：返回归一化嵌入
- `/embed_batch`：一次返回多个文本的归一化嵌入
- 预热：`EMBED_WARMUP_ON_HEALTH=1`（默认）在首次健康检查时触发懒加载预热

### 数据文件

- `assets/puzzles.json` - 约 890 条词语谜题，含提示、类别、词性
- `data/semantic_calibration_v27_semreal_anchor.json` - 保序回归曲线（x_pred → y_calibrated）
- `data/manual_similarity_overrides.json` - 硬编码相似度覆盖
- `data/gold_v26_*.csv` - 人工标注金标准，用于校准/评估
- `data/semantic_scoring_user_input_template.csv` - 用户输入样本，用于扩充

### 模型版本

- **v27**（当前）：半监督真实用户数据 + 人工锚点
- **v26**：金标准 + 无监督预训练
- **v25**：提示蒸馏数据集
- **v21**：精炼版（回退模型）

参见 `V7_DEPLOYMENT.md` 了解早期模型迭代的历史背景。

## 重要说明

### 嵌入服务必须运行

游戏**需要**嵌入服务来提供语义相似度。没有它，游戏会回退到纯词面评分（用户体验差）。

### 分数追踪

使用 `--dart-define=SCORE_TRACE=true` 启用，记录 JSON 格式的评分详情：
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

### 模型可移植性

在新机器上使用：
1. 复制 `models/bge-m3-finetuned-v27-semreal-anchor/`
2. 复制 `data/semantic_calibration_v27_semreal_anchor.json`
3. 复制 `data/manual_similarity_overrides.json`
4. 运行 `bash scripts/preflight_v26.sh` 验证

或设置自定义路径：
```bash
EMBED_MODEL_DIR=/custom/path/model python embedding_server.py
```

### 夜间训练理念

- **工作日**：训练候选模型，不晋升
- **周末**：仅当 MAE/准确率提升时才晋升
- **安全性**：晋升时自动删除旧模型，失败的候选自动删除
- **回滚**：`data/manual_similarity_overrides.json` 中的人工覆盖始终受尊重

### 校准曲线

保序回归曲线将原始语义百分比映射到校准分数。这纠正了模型偏差（例如过度自信的预测）。存储为 JSON 格式：
```json
{
  "x_pred": [0, 10, 20, ..., 100],
  "y_calibrated": [0, 5, 15, ..., 95]
}
```

运行时在 `_calibrateSemanticPercent()` 中应用线性插值。
