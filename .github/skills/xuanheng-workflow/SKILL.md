---
name: xuanheng-workflow
description: Use when the user says “玄衡”, or asks to optimize puzzle hints/categories in this repo with the strict Xuanheng workflow, especially when you must preserve hard gates, batch closure, and source-backed routing between score diagnosis and puzzle editing.
---

# Skill: 玄衡统一工作流

## 目标
把当前仓库里已经存在的玄衡规则整合成一个明确入口：当用户喊“玄衡”时，先判断任务属于“分数异常诊断”还是“题库/分类优化”，然后走对应流程，不编造不存在的来源，不跳过闭环校验。

## 适用场景
- 用户直接说“玄衡”
- 用户要求优化某个分类、某批谜题、某组 hints
- 用户要求严格按玄衡规则执行
- 用户反馈分数异常、无关词高分、校准疑似抬分

## 不适用场景
- Flutter UI、控制器、服务层功能开发
- 模型训练、评估、nightly 训练
- 与 `assets/puzzles.json` 和语义打分链路无关的普通代码任务

## 任务路由

### A. 题库/分类优化任务
若用户目标是：
- “优化 xx 分类”
- “修 hints / 清理泄露 / 调自然度 / 做整类闭环”
- “按玄衡规则改 puzzles.json”

则直接进入 **题库优化流**，不要先做分数链路诊断。

### B. 分数异常诊断任务
若用户目标是：
- “为什么这个词分数这么高/低”
- “这个百分比不合理”
- “是不是 calibration 抬分了”
- “为什么无关词会高分”

则先进入 **分数诊断流**，按顺序检查：
1. `data/manual_similarity_overrides.json`
2. `data/semantic_calibration_v27_semreal_anchor.json`
3. `lib/controllers/guess_game_controller.dart`
4. 仅在前三项排除后，才考虑 `assets/puzzles.json`

### C. 特殊子流程：工作分类细修
只有当：
- 当前分类是 `工作`
- 主闭环已经完成
- 用户继续要求精细化/深抠/细修残余书面味

才进入 [work-subtle-naturalization](../work-subtle-naturalization/SKILL.md)。

## 玄衡硬门槛
用户一旦喊“玄衡”，以下全部视为硬门槛：

1. **前6条 + 已知分类不得直接锁定答案**
2. **第7条是最强锚点**
3. **7条 hints 必须尽量对应 7 个不同主维度**
4. **任何 hint 不得与 answer 共享字符**
5. **禁止元描述、模板词、泛词、残片、主观臆造**
6. **禁止同题重复、同类重复、全局重复**
7. **禁止同题内 7 条 hints 出现同义词/近义词替换，例如“郁闷”与“郁结”不能同时出现**
7. **任意修改后必须重检，未到零错误不得报完成**
8. **禁止未检报检、禁止虚报“已完成/已通过”**
9. **自然语义优先于整齐化，不得为了控字数牺牲自然性**
10. **没有来源依据时，宁可降强度，不得编造细节**

## 题库优化流

### 1. 先界定范围
明确：
- 目标分类或目标答案
- 是单题、单分类还是批量任务
- 只改 `assets/puzzles.json`，还是还要顺带解释分数表现

### 2. 分类任务必须批量闭环
当用户说“优化某分类”时：
- 必须处理该分类下全部目标谜题
- 禁止只修一题就汇报“分类已完成”
- 必须全部通过后再统一汇报

### 3. 逐词闭环
对分类中的每个答案，固定顺序如下：
1. 回读当前答案 7 条 hints
2. 先检查硬规则
3. 若有违规，只修当前答案
4. 修完后立即重新检查当前答案
5. 当前答案零错误后，记录 7 条 hints、维度、可猜度判断
6. 只有当前答案闭环，才允许进入下一个答案

### 4. 修改策略
- 优先最小改动，不先重写整组
- 若用户指出第2-6条任一槽位泄露，优先下调该槽位强度
- 若第6/7条只是泛化词或弱相关词，视为无效锚点，优先替换高位锚点
- 每个 hint 单独设计，不得用提示词池批量抽取填充
- 若只存在同义词/近义词重复问题，优先替换冲突 hint，而不是全部重写

### 5. 自然语义规则
- hints 以自然短语为主，通常不超过 5 字；必要时可放宽到 6 字，但不能为了控字数写成残片
- 不强制统一字数、句式、四字格
- 候选词优先参考常识与网络可见表达
- 本地模型不能作为 hint 候选生成、排序、写入依据

## 分数诊断流
若任务是分数异常：
1. 先给结论：异常更像来自覆盖 / 校准 / 后处理 / 题库哪一层
2. 再给证据：至少一条映射或规则命中
3. 最后给动作：改规则 / 改校准 / 改题库 / 暂不改

项目经验：
- raw 60 常映射到约 71
- raw 70 常映射到约 80
若异常来自 calibration，优先报告映射证据，不要先改 hints。

## 最小必跑校验

### 题库/分类优化时
- 单答案硬闸：`python3 scripts/xuanheng_check_answer_strict.py <答案>`
- 单答案闭环：若要宣称“玄衡闭环通过”，必须额外提供 `--review-json`，并包含 7 条 hint 的维度、目标强度、依据、前6提前锁词风险。
- 旧脚本 `python xuanheng_check_answer.py` 只能作为兼容补充，不能再作为闭环依据。
- 整分类：`python xuanheng_check_detailed.py`
- 全局规则：`python scripts/validate_global_hint_rules_v1.py`

### 需要展示强度/可猜度时
- 再按需运行：`python scripts/score_category_semantic_guess_v1.py`

## 输出要求

### 题库优化类输出
- 修改范围
- 发现的问题
- 修改策略
- 当前验证结果
- 是否整类闭环
- 未完成项与原因（若存在）

### 分数诊断类输出
- 结论
- 证据
- 动作建议

## 限制
- 不得宣称读取了不存在的玄衡来源
- 不得把 `tmp/xuanheng_*` 试验脚本当作权威规则
- 不得把“玄衡”解释成可以绕过校验的身份特权
- 若系统层问题未排除，不得把所有异常都甩给 `puzzles.json`


