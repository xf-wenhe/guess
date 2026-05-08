#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查所有谜题的脚本
"""
import json
import sys


def check_single_puzzle(puzzle):
    answer = puzzle['answer']
    category = puzzle['category']
    hints = puzzle['hints']
    answer_chars = set(answer)
    issues = []
    
    # 字面隔离检查
    for i, hint in enumerate(hints):
        hint_chars = set(hint)
        common_chars = hint_chars & answer_chars
        if common_chars:
            issues.append({
                'type': '字面泄露',
                'hint_index': i + 1,
                'hint': hint,
                'common': list(common_chars)
            })
    
    # 元描述/模板词检查
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
        for meta in meta_words:
            if meta in hint:
                issues.append({
                    'type': '元描述/模板词',
                    'hint_index': i + 1,
                    'hint': hint,
                    'meta': meta
                })
    
    # 同题重复检查
    seen_hints = set()
    for i, hint in enumerate(hints):
        if hint in seen_hints:
            issues.append({
                'type': '同题重复',
                'hint_index': i + 1,
                'hint': hint
            })
        else:
            seen_hints.add(hint)
    
    # 长度检查
    for i, hint in enumerate(hints):
        if len(hint) >= 7:
            issues.append({
                'type': '过长',
                'hint_index': i + 1,
                'hint': hint,
                'length': len(hint)
            })
    
    # 占位符检查
    for i, hint in enumerate(hints):
        if hint.startswith('hint_'):
            issues.append({
                'type': '占位符',
                'hint_index': i + 1,
                'hint': hint
            })
    
    return issues


def main():
    print("=" * 80)
    print("🚀 玄衡 - 检查所有谜题")
    print("=" * 80)
    
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        puzzles = json.load(f)
    print(f"✅ 读取 {len(puzzles)} 个谜题")
    
    all_issues = 0
    problematic_puzzles = 0
    
    for puzzle in puzzles:
        issues = check_single_puzzle(puzzle)
        if issues:
            problematic_puzzles += 1
            all_issues += len(issues)
            print(f"\n❌ {puzzle['answer']} (category: {puzzle['category']})")
            print(f"  当前hints：{puzzle['hints']}")
            for issue in issues:
                print(f"   - [{issue['type']}] hint {issue['hint_index']}: {issue['hint']}")
    
    if all_issues > 0:
        print(f"\n{'=' * 80}")
        print(f"❌ 发现 {problematic_puzzles} 个问题谜题，共 {all_issues} 个问题！")
    else:
        print(f"\n{'=' * 80}")
        print(f"✅ 所有谜题检查通过！")


if __name__ == "__main__":
    main()
