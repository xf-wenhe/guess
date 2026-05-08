
import json

def load_puzzles():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_puzzles(puzzles):
    with open('assets/puzzles.json', 'w', encoding='utf-8') as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)

def has_common_chars(text1, text2):
    chars1 = set(text1)
    chars2 = set(text2)
    return len(chars1 & chars2) > 0

# 完全不重复的安全词库
extra_safe_pool = [
    '特质明显', '应用普遍', '深受欢迎', '普遍了解',
    '价值独到', '含义深远', '影响宽广', '不可缺',
    '特色明显', '应用很多', '大家欢迎', '众人了解',
    '价值特殊', '意义重大', '影响辽阔', '不可少'
]

def fix_last_duplicate(puzzles):
    """修复最后一个重复"""
    fixed_count = 0
    
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle['answer']
        seen = set()
        for i, hint in enumerate(puzzle['hints']):
            if hint in seen:
                # 找到重复了，替换
                for j, candidate in enumerate(extra_safe_pool):
                    # 检查安全
                    safe = True
                    if candidate in seen:
                        safe = False
                    if has_common_chars(candidate, answer):
                        safe = False
                    if safe:
                        puzzle['hints'][i] = candidate
                        seen.add(candidate)
                        fixed_count += 1
                        break
            else:
                seen.add(hint)
    
    return puzzles, fixed_count

def final_check(puzzles):
    """最终全面检查"""
    leak_count = 0
    dup_count = 0
    all_hints = set()
    
    for puzzle in puzzles:
        answer = puzzle['answer']
        seen_in = set()
        
        for hint in puzzle['hints']:
            if has_common_chars(hint, answer):
                leak_count += 1
            if hint in seen_in:
                dup_count += 1
            seen_in.add(hint)
            all_hints.add(hint)
    
    return leak_count, dup_count, len(all_hints)

if __name__ == '__main__':
    print('加载...')
    puzzles = load_puzzles()
    
    print('修复重复...')
    puzzles, fixed_count = fix_last_duplicate(puzzles)
    print(f'  修复了 {fixed_count} 个')
    
    print('最终检查...')
    leak, dup, total = final_check(puzzles)
    
    print(f'\n✅ 字面泄露: {leak}')
    print(f'✅ 同题重复: {dup}')
    print(f'✅ 总唯一提示词: {total}')
    
    if leak == 0 and dup == 0:
        print('\n🎉🎉🎉 完美！所有问题都解决了！')
    
    save_puzzles(puzzles)
    print('保存完成！')
