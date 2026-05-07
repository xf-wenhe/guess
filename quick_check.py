import json
from pathlib import Path

def load_puzzles():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def check_literal_leak(puzzle):
    """检查hint和answer有没有相同字"""
    answer = puzzle['answer']
    answer_chars = set(answer)
    leaks = []
    for i, hint in enumerate(puzzle['hints']):
        hint_chars = set(hint)
        common = answer_chars & hint_chars
        if common:
            leaks.append({
                'index': i,
                'hint': hint,
                'common_chars': list(common)
            })
    return leaks

def check_duplicate_hints(puzzles):
    """检查全局重复hints"""
    hint_map = {}
    duplicates = []
    for idx, puzzle in enumerate(puzzles):
        category = puzzle['category']
        answer = puzzle['answer']
        for i, hint in enumerate(puzzle['hints']):
            key = hint
            if key in hint_map:
                duplicates.append({
                    'puzzle1': hint_map[key],
                    'puzzle2': {
                        'index': idx,
                        'category': category,
                        'answer': answer,
                        'hint_index': i,
                        'hint': hint
                    }
                })
            else:
                hint_map[key] = {
                    'index': idx,
                    'category': category,
                    'answer': answer,
                    'hint_index': i,
                    'hint': hint
                }
    return duplicates

def check_same_category_duplicates(puzzles):
    """检查同分类内重复hints"""
    category_hints = {}
    duplicates = []
    for idx, puzzle in enumerate(puzzles):
        category = puzzle['category']
        answer = puzzle['answer']
        if category not in category_hints:
            category_hints[category] = {}
        for i, hint in enumerate(puzzle['hints']):
            key = hint
            if key in category_hints[category]:
                duplicates.append({
                    'category': category,
                    'puzzle1': category_hints[category][key],
                    'puzzle2': {
                        'index': idx,
                        'answer': answer,
                        'hint_index': i,
                        'hint': hint
                    }
                })
            else:
                category_hints[category][key] = {
                    'index': idx,
                    'answer': answer,
                    'hint_index': i,
                    'hint': hint
                }
    return duplicates

def check_same_puzzle_duplicates(puzzle):
    """检查同一谜题内重复hints"""
    seen = {}
    duplicates = []
    for i, hint in enumerate(puzzle['hints']):
        if hint in seen:
            duplicates.append({
                'index1': seen[hint],
                'index2': i,
                'hint': hint
            })
        else:
            seen[hint] = i
    return duplicates

def check_hint_length(puzzle):
    """检查hint长度（建议短词，但不要强制）"""
    issues = []
    for i, hint in enumerate(puzzle['hints']):
        if len(hint) > 7:
            issues.append({
                'index': i,
                'hint': hint,
                'length': len(hint)
            })
    return issues

def main():
    puzzles = load_puzzles()
    print(f"=== 检查共 {len(puzzles)} 个谜题 ===")
    
    all_literal_leaks = []
    all_same_puzzle_dupes = []
    
    for idx, puzzle in enumerate(puzzles):
        category = puzzle['category']
        answer = puzzle['answer']
        
        # 检查字面泄露
        leaks = check_literal_leak(puzzle)
        if leaks:
            all_literal_leaks.append({
                'index': idx,
                'category': category,
                'answer': answer,
                'leaks': leaks
            })
        
        # 检查同题内重复
        same_puzzle_dupes = check_same_puzzle_duplicates(puzzle)
        if same_puzzle_dupes:
            all_same_puzzle_dupes.append({
                'index': idx,
                'category': category,
                'answer': answer,
                'duplicates': same_puzzle_dupes
            })
    
    # 检查全局重复
    global_dupes = check_duplicate_hints(puzzles)
    
    # 检查同分类重复
    category_dupes = check_same_category_duplicates(puzzles)
    
    print("\n=== 检查结果 ===")
    print(f"字面泄露: {len(all_literal_leaks)} 个谜题")
    print(f"同题内重复: {len(all_same_puzzle_dupes)} 个谜题")
    print(f"全局重复hint: {len(global_dupes)} 组")
    print(f"同分类重复hint: {len(category_dupes)} 组")
    
    if all_literal_leaks:
        print("\n--- 字面泄露详情 ---")
        for item in all_literal_leaks[:10]:  # 先显示前10个
            print(f"[{item['category']}] {item['answer']}")
            for leak in item['leaks']:
                print(f"  Hint {leak['index']}: '{leak['hint']}' 包含字 {leak['common_chars']}")
    
    if global_dupes:
        print("\n--- 全局重复详情（前10组）---")
        for item in global_dupes[:10]:
            p1 = item['puzzle1']
            p2 = item['puzzle2']
            print(f"'{p1['hint']}' 在 [{p1['category']}]{p1['answer']}#{p1['hint_index']} 和 [{p2['category']}]{p2['answer']}#{p2['hint_index']}")
    
    if category_dupes:
        print("\n--- 同分类重复详情（前10组）---")
        for item in category_dupes[:10]:
            p1 = item['puzzle1']
            p2 = item['puzzle2']
            print(f"[{item['category']}] '{p1['hint']}' 在 {p1['answer']}#{p1['hint_index']} 和 {p2['answer']}#{p2['hint_index']}")
    
    # 保存完整结果
    result = {
        'literal_leaks': all_literal_leaks,
        'same_puzzle_dupes': all_same_puzzle_dupes,
        'global_dupes': global_dupes,
        'category_dupes': category_dupes
    }
    with open('tmp/check_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存到 tmp/check_result.json")

if __name__ == '__main__':
    main()
