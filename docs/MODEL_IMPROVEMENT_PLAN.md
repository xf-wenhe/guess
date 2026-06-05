# 语义模型持续改进方案

## 目标
让每次夜间训练都能让模型有实质性成长,特别是:
- 同义词对(诸葛亮/孔明)达到 90%+
- 近义词对(医生/大夫)达到 75-85%
- 完全无关对(猫咪/刘备)低于 15%

## 核心问题诊断

### 1. 金标锚点数量不足
当前 `gold_v26_manual_anchor.csv` 只有约 100 条(含自匹配锚点),真正的人工标注对只有约 28 条,远不足以覆盖中文语义的复杂性。

### 2. 无监督数据缺乏语义信号
当前无监督训练使用 `MultipleNegativesRankingLoss`,但生成的词对缺乏明确的相似度标签,只是简单的 answer-hint 配对。

### 3. 训练策略过于保守
- 学习率 3e-6 太低
- 仅训练 1600 对数据
- 每次只训练 1 epoch

## 必须先准备的资产

在继续加轮次、加数据、换模型之前，先准备下面三样。否则训练只能整体漂移，不能精准修复离谱输出。

1. 分数标注规范
- 文件: `docs/SEMANTIC_LABELING_SPEC_V1.md`
- 用途: 统一 0-100 分的自然语义标尺，避免同一类错误今天打 20、明天打 55。

2. 失败样本回收表
- 文件: `data/semantic_error_review_template_v1.csv`
- 用途: 把线上离谱高分/低分样本沉淀成可审核、可合入训练的数据。

3. 冻结评测表
- 文件: `data/semantic_holdout_template_v1.csv`
- 用途: 作为不参与训练和校准的稳定 holdout，防止“越训越会做旧题”。

推荐执行顺序:
1. 先用 `semantic_error_review_template_v1.csv` 回收 100 条真实坏例。
2. 按 `SEMANTIC_LABELING_SPEC_V1.md` 审核 corrected_score 和 error_type。
3. 从中抽 20%-30% 放入 holdout，其余再考虑并入 train/anchor。

## 改进方案

### 方案 A: 主动学习 + 金标扩充 (强烈推荐) ⭐⭐⭐⭐⭐

#### 步骤 1: 自动发现困难样本
每次训练后,识别模型预测与预期差距最大的样本:

```python
# scripts/mine_hard_cases_v28.py
"""
从真实用户输入中找出模型预测不准确的案例
优先级:
1. 同义词但预测相似度 < 70% (诸葛亮/孔明 -> 65%)
2. 无关词但预测相似度 > 20% (猫咪/刘备 -> 45%)
3. 相关词但预测偏差 > 15% (火影/海贼王 -> 30% 实际应该 65%)
"""

import csv
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

MODEL_PATH = 'models/bge-m3-finetuned-v27-semreal-anchor'
USER_INPUT_CSV = 'data/semantic_scoring_user_input_template.csv'
OUTPUT_CSV = 'data/hard_cases_for_review_v28.csv'
ANGLES = ['从含义角度看：', '从用途角度看：', '从场景角度看：', '从特征角度看：', '从关联角度看：']

def semantic_similarity(model, w1, w2):
    scores = []
    for angle in ANGLES:
        v1 = model.encode([f'{angle}{w1}'], normalize_embeddings=True)[0]
        v2 = model.encode([f'{angle}{w2}'], normalize_embeddings=True)[0]
        scores.append(float((v1 * v2).sum()))
    scores.sort()
    return sum(scores[1:-1]) / len(scores[1:-1]) * 100

def main():
    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)
    
    rows = []
    with open(USER_INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            answer = row['answer'].strip()
            user_input = row['user_input'].strip()
            expected_score = float(row['score_0_100'])
            
            predicted = semantic_similarity(model, answer, user_input)
            error = abs(predicted - expected_score)
            
            # 标记困难样本
            if error > 15:
                rows.append({
                    'answer': answer,
                    'user_input': user_input,
                    'expected_score': expected_score,
                    'predicted_score': round(predicted, 2),
                    'error': round(error, 2),
                    'priority': 'high' if error > 25 else 'medium',
                    'review_status': 'pending',
                    'corrected_score': '',
                    'notes': ''
                })
    
    # 按错误从大到小排序
    rows.sort(key=lambda x: x['error'], reverse=True)
    
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows[:100])  # 输出前 100 个最困难的样本
    
    print(f'已输出 {len(rows[:100])} 个困难样本到 {OUTPUT_CSV}')
    print(f'请人工审核并填写 corrected_score 和 notes 列')

if __name__ == '__main__':
    main()
```

#### 步骤 2: 人工审核困难样本
定期(每周)审核 `hard_cases_for_review_v28.csv`:
- 确认 `corrected_score` (正确的相似度)
- 添加 `notes` (为什么模型错了)
- 将 `review_status` 改为 `approved`

#### 步骤 3: 合并到金标锚点
```python
# scripts/merge_reviewed_to_anchor_v28.py
"""
将审核通过的困难样本合并到 gold_v26_manual_anchor.csv
"""
import csv
from pathlib import Path

REVIEWED_CSV = 'data/hard_cases_for_review_v28.csv'
ANCHOR_CSV = 'data/gold_v26_manual_anchor.csv'

def main():
    # 读取已审核样本
    new_anchors = []
    with open(REVIEWED_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['review_status'] != 'approved':
                continue
            if not row['corrected_score']:
                continue
            
            score = int(float(row['corrected_score']))
            new_anchors.append({
                'id': '',
                'answer': row['answer'],
                'user_input': row['user_input'],
                'answer_category': '',
                'input_category_guess': '',
                'relation_tag': relation_for_score(score),
                'expected_range': f'{max(0, score-5)}-{min(100, score+5)}',
                'score_0_100': str(score),
                'reason': f"主动学习困难样本: {row['notes']}",
                'reviewer': 'active_learning_v28'
            })
    
    # 读取现有锚点
    existing = []
    with open(ANCHOR_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        existing = list(reader)
    
    # 去重合并
    seen = {(r['answer'], r['user_input']) for r in existing}
    for anchor in new_anchors:
        key = (anchor['answer'], anchor['user_input'])
        if key not in seen:
            existing.append(anchor)
            seen.add(key)
    
    # 重新编号并写回
    for i, row in enumerate(existing, start=1):
        row['id'] = str(i)
    
    with open(ANCHOR_CSV, 'w', encoding='utf-8', newline='') as f:
        fieldnames = existing[0].keys()
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)
    
    print(f'新增 {len(new_anchors)} 个锚点,总计 {len(existing)} 个')

def relation_for_score(score: int) -> str:
    if score >= 85:
        return 'alias_synonym_high'
    if score >= 70:
        return 'near_synonym_high'
    if score >= 50:
        return 'related_mid'
    if score >= 30:
        return 'related_low'
    return 'hard_negative_low'

if __name__ == '__main__':
    main()
```

### 方案 B: 改进无监督训练数据质量 ⭐⭐⭐⭐

当前无监督数据从 puzzles 生成,但缺乏语义关系标签。改进:

```python
# scripts/build_v27_semisup_pairs.py
"""
生成带有伪标签的半监督训练对
使用启发式规则 + 当前模型预测
"""
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

PUZZLES_JSON = Path('assets/puzzles.json')
OUTPUT_JSONL = Path('data/semisupervised_pairs_v27.jsonl')
MODEL_PATH = 'models/bge-m3-finetuned-v27-semreal-anchor'

def main():
    model = SentenceTransformer(MODEL_PATH, device='cpu', local_files_only=True)
    
    puzzles = json.loads(PUZZLES_JSON.read_text(encoding='utf-8'))
    pairs = []
    
    for puzzle in puzzles:
        answer = puzzle['answer']
        hints = puzzle.get('hints', [])
        
        # 1. answer 自匹配 (100% 相似)
        pairs.append({
            'text_a': answer,
            'text_b': answer,
            'similarity': 1.0,
            'source': 'self_match'
        })
        
        # 2. answer vs hints (需要模型预测相似度)
        for hint in hints[:3]:  # 只用前3个高质量提示
            if len(hint) < 2 or len(hint) > 6:
                continue
            
            # 使用当前模型预测作为伪标签
            sim = semantic_similarity(model, answer, hint)
            
            # 只保留高质量对 (避免引入噪声)
            if sim > 0.6 or sim < 0.2:  # 明确相关或明确无关
                pairs.append({
                    'text_a': answer,
                    'text_b': hint,
                    'similarity': sim,
                    'source': 'pseudo_label'
                })
    
    # 3. 同类别 puzzles 互为正样本
    from collections import defaultdict
    category_map = defaultdict(list)
    for puzzle in puzzles:
        category = puzzle.get('category', '其他')
        if category not in ['其他', '']:
            category_map[category].append(puzzle['answer'])
    
    for category, answers in category_map.items():
        if len(answers) < 2:
            continue
        for i, a1 in enumerate(answers):
            for a2 in answers[i+1:i+6]:  # 每个词最多匹配5个同类
                sim = semantic_similarity(model, a1, a2)
                if sim > 0.3:  # 同类应该有一定相关性
                    pairs.append({
                        'text_a': a1,
                        'text_b': a2,
                        'similarity': sim,
                        'source': f'same_category_{category}'
                    })
    
    # 写入 JSONL
    with OUTPUT_JSONL.open('w', encoding='utf-8') as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + '\n')
    
    print(f'生成 {len(pairs)} 个半监督训练对')
    
    # 统计分布
    from collections import Counter
    source_dist = Counter(p['source'] for p in pairs)
    print('来源分布:', dict(source_dist))

def semantic_similarity(model, w1, w2):
    ANGLES = ['从含义角度看：', '从用途角度看：', '从场景角度看：', '从特征角度看：', '从关联角度看：']
    scores = []
    for angle in ANGLES:
        v1 = model.encode([f'{angle}{w1}'], normalize_embeddings=True)[0]
        v2 = model.encode([f'{angle}{w2}'], normalize_embeddings=True)[0]
        scores.append(float((v1 * v2).sum()))
    scores.sort()
    return sum(scores[1:-1]) / len(scores[1:-1])

if __name__ == '__main__':
    main()
```

然后修改预训练脚本使用 `CosineSimilarityLoss` 而不是 `MultipleNegativesRankingLoss`:

```python
# scripts/pretrain_v27_semisupervised.py (修改版)
from sentence_transformers import InputExample, SentenceTransformer, losses

def load_semisup_pairs(path):
    examples = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            examples.append(InputExample(
                texts=[item['text_a'], item['text_b']],
                label=float(item['similarity'])  # 使用相似度作为标签
            ))
    return examples

# 使用 CosineSimilarityLoss 进行回归训练
train_loss = losses.CosineSimilarityLoss(model)
```

### 方案 C: 调整夜间训练参数 (立即可用) ⭐⭐⭐

修改 `scripts/nightly_train_v26.sh` 或通过环境变量覆盖:

```bash
# 更激进的训练策略
export SEM_MAX_PAIRS=3000  # 从 1600 增加到 3000
export SEM_BATCH_SIZE=8
export SEM_EPOCHS=2  # 从 1 增加到 2
export SEM_WARMUP_STEPS=100  # 从 50 增加到 100
export SEM_LEARNING_RATE=5e-6  # 从 3e-6 增加到 5e-6

# 锚点微调使用更高学习率
export NIGHTLY_ANCHOR_LEARNING_RATE=3e-6  # 从 1.5e-6 增加到 3e-6
export NIGHTLY_ANCHOR_EPOCHS=2  # 增加到 2 轮

# 运行夜间训练
bash scripts/nightly_train_v26.sh
```

### 方案 D: 建立持续反馈循环 ⭐⭐⭐⭐

在 Flutter 应用中集成预测错误日志:

```dart
// lib/services/prediction_error_logger.dart
class PredictionErrorLogger {
  static const String logPath = 'data/prediction_errors_log_v28.jsonl';
  
  static Future<void> logError({
    required String answer,
    required String userInput,
    required int predictedScore,
    required int expectedMin,
    required int expectedMax,
    String? userFeedback,
  }) async {
    // 只记录预测超出合理范围的情况
    if (predictedScore >= expectedMin && predictedScore <= expectedMax) {
      return;
    }
    
    final entry = {
      'timestamp': DateTime.now().toIso8601String(),
      'answer': answer,
      'user_input': userInput,
      'predicted_score': predictedScore,
      'expected_min': expectedMin,
      'expected_max': expectedMax,
      'user_feedback': userFeedback,
      'error': predictedScore - (expectedMin + expectedMax) / 2,
    };
    
    final file = File(logPath);
    await file.writeAsString(
      '${jsonEncode(entry)}\n',
      mode: FileMode.append,
    );
  }
}
```

定期分析错误日志:

```python
# scripts/analyze_prediction_errors_v28.py
"""
分析生产环境中的预测错误,自动生成待审核列表
"""
import json
from pathlib import Path
from collections import Counter

ERROR_LOG = Path('data/prediction_errors_log_v28.jsonl')
OUTPUT_CSV = Path('data/errors_for_review_v28.csv')

def main():
    errors = []
    with ERROR_LOG.open('r', encoding='utf-8') as f:
        for line in f:
            errors.append(json.loads(line))
    
    # 按 (answer, user_input) 分组,计算平均误差
    from collections import defaultdict
    pair_errors = defaultdict(list)
    for e in errors:
        key = (e['answer'], e['user_input'])
        pair_errors[key].append(e['error'])
    
    # 计算每对的平均误差和出现频率
    rows = []
    for (answer, user_input), error_list in pair_errors.items():
        avg_error = sum(error_list) / len(error_list)
        count = len(error_list)
        rows.append({
            'answer': answer,
            'user_input': user_input,
            'avg_error': round(avg_error, 2),
            'count': count,
            'priority': 'high' if abs(avg_error) > 20 and count > 3 else 'medium',
        })
    
    # 按频率和误差排序
    rows.sort(key=lambda x: (x['priority'] == 'high', x['count'], abs(x['avg_error'])), reverse=True)
    
    import csv
    with OUTPUT_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows[:50])
    
    print(f'输出前 50 个高频错误对到 {OUTPUT_CSV}')

if __name__ == '__main__':
    main()
```

### 方案 E: 扩充领域专有知识 ⭐⭐⭐⭐⭐

当前金标锚点缺乏领域覆盖,需要系统性补充:

```python
# scripts/build_domain_anchors_v28.py
"""
构建领域专有知识锚点
"""

DOMAIN_ANCHORS = [
    # 历史人物 - 别名/字号
    ('诸葛亮', '孔明', 90),
    ('诸葛亮', '卧龙', 85),
    ('司马懿', '仲达', 90),
    ('关羽', '云长', 90),
    ('关羽', '武圣', 85),
    ('张飞', '翼德', 90),
    ('赵云', '子龙', 90),
    ('刘备', '玄德', 90),
    ('曹操', '孟德', 90),
    ('孙权', '仲谋', 90),
    ('周瑜', '公瑾', 90),
    ('吕布', '奉先', 90),
    ('李白', '太白', 90),
    ('杜甫', '子美', 90),
    ('苏轼', '东坡', 90),
    ('岳飞', '鹏举', 90),
    
    # 历史人物 - 称号/尊称
    ('孔子', '圣人', 80),
    ('孔子', '孔圣人', 90),
    ('老子', '道祖', 85),
    ('释迦牟尼', '佛陀', 90),
    ('关羽', '关公', 88),
    ('包拯', '包青天', 90),
    
    # 神话人物 - 别名
    ('孙悟空', '齐天大圣', 90),
    ('孙悟空', '弼马温', 85),
    ('孙悟空', '美猴王', 88),
    ('猪八戒', '天蓬元帅', 85),
    ('沙僧', '卷帘大将', 85),
    ('哪吒', '三太子', 85),
    ('二郎神', '杨戬', 90),
    
    # 动漫角色 - 别名
    ('柯南', '工藤新一', 85),
    ('怪盗基德', '黑羽快斗', 85),
    ('路飞', '蒙奇·D·路飞', 90),
    ('鸣人', '漩涡鸣人', 90),
    ('佐助', '宇智波佐助', 90),
    
    # 近义词 - 日常用语
    ('医生', '大夫', 80),
    ('老师', '教师', 80),
    ('学生', '学员', 75),
    ('高兴', '开心', 85),
    ('悲伤', '伤心', 85),
    ('愤怒', '生气', 85),
    ('美丽', '漂亮', 85),
    ('聪明', '智慧', 80),
    ('勇敢', '英勇', 80),
    
    # 近义词 - 动物昵称
    ('猫咪', '猫', 90),
    ('狗狗', '狗', 90),
    ('小猫', '猫', 85),
    ('小狗', '狗', 85),
    ('兔兔', '兔子', 90),
    
    # 食物 - 别名
    ('披萨', '比萨', 92),
    ('番茄', '西红柿', 90),
    ('土豆', '马铃薯', 90),
    ('玉米', '包谷', 85),
    
    # 地名 - 别名
    ('北京', '京城', 85),
    ('上海', '魔都', 80),
    ('成都', '蓉城', 85),
    ('杭州', '临安', 80),
    
    # 相关但非同义 - 历史事件
    ('关羽', '刮骨疗毒', 60),
    ('华佗', '刮骨疗毒', 62),
    ('刘备', '桃园结义', 65),
    ('关羽', '桃园结义', 65),
    ('张飞', '桃园结义', 65),
    ('诸葛亮', '草船借箭', 65),
    ('诸葛亮', '空城计', 65),
    ('曹操', '官渡之战', 60),
    ('赤壁', '赤壁之战', 68),
    
    # 相关但非同义 - 动漫关联
    ('火影', '海贼王', 60),
    ('死神', '火影', 58),
    ('柯南', '名侦探柯南', 90),
    ('柯南', '小兰', 55),
    ('路飞', '海贼王', 70),
    
    # 完全无关 - 硬负例
    ('猫咪', '刘备', 10),
    ('医生', '火影', 8),
    ('诸葛亮', '披萨', 5),
    ('李白', '寿司', 5),
    ('春节', '显卡', 5),
    ('地铁', '女娲', 5),
    ('计算机', '饺子', 5),
    ('钢琴', '火箭', 8),
]

def main():
    import csv
    output = []
    for i, (w1, w2, score) in enumerate(DOMAIN_ANCHORS, start=1):
        output.append({
            'id': str(i),
            'answer': w1,
            'user_input': w2,
            'answer_category': '',
            'input_category_guess': '',
            'relation_tag': relation_for_score(score),
            'expected_range': f'{max(0, score-5)}-{min(100, score+5)}',
            'score_0_100': str(score),
            'reason': '领域知识锚点',
            'reviewer': 'domain_expert_v28'
        })
        
        # 添加反向对
        output.append({
            'id': str(i * 10000),
            'answer': w2,
            'user_input': w1,
            'answer_category': '',
            'input_category_guess': '',
            'relation_tag': relation_for_score(score),
            'expected_range': f'{max(0, score-5)}-{min(100, score+5)}',
            'score_0_100': str(score),
            'reason': '领域知识锚点(反向)',
            'reviewer': 'domain_expert_v28'
        })
    
    with open('data/domain_anchors_v28.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output[0].keys())
        writer.writeheader()
        writer.writerows(output)
    
    print(f'生成 {len(output)} 个领域锚点(含反向)')

def relation_for_score(score: int) -> str:
    if score >= 85:
        return 'alias_synonym_high'
    if score >= 70:
        return 'near_synonym_high'
    if score >= 50:
        return 'related_mid'
    if score >= 30:
        return 'related_low'
    return 'hard_negative_low'

if __name__ == '__main__':
    main()
```

## 实施计划

### 第 1 周: 快速见效 (立即执行)
1. ✅ **扩充领域锚点** (方案 E)
   ```bash
   python scripts/build_domain_anchors_v28.py
   # 将 domain_anchors_v28.csv 合并到 gold_v26_manual_anchor.csv
   ```
   - 目标: 金标锚点从 100 条增加到 300+ 条
   
2. ✅ **调整夜间训练参数** (方案 C)
   ```bash
   export SEM_MAX_PAIRS=3000
   export SEM_EPOCHS=2
   export SEM_LEARNING_RATE=5e-6
   export NIGHTLY_ANCHOR_LEARNING_RATE=3e-6
   bash scripts/nightly_train_v26.sh
   ```

### 第 2 周: 主动学习
1. ✅ 实现困难样本挖掘 (方案 A 步骤 1)
   ```bash
   python scripts/mine_hard_cases_v28.py
   ```
   
2. ✅ 人工审核前 100 个困难样本
   - 每天审核 20-30 个
   - 确保 corrected_score 准确
   
3. ✅ 合并到金标锚点
   ```bash
   python scripts/merge_reviewed_to_anchor_v28.py
   ```

### 第 3-4 周: 半监督训练
1. ✅ 生成高质量半监督训练对 (方案 B)
   ```bash
   python scripts/build_v27_semisup_pairs.py
   ```
   
2. ✅ 修改训练脚本使用 CosineSimilarityLoss
   
3. ✅ 建立预测错误日志系统 (方案 D)
   - Flutter 端集成错误记录
   - 后端定期分析错误日志

### 长期(持续)
- **每周**: 审核 20-50 个困难样本
- **每月**: 扩充 50-100 个领域锚点
- **季度目标**: 金标锚点达到 500+ 条
- **年度目标**: 金标锚点达到 1000+ 条

## 预期效果

### 当前 (v27)
- 诸葛亮/孔明: ~65-75%
- 医生/大夫: ~70-75%
- 猫咪/刘备: ~15-25%
- 金标锚点: ~100 条

### 1 周后 (快速见效阶段)
- 诸葛亮/孔明: ~85-90% ✅
- 医生/大夫: ~78-83%
- 猫咪/刘备: ~8-12%
- 金标锚点: ~300 条

### 1 个月后 (主动学习 + 半监督)
- 诸葛亮/孔明: ~90-95% ✅✅
- 医生/大夫: ~82-88%
- 猫咪/刘备: ~5-10%
- 金标锚点: ~500 条

### 3 个月后 (持续改进)
- 同义词对准确率: > 95%
- 近义词对准确率: > 85%
- 无关对准确率: < 5%
- 金标锚点: ~800 条

## 监控指标

每次夜间训练后,自动输出:

1. **校准指标**:
   - `cal_mae` (校准后平均绝对误差) - 目标: < 8.0
   - `cal_bucket_acc` (分桶准确率) - 目标: > 75%

2. **回归测试**:
   - 回归测试通过率 - 目标: fixed regression 全部通过

3. **同义词专项评估** (新增):
   ```python
   # scripts/eval_v28_synonym_accuracy.py
   """
   专门评估同义词对的准确率
   """
   SYNONYM_PAIRS = [
       ('诸葛亮', '孔明', 85, 95),
       ('孙悟空', '齐天大圣', 85, 95),
       ('医生', '大夫', 75, 85),
       ('猫咪', '猫', 85, 95),
       ('披萨', '比萨', 85, 95),
       ('高兴', '开心', 80, 90),
       # ... 更多同义词对
   ]

   def evaluate_synonym_accuracy(model, calib_x, calib_y):
       correct = 0
       total = len(SYNONYM_PAIRS)
       
       for w1, w2, min_score, max_score in SYNONYM_PAIRS:
           pred = predict_with_calibration(model, w1, w2, calib_x, calib_y)
           if min_score <= pred <= max_score:
               correct += 1
               print(f'✅ {w1}/{w2}: {pred:.1f}')
           else:
               print(f'❌ {w1}/{w2}: 预测={pred:.1f}, 期望=[{min_score}, {max_score}]')
       
       accuracy = correct / total * 100
       print(f'\n同义词准确率: {accuracy:.1f}% ({correct}/{total})')
       return accuracy
   ```

4. **金标锚点增长追踪**:
   ```bash
   wc -l data/gold_v26_manual_anchor.csv
   ```

## 关键成功因素

1. **持续的人工审核**: 每周至少审核 20-50 个样本
2. **快速迭代**: 每完成一批锚点扩充,立即重新训练验证
3. **分层覆盖**: 确保同义词、近义词、相关词、无关词各层级都有充足样本
4. **领域知识**: 系统性补充历史、神话、动漫、日常用语等领域
5. **质量控制**: 人工审核时要严格把关,避免引入错误标签

## 参考文献

- 当前锚点: `data/gold_v26_manual_anchor.csv`
- 回归测试: `data/regression_pairs_v23.json`
- 夜间训练: `scripts/nightly_train_v26.sh`
- 模型评估: `scripts/eval_v26_gold.py`
