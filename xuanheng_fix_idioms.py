
#!/usr/bin/env python3
"""
玄衡 - 专门修复成语分类
"""

import json
import os
import random

# ==================== 路径配置 ====================
PROJECT_ROOT = "/Volumes/新/work/flutter/guess"
PUZZLES_PATH = os.path.join(PROJECT_ROOT, "assets/puzzles.json")
TMP_DIR = os.path.join(PROJECT_ROOT, "tmp")

# ==================== 成语专用hint池 ====================
IDIOM_HINTS_WEAK = [
    # 极弱（30%左右）
    "四字", "常用", "典故", "比喻", "故事",
    "经典", "古老", "传统", "常用语",
]

IDIOM_HINTS_MEDIUM = [
    # 中等（40-60%）
    "智慧", "道理", "教训", "寓意",
    "形容", "描述", "生动", "形象",
]

IDIOM_HINTS_MEDIUM_STRONG = [
    # 中强（70-80%）
    "行为", "态度", "方式", "情景",
    "现象", "结果", "状态", "情境",
]

IDIOM_STRONG_ANCHORS = [
    # 第7条（90%以上）
    "两全其美", "坐等意外", "依序进行",
    "只爱空谈", "假装听不见", "疑神疑鬼",
    "同伙作恶", "末尾一笔", "无用之物",
]

def main():
    print("="*80)
    print("🚀 玄衡 - 修复成语分类！")
    print("="*80)
    
    # 加载谜题
    with open(PUZZLES_PATH, "r", encoding="utf-8") as f:
        puzzles = json.load(f)
    print(f"✅ 共 {len(puzzles)} 个谜题")
    
    # 找到所有成语分类的谜题
    idiom_puzzles = []
    idiom_answers = set()
    for idx, puzzle in enumerate(puzzles):
        if puzzle["category"] == "成语":
            idiom_puzzles.append((idx, puzzle))
            idiom_answers.add(puzzle["answer"])
    print(f"✅ 找到 {len(idiom_puzzles)} 个成语谜题")
    
    # 收集所有已有hint，避免重复
    all_existing_hints = set()
    for puzzle in puzzles:
        for hint in puzzle["hints"]:
            all_existing_hints.add(hint)
    
    # 修复每个成语谜题
    fixed_count = 0
    for idx, puzzle in idiom_puzzles:
        answer = puzzle["answer"]
        category = puzzle["category"]
        
        # 生成新的hints
        new_hints = generate_idiom_hints(
            answer, all_existing_hints, idiom_answers
        )
        
        # 更新谜题
        if new_hints != puzzle["hints"]:
            puzzles[idx]["hints"] = new_hints
            # 更新已存在的hint集合
            for hint in new_hints:
                all_existing_hints.add(hint)
            fixed_count += 1
            print(f"✅ 修复: {answer}")
    
    # 保存
    with open(PUZZLES_PATH, "w", encoding="utf-8") as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 保存成功！")
    print(f"✅ 修复了 {fixed_count} 个成语谜题！")

def generate_idiom_hints(answer, all_existing_hints, idiom_answers):
    """为成语生成合规的hints"""
    hints = []
    used = set()
    
    # 第1条（30%）- 极弱
    pool1 = IDIOM_HINTS_WEAK.copy()
    random.shuffle(pool1)
    for h in pool1:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            used.add(h)
            break
    if len(hints) < 1:
        hints.append("四字")
    
    # 第2条（40%）- 弱
    pool2 = IDIOM_HINTS_WEAK.copy()
    random.shuffle(pool2)
    for h in pool2:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            used.add(h)
            break
    if len(hints) < 2:
        hints.append("常用")
    
    # 第3条（50%）- 中
    pool3 = IDIOM_HINTS_MEDIUM.copy()
    random.shuffle(pool3)
    for h in pool3:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            used.add(h)
            break
    if len(hints) < 3:
        hints.append("道理")
    
    # 第4条（60%）- 中
    pool4 = IDIOM_HINTS_MEDIUM.copy()
    random.shuffle(pool4)
    for h in pool4:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            used.add(h)
            break
    if len(hints) < 4:
        hints.append("形容")
    
    # 第5条（70%）- 中强
    pool5 = IDIOM_HINTS_MEDIUM_STRONG.copy()
    random.shuffle(pool5)
    for h in pool5:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            used.add(h)
            break
    if len(hints) < 5:
        hints.append("行为")
    
    # 第6条（80%）- 中强
    pool6 = IDIOM_HINTS_MEDIUM_STRONG.copy()
    random.shuffle(pool6)
    for h in pool6:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            used.add(h)
            break
    if len(hints) < 6:
        hints.append("状态")
    
    # 第7条（90%）- 强
    # 先尝试保持原来的第7条（如果合适）
    # 否则用强锚点
    pool7 = IDIOM_STRONG_ANCHORS.copy()
    random.shuffle(pool7)
    found = False
    for h in pool7:
        if (h not in all_existing_hints 
            and h not in used 
            and h not in idiom_answers
            and not has_common_chars(h, answer)):
            hints.append(h)
            found = True
            break
    if not found:
        hints.append("经典")
    
    return hints

def has_common_chars(text1, text2):
    """检查两个文本是否有共同字符"""
    if not text1 or not text2:
        return False
    return any(c in text2 for c in text1)

if __name__ == "__main__":
    main()

