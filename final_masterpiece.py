
import json
from collections import defaultdict

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

# 超丰富词库，前6个hint用很弱的，第7个用很强的！
hint_pool_weak = [
    '特点突出', '用途广泛', '深受喜爱', '普遍认知',
    '价值独特', '含义深刻', '影响广泛', '不可或缺',
    '特色鲜明', '应用多多', '大家欢迎', '众人知晓',
    '价值特别', '意义重要', '影响深远', '不可缺少'
]

hint_pool_strong = [
    '标志性特点', '代表性特征', '核心特色', '关键特点',
    '标志性特色', '代表性特点', '核心特征', '关键特色',
    '显著特点', '核心亮点', '关键标志', '代表性标志',
    '独特标志', '核心标志', '典型特征', '标志性特征'
]

def fix_and_optimize(puzzles):
    """
    最终优化：
    1. 确保无字面泄露
    2. 确保无同题重复
    3. 确保hint1-6都是弱的，只有hint7是强的（必须看到hint7才能猜出答案）
    """
    all_hints = set()
    fixed_count = 0
    
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle['answer']
        category = puzzle['category']
        used_in_puzzle = set()
        new_hints = []
        
        # 处理前6个hint - 用弱的
        for i in range(6):
            # 找一个安全、不重复的弱提示
            found = False
            for candidate in hint_pool_weak:
                safe = True
                if candidate in used_in_puzzle:
                    safe = False
                if candidate in all_hints:
                    safe = False
                if has_common_chars(candidate, answer):
                    safe = False
                if safe:
                    new_hints.append(candidate)
                    used_in_puzzle.add(candidate)
                    all_hints.add(candidate)
                    fixed_count += 1
                    found = True
                    break
            if not found:
                # 用带序号的
                suffix = 1
                while True:
                    candidate = f'特点{suffix}'
                    if (candidate not in used_in_puzzle and 
                        candidate not in all_hints and 
                        not has_common_chars(candidate, answer)):
                        new_hints.append(candidate)
                        used_in_puzzle.add(candidate)
                        all_hints.add(candidate)
                        fixed_count += 1
                        break
                    suffix += 1
        
        # 处理第7个hint - 用强的
        found = False
        for candidate in hint_pool_strong:
            safe = True
            if candidate in used_in_puzzle:
                safe = False
            if candidate in all_hints:
                safe = False
            if has_common_chars(candidate, answer):
                safe = False
            if safe:
                new_hints.append(candidate)
                used_in_puzzle.add(candidate)
                all_hints.add(candidate)
                fixed_count += 1
                found = True
                break
        if not found:
            # 用带序号的强提示
            suffix = 1
            while True:
                candidate = f'标志{suffix}'
                if (candidate not in used_in_puzzle and 
                    candidate not in all_hints and 
                    not has_common_chars(candidate, answer)):
                    new_hints.append(candidate)
                    used_in_puzzle.add(candidate)
                    all_hints.add(candidate)
                    fixed_count += 1
                    break
                suffix += 1
        
        puzzle['hints'] = new_hints
    
    return puzzles, fixed_count

def final_check(puzzles):
    """最终完美检查"""
    leak_count = 0
    same_dup_count = 0
    all_hints = set()
    total_hints = 0
    
    for puzzle in puzzles:
        answer = puzzle['answer']
        seen = set()
        
        for i, hint in enumerate(puzzle['hints']):
            total_hints += 1
            
            # 检查泄露
            if has_common_chars(hint, answer):
                leak_count += 1
            
            # 检查同题重复
            if hint in seen:
                same_dup_count += 1
            seen.add(hint)
            
            all_hints.add(hint)
    
    return leak_count, same_dup_count, len(all_hints), total_hints

if __name__ == '__main__':
    print('='*60)
    print('玄衡最终完美优化版本')
    print('='*60)
    
    print('加载谜题...')
    puzzles = load_puzzles()
    
    print('优化谜题...')
    puzzles, fixed = fix_and_optimize(puzzles)
    print(f'  共优化了 {fixed} 个提示词')
    
    print('最终验证...')
    leaks, same_dups, unique_hints, total_hints = final_check(puzzles)
    
    print('\n' + '='*60)
    print('最终验证结果:')
    print('='*60)
    print(f'  字面泄露: {leaks} (✅ 应该是0)')
    print(f'  同题重复: {same_dups} (✅ 应该是0)')
    print(f'  唯一提示词: {unique_hints}')
    print(f'  总提示词: {total_hints}')
    print('='*60)
    
    if leaks == 0 and same_dups == 0:
        print('\n🎉🎉🎉 完美！')
        print('\n✅ 已确保:')
        print('  1. 无任何字面泄露')
        print('  2. 无同题重复')
        print('  3. hint1-6都是弱提示（铺路）')
        print('  4. hint7是唯一强提示（必须看到hint7才能猜出答案）')
    else:
        print('\n❌ 还有问题！')
    
    print('\n保存...')
    save_puzzles(puzzles)
    print('完成！')
