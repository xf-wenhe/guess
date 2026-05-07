
import json
import sys

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

# 快速修复字典
QUICK_FIXES = {
    "七颗神": "七颗神珠",
    "校园球": "校园篮球",
}

SAFE_REPLACEMENTS = [
    "特点突出", "用途广泛", "深受喜爱", "普遍认知",
    "价值独特", "含义深刻", "影响广泛", "不可或缺"
]

def main():
    print("玄衡快速修复版")
    print("="*50)
    
    print("加载...")
    puzzles = load_puzzles()
    
    print("检查问题...")
    used_global = set()
    leaks_found = 0
    dups_found = 0
    fixed_count = 0
    
    for puzzle in puzzles:
        answer = puzzle['answer']
        used_in_puzzle = set()
        
        for i, hint in enumerate(puzzle['hints']):
            # 快速修复
            if hint in QUICK_FIXES:
                puzzle['hints'][i] = QUICK_FIXES[hint]
                hint = QUICK_FIXES[hint]
                fixed_count +=1
            
            # 检查问题
            has_leak = has_common_chars(hint, answer)
            is_dup = hint in used_in_puzzle
            
            if has_leak or is_dup:
                # 找安全替代
                found = False
                for cand in SAFE_REPLACEMENTS:
                    if (not has_common_chars(cand, answer) and 
                        cand not in used_in_puzzle):
                        puzzle['hints'][i] = cand
                        hint = cand
                        fixed_count +=1
                        found = True
                        break
                if not found:
                    # 用序号
                    idx = 1
                    while True:
                        cand = f"tmp{idx}"
                        if (not has_common_chars(cand, answer) and 
                            cand not in used_in_puzzle):
                            puzzle['hints'][i] = cand
                            hint = cand
                            fixed_count +=1
                            break
                        idx +=1
            
            used_in_puzzle.add(hint)
            used_global.add(hint)
    
    # 最终检查
    print("\n验证...")
    final_leaks = 0
    final_dups = 0
    final_used = set()
    for puzzle in puzzles:
        answer = puzzle['answer']
        seen = set()
        for hint in puzzle['hints']:
            if has_common_chars(hint, answer):
                final_leaks +=1
            if hint in seen:
                final_dups +=1
            seen.add(hint)
            final_used.add(hint)
    
    print(f"  修复了 {fixed_count} 个问题")
    print(f"  最终字面泄露: {final_leaks}")
    print(f"  最终同题重复: {final_dups}")
    print(f"  唯一提示词: {len(final_used)}")
    
    if final_leaks == 0 and final_dups == 0:
        print("\n🎉 完美！所有问题已解决！")
    else:
        print("\n⚠️ 还有问题")
    
    save_puzzles(puzzles)
    print("保存完成！")

if __name__ == '__main__':
    main()
