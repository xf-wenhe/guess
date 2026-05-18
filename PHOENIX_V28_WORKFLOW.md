# Phoenix 训练流水线 v28

> 命名寓意：凤凰涅槃，从 v27 的缺陷中重生。
> 目标：系统性解决反义词高分、角度退化、校准饱和、虚词失控四大核心问题。
> 基座模型不变：继续使用 bge-m3 (XLM-RoBERTa-large, 568M)。

---

## 全局路线图

```
Phase 0: 基线快照 ─── 记录 v27 的全部指标，作为对比基准
    │
Phase 1: 数据工程 ─── 构建高质量、多层次的训练数据集（核心工作量）
    │
Phase 2: 模型训练 ─── 多阶段训练：预训练 → 微调 → 校准
    │
Phase 3: 评估验收 ─── 回归测试 + 新增专项测试 + 对比基线
    │
Phase 4: 部署上线 ─── 更新校准曲线、人工锚点、上线切换
```

---

## Phase 0: 基线快照

> 目的：建立量化基准，后续每一步都能对比。

### 0.1 运行现有回归测试
```bash
python3 scripts/run_regression_pairs_v23.py | tee tmp/baseline_v27_regression.log
```
预期：30/30 PASS

### 0.2 运行 gold 标准评估
```bash
SEM_MODEL_PATH=models/bge-m3-finetuned-v27-semreal-anchor \
  python3 scripts/eval_v26_gold.py --json-out tmp/baseline_v27_metrics.json
```
记录：raw_mae, cal_mae, raw_bucket_acc, cal_bucket_acc

### 0.3 运行边缘用例诊断
```bash
python3 tmp/phoenix_edge_diagnostic_v27.py
```
（此脚本在 Phase 1 中创建，包含反义词/虚词/子集词/同音词等 30+ 测试对）

### 0.4 记录指标到基线文件
```bash
# 保存到 tmp/phoenix_baseline_v27.json
```

**产出**：`tmp/phoenix_baseline_v27.json`

---

## Phase 1: 数据工程

> 这是整个 Phoenix 流水线最关键的阶段。
> 目标：将训练数据从 572 条扩展到 5000+ 条，覆盖所有语义层次。

### Step 1.1: 反义词专项数据构建

> 解决的核心问题：好/坏 78.78 分、大/小 49.32 分

**操作**：
1. 创建 `data/antonym_pairs_v28.csv`
2. 手动 + 自动结合构建 200+ 对反义词

**自动挖掘方法**：
- 从 puzzles 中的形容词（62个）配对反义词
- 常见反义词词典覆盖：大/小、好/坏、黑/白、热/冷、生/死、快/慢、高/低、长/短、明/暗、美/丑 等
- 动词反义：爱/恨、来/去、买/卖、开/关、起/落、笑/哭

**标注规则**：
```csv
answer,user_input,score_0_100,relation_tag,reason
好,坏,12,antonym_low,反义词：语义对立
大,小,10,antonym_low,反义词：程度对立
黑,白,15,antonym_low,反义词：颜色对立
```

**需要你提供**：是否有常用反义词词典或词库？如果没有，我会从 puzzles 的 878 个词中自动挖掘并生成初稿供你审校。

### Step 1.2: 功能词/虚词专项数据

> 解决的核心问题：的/了 59.19、一/二 63.89、我/你 52.18

**操作**：
1. 创建 `data/function_word_pairs_v28.csv`

**覆盖范围**：
- 助词：的/了/吗/呢/吧/啊 — 互相配对 + vs 实词
- 代词：我/你/他/她/它/这/那 — 互相配对 + vs 实词
- 数词：一/二/三/四/五/百/千/万 — 互相配对 + vs 实词
- 量词：个/只/条/本/张/把 — 互相配对 + vs 实词

**标注规则**：
```csv
answer,user_input,score_0_100,relation_tag,reason
的,了,8,function_word_low,虚词之间无语义关联
我,你,5,function_word_low,代词之间无语义关联
的,猫,3,function_word_low,虚词vs实词语义无关
```

### Step 1.3: 同类词差异度标注

> 解决的核心问题：猫/狗 73.72、足球/篮球 65.91 得分偏高

**操作**：
1. 利用 puzzles 已有的 23 个分类，同分类内配对
2. 创建 `data/same_category_graded_v28.csv`

**方法**：
- 从每个分类中随机抽取 5-10 对同类词
- 按语义距离标注 3 个层次：
  - 同类但强关联 (50-60)：苹果/梨、猫/虎
  - 同类中等关联 (35-50)：苹果/香蕉、猫/狗
  - 同类弱关联 (20-35)：苹果/榴莲、足球/高尔夫

**预期数量**：200-300 对

**需要你提供**：你对同类词之间的分数期望是否认同？特别是猫/狗你期望多少分？

### Step 1.4: 子集/包含关系专项

> 解决的核心问题：书包/书包带 90.62 过高

**操作**：
1. 从 puzzles 答案中挖掘包含关系的词对
2. 创建 `data/subset_relation_pairs_v28.csv`

**标注规则**：
```csv
answer,user_input,score_0_100,relation_tag,reason
手机,手机壳,35,subset_relation_mid,子集关系：功能体vs配件
电脑,电脑桌,30,subset_relation_mid,子集关系：设备vs家具
茶,奶茶,55,subset_relation_mid,子集关系：原料vs成品
猫,波斯猫,60,subset_relation_mid,子集关系：上位词vs下位词
```

### Step 1.5: 高质量同义词/近义词扩充

> 当前 near_synonym_high 仅 6 条，严重不足

**操作**：
1. 从 puzzles 的 878 个答案中挖掘同义词/近义词对
2. 创建 `data/synonym_expansion_v28.csv`

**方法**：
- 利用 word2vec/同义词词林 自动挖掘候选
- 人工审校分数
- 目标：200+ 对

### Step 1.6: 合并训练集

**操作**：
1. 创建脚本 `scripts/build_v28_phoenix_train_csv.py`
2. 合并所有数据源：
   - 原有 gold_v26_pool.csv (260条) 
   - 原有 train_v27_semreal.csv 中的高质量部分
   - 新增 antonym_pairs_v28.csv (~200条)
   - 新增 function_word_pairs_v28.csv (~150条)
   - 新增 same_category_graded_v28.csv (~250条)
   - 新增 subset_relation_pairs_v28.csv (~100条)
   - 新增 synonym_expansion_v28.csv (~200条)
   - 新增隐喻/文化关联词对 (~100条)
3. 去重、双向对称化
4. 最终目标：**5000-8000 条**

**产出**：`data/train_v28_phoenix.csv`

---

## Phase 2: 模型训练

> 三阶段训练策略，每阶段有独立的验收标准。

### Step 2.1: Stage A — 无监督预训练

> 与现有 v26 流程相同，利用 17487 对无监督数据

```bash
TOKENIZERS_PARALLELISM=false PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  SEM_UNSUP_PAIRS_JSONL=data/unsupervised_pairs_v26.jsonl \
  SEM_BASE_MODEL=models/bge-m3-finetuned-v27-semreal-anchor \
  SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v28-phoenix-stageA \
  SEM_MAX_PAIRS=15000 SEM_BATCH_SIZE=8 SEM_EPOCHS=1 \
  SEM_LEARNING_RATE=1e-5 \
  python3 scripts/pretrain_v26_unsupervised.py
```

**验收**：模型加载正常，embedding 维度 1024

### Step 2.2: Stage B — 有监督精调（核心）

> 新创建训练脚本 `scripts/train_v28_phoenix_finetune.py`

**训练策略**：
- 基座：Stage A 的输出模型
- 损失函数：CoSENTLoss（保持兼容）+ 新增 AnglELoss 对比
- 训练参数：
  - epochs: 3
  - batch_size: 16
  - learning_rate: 2e-5
  - warmup_ratio: 0.1
  - scheduler: cosine
  - seed: 20260515

```bash
SEM_TRAIN_CSV=data/train_v28_phoenix.csv \
  SEM_BASE_MODEL=models/bge-m3-finetuned-v28-phoenix-stageA \
  SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v28-phoenix-stageB \
  SEM_EPOCHS=3 SEM_BATCH_SIZE=16 SEM_LR=2e-5 \
  SEM_WARMUP_RATIO=0.1 \
  python3 scripts/train_v28_phoenix_finetune.py
```

**需要你提供**：训练设备是 MPS (Mac) 还是 CUDA (GPU)？这影响 batch_size 和训练时间。

### Step 2.3: Stage C — 校准曲线重建

> 解决的核心问题：校准曲线 7/20 点饱和在 100%

```bash
SEM_MODEL_PATH=models/bge-m3-finetuned-v28-phoenix-stageB \
  SEM_CALIB_CSV=data/gold_v26_calib.csv \
  SEM_EVAL_CSV=data/gold_v26_eval.csv \
  SEM_CALIB_JSON=data/semantic_calibration_v28_phoenix.json \
  python3 scripts/eval_v26_gold.py --json-out tmp/v28_stageC_metrics.json
```

**验收**：
- 校准曲线饱和点 ≤ 2 个
- cal_mae < v27 的 cal_mae
- cal_bucket_acc ≥ v27 的 cal_bucket_acc

---

## Phase 3: 评估验收

### Step 3.1: 回归测试
```bash
SEM_MODEL_PATH=models/bge-m3-finetuned-v28-phoenix-stageB \
  SEM_CALIB_PATH=data/semantic_calibration_v28_phoenix.json \
  python3 scripts/run_regression_pairs_v23.py
```
**通过标准**：30/30 PASS

### Step 3.2: 边缘用例专项测试

运行 Phase 0 中创建的诊断脚本，对比 v27 vs v28：
```bash
SEM_MODEL_PATH=models/bge-m3-finetuned-v28-phoenix-stageB \
  python3 tmp/phoenix_edge_diagnostic_v27.py | tee tmp/v28_edge_results.log
```

**通过标准**：

| 测试类别 | v27 表现 | v28 目标 |
|---------|---------|---------|
| 反义词 (好/坏等) | 78.78 | ≤ 20 |
| 虚词互比 (的/了) | 59.19 | ≤ 12 |
| 代词互比 (我/你) | 52.18 | ≤ 10 |
| 数字互比 (三/四) | 80.09 | ≤ 15 |
| 同类弱关联 (猫/狗) | 73.72 | 35-55 |
| 子集关系 (书包/书包带) | 90.62 | ≤ 50 |
| 无关词 (的/火锅) | 24.86 | ≤ 10 |

### Step 3.3: 无退化确认

> 确保 v28 在修复问题的同时，没有在正确场景上退化

```bash
# 同义词不应退步
# 相关词不应退步
# 无关词不应升分
```

**通过标准**：
- 同义词对得分与 v27 差异 ≤ ±5
- 相关词对得分与 v27 差异 ≤ ±8
- 无关词对得分不高于 v27

### Step 3.4: 总评分卡

创建 `tmp/phoenix_v28_scorecard.json`，汇总所有指标并与基线对比。

---

## Phase 4: 部署上线

### Step 4.1: 更新模型文件
```bash
# 备份 v27
cp -r models/bge-m3-finetuned-v27-semreal-anchor models/_archive/bge-m3-finetuned-v27-semreal-anchor-backup

# 部署 v28
# 更新 embedding_server.py 中的 LOCAL_DIR 或通过环境变量指向新模型
```

### Step 4.2: 更新校准曲线
```bash
# 将 data/semantic_calibration_v28_phoenix.json 部署为当前使用的校准文件
```

### Step 4.3: 更新人工锚点

> 基于 v28 的实际表现，调整 `data/manual_similarity_overrides.json`
> v28 修复好的问题可以移除对应的人工覆盖（如反义词惩罚）

### Step 4.4: 全链路验证
```bash
bash scripts/preflight_v26.sh
```

### Step 4.5: 游戏内测试
```bash
flutter run -d macos --dart-define=SCORE_TRACE=true
```
手动测试 10+ 组猜测，验证游戏体验。

---

## 需要你提供的信息

| 序号 | 问题 | 用途 |
|------|------|------|
| 1 | 训练设备：Mac MPS 还是 NVIDIA CUDA？ | 决定 batch_size 和训练时间 |
| 2 | 是否有反义词词典或同义词词林？ | Step 1.1 数据构建 |
| 3 | 对同类词（猫/狗）的期望分数范围？ | Step 1.3 标注校准 |
| 4 | 是否有真实玩家猜测数据？ | 可用于 hard negative mining |
| 5 | 是否有 LLM API（如 GPT/Claude）可用？ | 自动化数据标注辅助 |

---

## 文件清单（将要创建的）

```
scripts/
  build_v28_antonym_pairs.py          # Step 1.1
  build_v28_function_word_pairs.py    # Step 1.2
  build_v28_category_graded.py        # Step 1.3
  build_v28_subset_pairs.py           # Step 1.4
  build_v28_synonym_expansion.py      # Step 1.5
  build_v28_phoenix_train_csv.py      # Step 1.6
  train_v28_phoenix_finetune.py       # Step 2.2

data/
  antonym_pairs_v28.csv               # Step 1.1
  function_word_pairs_v28.csv         # Step 1.2
  same_category_graded_v28.csv        # Step 1.3
  subset_relation_pairs_v28.csv       # Step 1.4
  synonym_expansion_v28.csv           # Step 1.5
  train_v28_phoenix.csv               # Step 1.6
  semantic_calibration_v28_phoenix.json # Step 2.3

tmp/
  phoenix_baseline_v27.json           # Phase 0
  phoenix_edge_diagnostic_v27.py      # Phase 0
  v28_stageC_metrics.json             # Step 2.3
  phoenix_v28_scorecard.json          # Step 3.4

models/
  bge-m3-finetuned-v28-phoenix-stageA/  # Step 2.1
  bge-m3-finetuned-v28-phoenix-stageB/  # Step 2.2
```
