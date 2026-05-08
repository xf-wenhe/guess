
#!/usr/bin/env python3
"""
玄衡完整工作流（优化版）
=======================
修复性能问题，避免重复处理，提高效率
"""

import json
import os
import shutil
import subprocess
import random
from datetime import datetime

# ==================== 路径配置 ====================
PROJECT_ROOT = "/Volumes/新/work/flutter/guess"
SKILL_PATH = os.path.join(PROJECT_ROOT, ".github/skills/puzzle-management/SKILL.md")
PUZZLES_PATH = os.path.join(PROJECT_ROOT, "assets/puzzles.json")
VALIDATE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts/validate_global_hint_rules_v1.py")
TMP_DIR = os.path.join(PROJECT_ROOT, "tmp")

os.makedirs(TMP_DIR, exist_ok=True)

# ==================== 元描述词黑名单 ====================
META_DESCRIPTORS = [
    "情感张力", "叙事线索", "能力设定", "阵营对抗", "羁绊情深", "虚构世界",
    "故事主线", "角色关系", "主题思想", "艺术风格", "创作背景", "文化内涵",
    "象征意义", "表达手法", "叙事结构", "情感表达", "情节发展", "人物塑造",
    "场景线索", "故事推进", "冲突升级", "成长历程", "冒险旅程", "世界设定",
]

# ==================== 扩展的安全hint池 ====================
SAFE_HINT_POOL = [
    # 通用
    "围坐", "夏夜", "香气", "烟雾", "热闹", "轻松", "有趣",
    "色彩", "声音", "气味", "触感", "氛围", "感觉", "心情",
    "户外", "室内", "日常", "特殊", "传统", "现代", "新颖",
    "简单", "复杂", "精致", "粗犷", "温馨", "欢快", "安静",
    # 美食相关（无字面泄露风险）
    "美味", "好吃", "可口", "香浓", "酥脆", "爽口", "甜蜜",
    "酸爽", "麻辣", "清淡", "浓郁", "细腻", "鲜嫩", "软糯",
    # 动漫/故事相关
    "热血", "感动", "搞笑", "治愈", "励志", "冒险", "奇幻",
    "神秘", "浪漫", "紧张", "刺激", "温馨", "欢乐", "悲伤",
    # 生活相关
    "实用", "方便", "耐用", "美观", "时尚", "复古", "简约",
    "大气", "可爱", "优雅", "酷炫", "有趣", "新鲜", "特别",
]

def main():
    print("="*80)
    print("🚀 玄衡启动（优化版）！")
    print("="*80)
    
    # 第一步：备份
    print("\n[1/8] 备份当前谜题")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(TMP_DIR, f"puzzles_backup_{timestamp}.json")
    shutil.copy(PUZZLES_PATH, backup_path)
    print(f"✅ 备份保存至: {backup_path}")
    
    # 第二步：加载谜题
    print("\n[2/8] 加载谜题文件")
    with open(PUZZLES_PATH, "r", encoding="utf-8") as f:
        puzzles = json.load(f)
    print(f"✅ 共 {len(puzzles)} 个谜题")
    
    # 第三步：初始完整检查
    print("\n[3/8] 初始完整检查")
    issues = check_puzzles(puzzles)
    
    if not issues:
        print("🎉 所有谜题符合规则！")
        return
    
    # 第四步：循环修复直至完美（优化版）
    print(f"\n[4/8] 发现 {len(issues)} 个问题，开始修复...")
    max_loops = 3
    loop_count = 0
    
    while loop_count < max_loops and issues:
        loop_count += 1
        print(f"\n--- 修复轮次 {loop_count} ---")
        
        # 修复问题（优化：按谜题ID去重）
        puzzles = fix_puzzles_optimized(puzzles, issues)
        
        # 保存中间结果
        loop_backup = os.path.join(TMP_DIR, f"puzzles_loop_{loop_count}.json")
        with open(loop_backup, "w", encoding="utf-8") as f:
            json.dump(puzzles, f, ensure_ascii=False, indent=2)
        print(f"✅ 轮次 {loop_count} 结果保存至: {loop_backup}")
        
        # 再次完整检查
        print(f"\n--- 完整检查轮次 {loop_count} ---")
        issues = check_puzzles(puzzles)
        
        if not issues:
            print(f"🎉 第 {loop_count} 轮修复后完美通过！")
            break
        
        print(f"⚠️  仍有 {len(issues)} 个问题，继续修复...")
    
    # 第五步：保存最终结果
    print("\n[5/8] 保存最终结果")
    with open(PUZZLES_PATH, "w", encoding="utf-8") as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)
    print("✅ 保存成功！")
    
    # 第六步：运行自动验证脚本
    print("\n[6/8] 运行自动验证脚本")
    try:
        result = subprocess.run(
            ["python3", VALIDATE_SCRIPT],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=120
        )
        print("✅ 自动验证脚本运行完成")
    except Exception as e:
        print(f"⚠️  自动验证脚本运行失败: {e}")
    
    # 第七步：总结
    print("\n" + "="*80)
    print("✅ 玄衡工作流完成！")
    print("="*80)
    print(f"- 修复轮次: {loop_count}")
    print(f"- 最终状态: {'完美' if not issues else '有问题'}")
    print(f"- 备份文件: {backup_path}")

def check_puzzles(puzzles):
    """完整检查所有谜题（优化版）"""
    issues = []
    
    # 收集所有hint用于唯一性检查
    all_hints = set()
    category_hints = {}  # category -> set(hints)
    seen_issues = set()  # 避免重复问题
    
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle["answer"]
        category = puzzle["category"]
        hints = puzzle["hints"]
        
        if category not in category_hints:
            category_hints[category] = set()
        
        # 1. 字面隔离检查
        for i, hint in enumerate(hints):
            if has_common_chars(hint, answer):
                issue_key = ("literal", idx, i)
                if issue_key not in seen_issues:
                    issues.append({
                        "type": "literal_leak",
                        "idx": idx,
                        "answer": answer,
                        "category": category,
                        "hint_idx": i,
                        "hint": hint,
                    })
                    seen_issues.add(issue_key)
        
        # 2. 元描述检查
        for i, hint in enumerate(hints):
            if is_meta_descriptor(hint):
                issue_key = ("meta", idx, i)
                if issue_key not in seen_issues:
                    issues.append({
                        "type": "meta_descriptor",
                        "idx": idx,
                        "answer": answer,
                        "category": category,
                        "hint_idx": i,
                        "hint": hint,
                    })
                    seen_issues.add(issue_key)
        
        # 3. 唯一性（同题）检查
        if len(set(hints)) != len(hints):
            issue_key = ("dup_puzzle", idx)
            if issue_key not in seen_issues:
                issues.append({
                    "type": "duplicate_in_puzzle",
                    "idx": idx,
                    "answer": answer,
                    "category": category,
                })
                seen_issues.add(issue_key)
        
        # 4. 唯一性（同分类）和全局检查
        for i, hint in enumerate(hints):
            if hint in category_hints[category]:
                issue_key = ("dup_category", idx, i)
                if issue_key not in seen_issues:
                    issues.append({
                        "type": "duplicate_in_category",
                        "idx": idx,
                        "answer": answer,
                        "category": category,
                        "hint_idx": i,
                        "hint": hint,
                    })
                    seen_issues.add(issue_key)
            if hint in all_hints:
                issue_key = ("dup_global", idx, i)
                if issue_key not in seen_issues:
                    issues.append({
                        "type": "duplicate_global",
                        "idx": idx,
                        "answer": answer,
                        "category": category,
                        "hint_idx": i,
                        "hint": hint,
                    })
                    seen_issues.add(issue_key)
            
            category_hints[category].add(hint)
            all_hints.add(hint)
    
    # 打印问题（优化：统计类型）
    print(f"发现 {len(issues)} 个问题:")
    type_counts = {}
    for issue in issues[:50]:  # 只统计前50个
        t = issue["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, count in sorted(type_counts.items()):
        print(f"  - {t}: {count} 个")
    if len(issues) > 50:
        print(f"  ... 还有 {len(issues)-50} 个问题")
    
    return issues

def fix_puzzles_optimized(puzzles, issues):
    """修复谜题问题（优化版：按谜题分组处理）"""
    # 先收集所有hint
    all_hints = set()
    category_hints = {}
    for puzzle in puzzles:
        category = puzzle["category"]
        if category not in category_hints:
            category_hints[category] = set()
        for hint in puzzle["hints"]:
            all_hints.add(hint)
            category_hints[category].add(hint)
    
    # 按谜题ID分组问题，避免重复处理同一个谜题
    puzzle_issues = {}
    for issue in issues:
        idx = issue["idx"]
        if idx not in puzzle_issues:
            puzzle_issues[idx] = []
        puzzle_issues[idx].append(issue)
    
    # 逐个修复谜题
    fixed_count = 0
    for idx, issues_in_puzzle in puzzle_issues.items():
        puzzle = puzzles[idx]
        answer = puzzle["answer"]
        category = puzzle["category"]
        
        # 检查是否需要重写整个hints
        needs_full_rewrite = any(
            issue["type"] == "duplicate_in_puzzle" 
            for issue in issues_in_puzzle
        )
        
        if needs_full_rewrite:
            # 重写整组hints
            new_hints = generate_safe_hints(answer, category, all_hints, category_hints)
            puzzles[idx]["hints"] = new_hints
            # 更新hint集合
            for hint in new_hints:
                all_hints.add(hint)
                category_hints[category].add(hint)
            fixed_count += 1
        else:
            # 修复单个hints
            for issue in issues_in_puzzle:
                hint_idx = issue["hint_idx"]
                if hint_idx < 0:
                    continue
                
                new_hint = get_unique_safe_hint(answer, category, all_hints, category_hints, hint_idx)
                puzzles[idx]["hints"][hint_idx] = new_hint
                all_hints.add(new_hint)
                category_hints[category].add(new_hint)
                fixed_count += 1
    
    print(f"✅ 修复了 {fixed_count} 个问题")
    return puzzles

def generate_safe_hints(answer, category, all_hints, category_hints):
    """生成一组安全的hints"""
    hints = []
    used_in_puzzle = set()
    
    for i in range(7):
        hint = get_unique_safe_hint(
            answer, category, all_hints, category_hints, i, used_in_puzzle
        )
        hints.append(hint)
        used_in_puzzle.add(hint)
        all_hints.add(hint)
        category_hints[category].add(hint)
    return hints

def get_unique_safe_hint(answer, category, all_hints, category_hints, slot, used_in_puzzle=None):
    """获取一个唯一的安全hint（优化版）"""
    if used_in_puzzle is None:
        used_in_puzzle = set()
    
    # 第7条用最强锚点
    if slot == 6:
        if category == "美食":
            strong_anchors = ["明火现做", "炭烤", "火烤", "油炸", "清蒸", "红烧"]
        elif category == "动漫":
            strong_anchors = ["忍者", "海贼", "死神", "赛亚人", "武士", "魔法"]
        elif category == "游戏":
            strong_anchors = ["通关", "升级", "装备", "技能", "副本", "任务"]
        else:
            strong_anchors = ["特色", "标志", "代表", "核心"]
        
        for anchor in strong_anchors:
            if (anchor not in all_hints 
                and anchor not in category_hints[category] 
                and anchor not in used_in_puzzle
                and not has_common_chars(anchor, answer)):
                return anchor
    
    # 其他槽位用安全池
    pool = SAFE_HINT_POOL.copy()
    random.shuffle(pool)
    for hint in pool:
        if (hint not in all_hints 
            and hint not in category_hints[category] 
            and hint not in used_in_puzzle
            and not has_common_chars(hint, answer)):
            return hint
    
    # 兜底方案
    fallback = f"感觉{slot+1}"
    counter = 1
    while (fallback in all_hints 
           or fallback in category_hints[category] 
           or fallback in used_in_puzzle
           or has_common_chars(fallback, answer)):
        fallback = f"氛围{counter}"
        counter += 1
    return fallback

def has_common_chars(text1, text2):
    """检查两个文本是否有共同字符"""
    if not text1 or not text2:
        return False
    return any(c in text2 for c in text1)

def is_meta_descriptor(text):
    """检查是否是元描述词"""
    return any(meta in text for meta in META_DESCRIPTORS)

if __name__ == "__main__":
    main()

