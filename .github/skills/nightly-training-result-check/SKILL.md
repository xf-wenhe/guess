---
name: nightly-training-result-check
description: "每晚训练结果检测流程。USE FOR: 夜训是否成功、是否晋升、为何 rejected、DRY_RUN 与真实夜训混淆排查、门槛是否过严。WHEN: 用户问昨晚训练结果、夜训结论、要不要调门槛、accepted/promoted 为什么是 False。"
---

# Skill: 每晚训练结果检测

## 目标
用统一口径快速判断夜训是否有效执行、候选是否达标、是否晋升，并给出是否需要调参的最小建议。

## 适用场景
- 用户问“昨晚训练结果如何”
- summary 显示 `DRY_RUN`，不确定是否真跑过
- 训练有 metrics 但 `accepted=False` 或 `promoted=False`
- 需要判断门槛是否过严（而不是训练失败）

## 标准流程
1. 先分清数据源：
   - 工作区手动运行日志：`tmp/nightly_*`
   - launchd 真实夜训日志：`$HOME/.guess_nightly/nightly_data/tmp/nightly_*`
2. 优先读取 launchd summary：`nightly_round_summary_<stamp>.txt`。
3. 若 summary 为 `DRY_RUN`，判定为“仅流程演练”，不可下训练优劣结论。
4. 若非 `DRY_RUN`，读取同批次 metrics：
   - `nightly_base_metrics_*`
   - `nightly_candidate_metrics_*`
   - 必要时补读 `nightly_pretrain_metrics_*` 与 `nightly_anchor_metrics_*`
5. 对照门槛判断 rejected 原因：
   - `NIGHTLY_MIN_MAE_IMPROVEMENT`
   - `NIGHTLY_MIN_ACC_IMPROVEMENT`
   - `NIGHTLY_REQUIRE_NO_DEGRADE_ALL`
   - `NIGHTLY_REQUIRE_STRICT_IMPROVEMENT`
6. 输出结论时必须区分：
   - 训练失败（命令/产物异常）
   - 训练成功但未达门槛（正常 rejected）
   - 达标并晋升（accepted=True + promoted=True）

## 项目特化规则
- 本项目真实夜训优先看 `$HOME/.guess_nightly/nightly_data/tmp/`，不要只看工作区 `tmp/`。
- 工作区 `tmp` 中常见 `NIGHTLY_DRY_RUN=1` 手动演练，容易误判为“昨晚没结果”。
- launchd 运行根目录是 `$HOME/.guess_nightly/workspaces/guess_runtime`，与工作区路径不同属正常。

## 快速检查命令
```bash
# 1) 看最近真实夜训产物
ls -lt ~/.guess_nightly/nightly_data/tmp | head -n 30

# 2) 读最新 summary
cat ~/.guess_nightly/nightly_data/tmp/nightly_round_summary_<stamp>.txt

# 3) 对比某轮 base/candidate 指标
cat ~/.guess_nightly/nightly_data/tmp/nightly_base_metrics_<stamp>_r1.json
cat ~/.guess_nightly/nightly_data/tmp/nightly_candidate_metrics_<stamp>_r1.json
```

## 输出模板
1. 结论：`DRY_RUN` / `真实训练未达标` / `已晋升`。
2. 证据：给出 round、`base_mae/cand_mae/base_acc/cand_acc/reg_ok/accepted/promoted`。
3. 解释：明确是“门槛拦截”还是“训练异常”。
4. 动作：仅给最小调整建议（优先调门槛，不先动训练强度）。

## 禁止事项
- 只看工作区 `tmp` 就下“昨晚无结果”结论。
- 在 `DRY_RUN` 情况下给出模型优劣判断。
- 未给证据就建议大幅改训练参数（如直接翻倍 lr 或大改 pairs）。
