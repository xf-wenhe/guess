# Phoenix v28 诊断报告与优化方案

## 一、v28 训练结果

| 指标 | v27 (基线) | v28 (1 epoch) |
|------|-----------|---------------|
| 回归测试 | 30/30 (100%) | 29/30 (96.7%) |
| Gold MAE (raw) | — | 31.004 |
| Gold MAE (cal) | — | 5.540 |
| Gold Bucket Acc (cal) | — | 79.66% |
| 校准饱和点 | 7/20 | 6/20 |
| FAIL 项 | 无 | 汽车-卡车 |

## 二、核心问题

### 问题 1：模型 embedding 空间全面"坍缩"

v28 的 raw cosine similarity 普遍高于 v27，反义词和虚词尤甚：

| 词对 | v27 raw | v28 raw | 变化 |
|------|---------|---------|------|
| 大/小 | 49.32 | 77.32 | +28 |
| 生/死 | 41.95 | 82.73 | +41 |
| 买/卖 | 69.08 | 86.81 | +18 |
| 的/了 | 59.19 | 77.57 | +18 |
| 我/你 | 52.18 | 80.99 | +29 |

**根因**：CoSENTLoss 是排序损失，只学了"同义词 > 相关词 > 反义词"的相对顺序，
没有惩罚反义词之间的绝对余弦距离。16,000 条训练数据中，大量 hint 锚点
(70-90分) 把 embedding 空间往高相似度方向拉，反义词/虚词被连带拉近。

### 问题 2：校准曲线过度补偿 → 连带伤害

校准曲线为了把 75-85 区间的"假高分"压下去，形成了粗暴的压缩：

- raw=69 → cal=4 (压缩 65 分)
- raw=80 → cal=23 (压缩 57 分)

但"汽车-卡车"(raw=79.88) 本应是合理的中高相关词，也被压到 20.82 → FAIL。

### 问题 3：Gold 校准数据集缺少中低分锚点

calib CSV 中 35% 是 100 分（self-anchor），score 70-89 区间仅 5 行。
校准曲线在 70-90 区间几乎没有锚点，只能盲目外推。

## 三、解决方案

### 方案 A：换损失函数（推荐，夜训可直接用）

将 CoSENTLoss 替换为 **MSELoss + ContrastiveLoss 混合**：

- **MSELoss**：直接回归 score，惩罚"反义词 raw=80 但 label=0.10"这种偏差
  让模型学到绝对距离，而不只是排序。
- **ContrastiveLoss**：以 margin 强制推开低分组词对的 embedding 距离
  margin=0.5 时，score<0.2 的词对 embedding 距离会被强制拉开。

实现方式：`scripts/train_v28c_mse_contrastive.py`（已设计，未创建）
- 损失 = 0.5 * MSE(cosine_sim, label) + 0.5 * Contrastive(margin=0.5)
- 对 score < 0.2 的 pair 额外加权 3x

### 方案 B：训练数据重平衡（配合方案 A）

当前问题：
- hint 锚点 (score 30-90) 有 ~6,000 条，占总数据 37%
- 这些数据把 embedding 空间往"高相似度"方向拉
- 反义词仅 314 条 (2%)，信号被淹没

调整：
1. hint 锚点降采样到 2,000 条
2. 反义词从 314 → 1,570 (过采样 5x)
3. 虚词数据保持 2,348 条
4. 最终比例：难负样本 ~50%，hint ~15%，同义/相关 ~35%

### 方案 C：重建 Gold 校准数据集（配合方案 A/B）

当前 `gold_v26_calib.csv` 的分数分布不均：
- 100 分：50 行 (35%)
- 0-9 分：28 行 (20%)
- 70-89 分：仅 5 行 (4%)

需要补充 70-90 分区间的锚点，让校准曲线有足够数据学习这个区间的映射。

具体操作：从 train_v28_phoenix.csv 中抽取 score 60-95 的行，
补充到 gold_v26_calib.csv，使 60-95 区间至少有 30 行。

## 四、夜训集成建议

夜训脚本 `scripts/nightly_train_v26.sh` 需要更新为 v28 Phoenix 流程：

### 训练命令（3 epochs）

```bash
# Phase 1: 数据构建（仅首次或数据变更时）
python3 scripts/build_v28_antonym_pairs.py
python3 scripts/build_v28_function_word_pairs.py
python3 scripts/build_v28_category_graded.py
python3 scripts/build_v28_subset_pairs.py
python3 scripts/build_v28_synonym_expansion.py
python3 scripts/build_v28_phoenix_train_csv.py

# Phase 2: 训练（使用 MSE+Contrastive 损失）
SEM_TRAIN_CSV=data/train_v28_phoenix.csv \
SEM_BASE_MODEL=models/bge-m3-finetuned-v27-semreal-anchor \
SEM_OUTPUT_MODEL=models/bge-m3-finetuned-v28-phoenix \
SEM_EPOCHS=3 SEM_BATCH_SIZE=8 SEM_LR=2e-5 \
python3 scripts/train_v28c_mse_contrastive.py

# Phase 3: 校准 + 评估
SEM_MODEL_PATH=models/bge-m3-finetuned-v28-phoenix \
SEM_CALIB_JSON=data/semantic_calibration_v28_phoenix.json \
python3 scripts/eval_v26_gold.py

# Phase 4: 回归验证
SEM_MODEL_PATH=models/bge-m3-finetuned-v28-phoenix \
SEM_CALIB_PATH=data/semantic_calibration_v28_phoenix.json \
python3 scripts/run_regression_pairs_v23.py
```

### 自动提升条件

```bash
# 在 nightly 脚本中加入
REGRESSION_PASS=$(python3 scripts/run_regression_pairs_v23.py | grep pass_rate | awk -F= '{print $NF}')
if [[ "$REGRESSION_PASS" == "100.0%" ]]; then
    # 对比 v27 边缘诊断
    # 如果反义词 raw < 30, 虚词 raw < 25 → 提升
fi
```

## 五、需要你做的事

1. **确认方案选择**：是否采用 MSE+Contrastive 混合损失？
   还是只用 MSE？或你有其他想法？

2. **我需要创建的文件**（你确认后我立即创建）：
   - `scripts/train_v28c_mse_contrastive.py` — 新训练脚本
   - `scripts/build_v28_gold_calib_supplement.py` — 校准数据补充脚本
   - 更新 `scripts/nightly_train_v26.sh` 或创建 `scripts/nightly_train_v28.sh`

3. **不需要你提供额外数据**，所有训练数据已就绪（16,034 条）。

4. **预计夜训时间**：3 epochs × ~5 小时/epoch = ~15 小时（MPS）
   建议在 22:00 启动，次日 13:00 左右完成。
