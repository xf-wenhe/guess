
import json
import re
from collections import defaultdict

def load_puzzles():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def has_common_chars(text1, text2):
    chars1 = set(text1)
    chars2 = set(text2)
    return len(chars1 & chars2) > 0

def check_literal_leaks(puzzle):
    leaks = []
    answer = puzzle['answer']
    for i, hint in enumerate(puzzle['hints']):
        if has_common_chars(hint, answer):
            common = [c for c in answer if c in hint]
            leaks.append({
                'index': i,
                'hint': hint,
                'common_chars': list(set(common))
            })
    return leaks if leaks else None

def check_duplicates(puzzles):
    global_hints = defaultdict(list)
    category_hints = defaultdict(lambda: defaultdict(list))
    same_puzzle_dups = defaultdict(list)

    for idx, puzzle in enumerate(puzzles):
        category = puzzle['category']
        answer = puzzle['answer']
        for i, hint in enumerate(puzzle['hints']):
            global_hints[hint].append({'index': idx, 'answer': answer})
            category_hints[category][hint].append({'index': idx, 'answer': answer})
        # 同一谜题内部检查重复
        seen = {}
        for i, hint in enumerate(puzzle['hints']):
            if hint in seen:
                same_puzzle_dups[idx].append({
                    'answer': answer,
                    'hint': hint,
                    'positions': [seen[hint], i]
                })
            else:
                seen[hint] = i

    return global_hints, category_hints, same_puzzle_dups

def main():
    puzzles = load_puzzles()
    print('='*80)
    print('谜题全面分析报告')
    print('='*80)
    
    # 1. 检查字面泄露
    print('\n1. 字面泄露检查')
    print('-'*80)
    leak_count = 0
    leak_details = []
    for idx, puzzle in enumerate(puzzles):
        leaks = check_literal_leaks(puzzle)
        if leaks:
            leak_count += 1
            leak_details.append({
                'index': idx,
                'category': puzzle['category'],
                'answer': puzzle['answer'],
                'leaks': leaks
            })
    print(f'  有 {leak_count} 个谜题存在字面泄露')
    
    # 2. 检查重复提示
    print('\n2. 重复提示检查')
    print('-'*80)
    global_hints, category_hints, same_puzzle_dups = check_duplicates(puzzles)
    
    global_dups = {k:v for k,v in global_hints.items() if len(v)>=2}
    print(f'  全局重复提示: {len(global_dups)} 个')
    
    category_dups = 0
    for cat, hints in category_hints.items():
        for hint, info in hints.items():
            if len(info)>=2:
                category_dups +=1
    print(f'  同分类重复提示: {category_dups} 个')
    print(f'  同谜题重复提示: {len(same_puzzle_dups)} 个')
    
    # 3. 保存详细报告
    report = {
        'literal_leaks': leak_details,
        'global_duplicates': global_dups,
        'category_duplicates': {k: {h:i for h,i in v.items() if len(i)>=2} for k,v in category_hints.items()},
        'same_puzzle_duplicates': same_puzzle_dups
    }
    
    import os
    os.makedirs('tmp', exist_ok=True)
    with open('tmp/full_check_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('\n  详细报告已保存到: tmp/full_check_report.json')
    
    # 4. 显示前20个泄露示例
    print('\n3. 前20个字面泄露示例')
    print('-'*80)
    for i, d in enumerate(leak_details[:20], 1):
        print(f'\n{i}. {d["category"]}: {d["answer"]}')
        for leak in d['leaks']:
            print(f'   - 提示{leak["index"]}: "{leak["hint"]}"')
            print(f'     共同字: {leak["common_chars"]}')

if __name__ == '__main__':
    main()
