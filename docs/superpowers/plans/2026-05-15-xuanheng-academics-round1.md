# 学科分类第一轮闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 `assets/puzzles.json` 中 `学科` 分类执行玄衡第一轮闭环，先清理硬规则违规与明显不自然项，再给第二轮精调留出稳定基础。

**Architecture:** 只修改 `assets/puzzles.json`。按 `学科` 分类逐题执行“回读 -> 检查 -> 最小改动 -> 当前题复检”的闭环，不先进入分数链路诊断，除非执行中发现异常更像 calibration / override / controller 问题。完成逐题处理后，再做分类级和全局级校验。

**Tech Stack:** JSON 数据文件、Python 校验脚本、玄衡 workflow 规则

---

### Task 1: 建立学科分类工作清单

**Files:**
- Modify: `assets/puzzles.json`
- Check: `xuanheng_check_answer.py`
- Check: `xuanheng_check_detailed.py`
- Check: `scripts/validate_global_hint_rules_v1.py`

- [ ] **Step 1: 抽取学科分类全部答案并记录处理顺序**

Run:
```bash
python - <<'PY'
import json
with open('assets/puzzles.json','r',encoding='utf-8') as f:
    data=json.load(f)
items=[x['answer'] for x in data if x.get('category')=='学科']
for i,answer in enumerate(items,1):
    print(f'{i}. {answer}')
PY
```

Expected: 输出 `学科` 分类全部答案，作为逐题闭环顺序。

- [ ] **Step 2: 明确第一轮只处理这些问题**

规则：
```text
1. answer 与 hint 共字
2. 同题重复 / 同类重复 / 全局重复
3. 元描述 / 模板词 / 空泛词 / 残片
4. 前6条明显泄露
5. 第7条明显不是最强锚点
6. 明显不自然表达
```

- [ ] **Step 3: 确认第一轮不做这些事情**

规则：
```text
1. 不追求整类最终风格统一
2. 不强做严格 7 维度精修
3. 不先查 calibration / override / controller
4. 不一次性整组重写所有题
```

### Task 2: 逐题执行第一轮闭环

**Files:**
- Modify: `assets/puzzles.json`
- Check: `xuanheng_check_answer.py`

- [ ] **Step 1: 回读当前答案的 7 条 hints**

对当前答案执行：
```text
1. 读取 answer / category / 7条 hints
2. 标记明显违规项
3. 只决定当前答案的修复策略
```

- [ ] **Step 2: 优先最小改动修复当前答案**

修复顺序：
```text
1. 先修字面隔离
2. 再修模板词 / 残片 / 空泛词
3. 再压低前6条明显泄露
4. 再补强第7条锚点
5. 若局部修补收益太低，才重写当前整组
```

- [ ] **Step 3: 修改后立即复检当前答案**

Run:
```bash
python xuanheng_check_answer.py
```

Expected: 至少不再命中当前答案的明显硬规则问题；若脚本输出仍有违规，继续只修当前答案，禁止跳题。

- [ ] **Step 4: 记录当前答案闭环状态**

记录内容：
```text
1. 当前答案改了哪些槽位
2. 当前答案原始主要问题
3. 当前答案是否已通过第一轮目标
4. 若未通过，继续留在当前答案
```

- [ ] **Step 5: 当前答案通过后再进入下一个答案**

执行规则：
```text
只有当前答案完成“修改后复检”且无明显残留硬违规，才允许处理下一个答案。
```

### Task 3: 执行分类级与全局级验证

**Files:**
- Modify: `assets/puzzles.json`
- Check: `xuanheng_check_detailed.py`
- Check: `scripts/validate_global_hint_rules_v1.py`

- [ ] **Step 1: 跑学科分类检查**

Run:
```bash
python xuanheng_check_detailed.py
```

Expected: `学科` 分类不再出现第一轮目标范围内的大量明显违规。

- [ ] **Step 2: 跑全局规则检查**

Run:
```bash
python scripts/validate_global_hint_rules_v1.py
```

Expected: 输出全局规则检查结果；若发现第一轮本应处理的问题，回到对应答案继续修复。

- [ ] **Step 3: 输出第一轮总结，不虚报完成**

总结必须包括：
```text
1. 处理了多少个学科答案
2. 第一轮主要清掉了哪些问题
3. 还剩哪些适合放到第二轮（维度细调、阶梯细调、风格统一）
4. 若有无法归因于题库的问题，明确指出需升级到分数诊断流
```

### Task 4: 触发升级条件时切换诊断流

**Files:**
- Check: `data/manual_similarity_overrides.json`
- Check: `data/semantic_calibration_v27_semreal_anchor.json`
- Check: `lib/controllers/guess_game_controller.dart`

- [ ] **Step 1: 仅在出现这些信号时升级**

升级信号：
```text
1. hints 明显合理但可猜度表现整体反常
2. 某类词在多题中系统性高分 / 低分
3. 更像 calibration 抬升或 controller 后处理导致的体验异常
```

- [ ] **Step 2: 若升级，暂停继续修改题库并明确说明原因**

输出格式：
```text
1. 先说为什么怀疑不是单纯题库问题
2. 指出要检查 overrides / calibration / controller 哪一层
3. 暂停继续批量改 hints，避免误修
```

## Verification

按以下顺序验收：
1. 抽取 `学科` 分类答案清单，确认处理范围。
2. 逐题执行“回读 -> 最小改动 -> 当前题复检”。
3. 跑 `python xuanheng_check_detailed.py`。
4. 跑 `python scripts/validate_global_hint_rules_v1.py`。
5. 如无系统层异常信号，输出第一轮总结；如有，转入玄衡分数诊断流。
