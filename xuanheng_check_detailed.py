
#!/usr/bin/env python3
"""
玄衡 - 严格按照 SKILL.md 完整详细检查
"""

import json
import os

# ==================== 路径 ====================
PROJECT_ROOT = "/Volumes/新/work/flutter/guess"
PUZZLES_PATH = os.path.join(PROJECT_ROOT, "assets/puzzles.json")
SKILL_PATH = os.path.join(PROJECT_ROOT, ".github/skills/puzzle-management/SKILL.md")


def main():
    print("="*80)
    print("🚀 玄衡 - 严格按照 SKILL 完整详细检查")
    print("="*80)
    
    # 1. 读取SKILL确认规则
    print("\n[1/5] 读取 SKILL 规则...")
    with open(SKILL_PATH, "r", encoding="utf-8") as f:
        skill_content = f.read()
    print("✅ SKILL 规则已读取")
    
    # 2. 读取谜题
    print("\n[2/5] 读取谜题...")
    with open(PUZZLES_PATH, "r", encoding="utf-8") as f:
        puzzles = json.load(f)
    print(f"✅ 读取 {len(puzzles)} 个谜题")
    
    # 3. 筛选成语谜题
    idiom_puzzles = []
    for idx, puzzle in enumerate(puzzles):
        if puzzle["category"] == "成语":
            idiom_puzzles.append((idx, puzzle))
    print(f"✅ 找到 {len(idiom_puzzles)} 个成语谜题")
    
    # 4. 逐条严格检查！
    print("\n[3/5] 逐条严格检查（按照 SKILL 规则）...")
    all_issues = check_all_puzzles(idiom_puzzles, puzzles)
    
    # 5. 报告结果
    print("\n" + "="*80)
    print("📊 检查结果报告")
    print("="*80)
    
    if not all_issues:
        print("✅ 检查完毕，没有发现问题！")
    else:
        print(f"❌ 发现 {len(all_issues)} 个问题！")
        
        # 分类统计
        type_counts = {}
        for issue in all_issues:
            t = issue["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        
        print("\n📋 问题分类统计：")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"   - {t}: {count} 个问题")
        
        print("\n🔍 详细问题列表（前20个）：")
        for i, issue in enumerate(all_issues[:20]):
            print(f"\n   {i+1}. [{issue['type']}]")
            print(f"      谜题：{issue['answer']} (index: {issue['idx']})")
            if "hint_idx" in issue:
                print(f"      位置：hint {issue['hint_idx']+1} ({issue.get('hint', '')})")
            print(f"      说明：{issue['message']}")
    
    print("\n" + "="*80)


def check_all_puzzles(idiom_puzzles, all_puzzles):
    """严格检查所有成语谜题"""
    issues = []
    
    # 收集所有hints（用于唯一性检查）
    all_hints = set()
    category_hints = {}
    for puzzle in all_puzzles:
        category = puzzle["category"]
        if category not in category_hints:
            category_hints[category] = set()
        for hint in puzzle["hints"]:
            all_hints.add(hint)
            category_hints[category].add(hint)
    
    # 检查每个成语谜题
    for idx, puzzle in idiom_puzzles:
        answer = puzzle["answer"]
        category = puzzle["category"]
        hints = puzzle["hints"]
        
        # ==========================================
        # 1. 字面隔离检查（SKILL核心规则）
        # ==========================================
        for i, hint in enumerate(hints):
            if has_common_chars(hint, answer):
                issues.append({
                    "type": "字面泄露",
                    "idx": idx,
                    "answer": answer,
                    "hint_idx": i,
                    "hint": hint,
                    "message": f"hint 与 answer 有共同字符"
                })
        
        # ==========================================
        # 2. 元描述/模板词检查
        # ==========================================
        meta_words = [
            "情感张力", "叙事线索", "能力设定", "阵营对抗", "羁绊情深", "虚构世界",
            "故事主线", "角色关系", "主题思想", "艺术风格", "创作背景", "文化内涵",
            "象征意义", "表达手法", "叙事结构", "情感表达", "情节发展", "人物塑造",
            "场景线索", "故事推进", "冲突升级", "成长历程", "冒险旅程", "世界设定",
            "典故来源", "固定词组", "比喻含义", "引申凝练", "搭配贴切", "句式紧凑",
            "义理凝练", "文势鲜明", "体例凝练", "义理有序", "文脉准确", "格律完整",
            "义理严谨", "格律鲜明", "底细见光", "文脉规整", "书面丰富", "意象凝练",
            "表达精当", "比拟常见", "意象有序", "文脉顺畅", "范式凝练", "义理紧凑",
            "格律贴切", "体例稳健", "文脉丰富", "表达有序", "比拟精当", "书面常见",
            "先定规则", "如同白说", "书面清楚", "句式丰富", "搭配常见", "表达鲜明",
            "比拟严谨", "意象准确", "搭配有序", "引申稳健", "句式精当", "搭配凝练",
            "修辞顺畅", "引申有力", "典源凝练", "典源紧凑", "表达稳健", "引申精当",
            "比拟有序", "搭配清楚", "句式得当", "文脉周全", "范式周全", "格律稳健",
            "义理有力", "典源有力", "修辞贴切", "字义顺畅", "引申鲜明", "修辞凝练",
            "字义稳健", "修辞有序", "典源鲜明"
        ]
        for i, hint in enumerate(hints):
            # 检查是否是元描述
            for meta in meta_words:
                if meta in hint:
                    issues.append({
                        "type": "元描述/模板词",
                        "idx": idx,
                        "answer": answer,
                        "hint_idx": i,
                        "hint": hint,
                        "message": f"hint 包含元描述或模板词 '{meta}'"
                    })
        
        # ==========================================
        # 3. 同题唯一性检查
        # ==========================================
        if len(set(hints)) != len(hints):
            issues.append({
                "type": "同题重复",
                "idx": idx,
                "answer": answer,
                "message": f"同题内有重复 hints"
            })
        
        # ==========================================
        # 4. 同分类唯一性检查
        # ==========================================
        category_used = set()
        for i, hint in enumerate(hints):
            count = 0
            for p in all_puzzles:
                if p["category"] == category and hint in p["hints"]:
                    count += 1
            
            if count > 1:
                issues.append({
                    "type": "同分类重复",
                    "idx": idx,
                    "answer": answer,
                    "hint_idx": i,
                    "hint": hint,
                    "message": f"hint 在同分类 {count} 个谜题中出现"
                })
        
        # ==========================================
        # 5. 全局唯一性检查
        # ==========================================
        global_used = set()
        for i, hint in enumerate(hints):
            count = 0
            for p in all_puzzles:
                if hint in p["hints"]:
                    count += 1
            
            if count > 1:
                issues.append({
                    "type": "全局重复",
                    "idx": idx,
                    "answer": answer,
                    "hint_idx": i,
                    "hint": hint,
                    "message": f"hint 在全局 {count} 个谜题中出现"
                })
        
        # ==========================================
        # 6. hint数量检查
        # ==========================================
        if len(hints) != 7:
            issues.append({
                "type": "hint数量错误",
                "idx": idx,
                "answer": answer,
                "message": f"应该有7个hint，当前有{len(hints)}个"
            })
    
    return issues


def has_common_chars(text1, text2):
    """检查两个文本是否有共同字符"""
    if not text1 or not text2:
        return False
    return any(c in text2 for c in text1)


if __name__ == "__main__":
    main()

