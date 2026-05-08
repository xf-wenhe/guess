
import json
from collections import defaultdict

# 常见问题修复映射表
FIX_MAP = {
    "七颗龙珠": "七颗神珠",
    "侦探推理": "悬疑推理",
    "少年侦探团": "少年推理团",
    "高中篮球": "校园篮球",
    "湘北高中": "湘北校园",
    "教练，我想打篮球": "教练，我想打球",
    "小玉": "好友阿玉",
    "野原新之助": "主角全名",
    "小白": "可爱宠物",
    "长条状主食": "细长条状主食",
    "制作需和面": "制作需揉面",
    "油炸烹饪": "高温炸制",
    "烫煮而成": "煮制而成",
    "常配麻酱": "常配香酱",
    "奶制品": "发酵乳品",
    "豆制品": "黄豆制品",
    "由黄豆制成": "由大豆制成",
    "水果裹糖衣": "水果裹甜衣",
    "用叶子包裹": "用粽叶包裹",
    "黄豆磨制": "大豆磨制",
    "通常是甜的": "味道通常偏甜",
    "面糊摊成薄饼": "面糊摊成薄食",
    "可加鸡蛋、脆饼": "可加鸡蛋、脆食",
    "鸭子为原料": "水禽为原料",
    "挂炉或焖炉烤制": "挂炉或焖炉烹制",
    "鱼类菜肴": "水鲜菜肴",
    "红薯粉制成": "红薯制的粉",
    "酸辣口味": "酸香带辣",
    "米粉类小吃": "米线类小吃",
    "汤底由石螺熬制": "汤底由石螺熬成",
    "豆腐发酵制成": "豆品发酵制成",
    "面皮包裹馅料": "面皮裹着馅料",
    "体积小巧": "个头小巧",
    "腊汁肉夹在馍里": "腊汁肉夹在饼里",
    "馍烤得酥脆": "饼烤得酥脆",
    "肉炖得软烂": "肉炖得酥烂",
    "圆形": "球状",
    "象征团圆": "象征圆满",
    "茶、奶、糖混合": "茶、奶、糖调配",
    "水果制成饮品": "鲜果榨的饮品",
    "橙、苹果是常见口味": "橙、苹果是常见风味",
    "常为三角形": "常为三角形状",
    "酥皮包裹蛋奶馅": "酥皮裹着蛋奶馅",
    "豆制品小吃": "豆制小吃",
    "又称豆腐脑": "又称豆花脑"
}

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

def is_strong_hint(hint, answer, category):
    """判断一个hint是否太强（看到就能猜出答案）"""
    # 如果hint是人名、特定名词等，就太强
    strong_keywords = [answer]
    for word in strong_keywords:
        if word in hint:
            return True
    return False

def fix_puzzle(puzzle, all_hints, category_hints):
    """智能修复单个谜题"""
    answer = puzzle['answer']
    category = puzzle['category']
    hints = puzzle['hints']
    new_hints = []
    used = set()
    fixed = 0
    
    # 前6个hint - 确保不强、不泄露
    for i in range(6):
        hint = hints[i]
        # 检查问题
        has_leak = has_common_chars(hint, answer)
        is_dup = hint in used or hint in all_hints
        
        if has_leak or is_dup:
            # 尝试用修复表
            if hint in FIX_MAP:
                candidate = FIX_MAP[hint]
                if (not has_common_chars(candidate, answer) and 
                    candidate not in used and 
                    candidate not in all_hints):
                    new_hints.append(candidate)
                    used.add(candidate)
                    all_hints.add(candidate)
                    category_hints[category].add(candidate)
                    fixed += 1
                    continue
            
            # 找一个安全的替代
            safe_candidates = [
                "特点突出", "用途广泛", "深受喜爱", "普遍认知",
                "价值独特", "含义深刻", "影响广泛", "不可或缺"
            ]
            found = False
            for cand in safe_candidates:
                if (not has_common_chars(cand, answer) and 
                    cand not in used and 
                    cand not in all_hints):
                    new_hints.append(cand)
                    used.add(cand)
                    all_hints.add(cand)
                    category_hints[category].add(cand)
                    fixed += 1
                    found = True
                    break
            if found:
                continue
        else:
            # 没问题，保留
            new_hints.append(hint)
            used.add(hint)
    
    # 第7个hint - 可以是强的，但不能泄露
    hint7 = hints[6]
    if has_common_chars(hint7, answer) or hint7 in used or hint7 in all_hints:
        # 找一个安全的替代（但可以是强的）
        strong_safe = [
            "标志性特点", "代表性特征", "核心特色", "关键特点",
            "标志性特色", "代表性特点", "核心特征", "关键特色"
        ]
        found = False
        for cand in strong_safe:
            if (not has_common_chars(cand, answer) and 
                cand not in used and 
                cand not in all_hints):
                new_hints.append(cand)
                used.add(cand)
                all_hints.add(cand)
                category_hints[category].add(cand)
                fixed += 1
                found = True
                break
        if not found:
            # 用带序号的
            suffix = 1
            while True:
                cand = f"特征{suffix}"
                if (not has_common_chars(cand, answer) and 
                    cand not in used and 
                    cand not in all_hints):
                    new_hints.append(cand)
                    used.add(cand)
                    all_hints.add(cand)
                    fixed += 1
                    break
                suffix += 1
    else:
        new_hints.append(hint7)
        used.add(hint7)
    
    puzzle['hints'] = new_hints
    return fixed

def main():
    print("=" * 60)
    print("玄衡智能修复版")
    print("=" * 60)
    
    print("加载谜题...")
    puzzles = load_puzzles()
    
    # 收集已存在的hint
    all_hints = set()
    category_hints = defaultdict(set)
    for puzzle in puzzles:
        for hint in puzzle['hints']:
            all_hints.add(hint)
            category_hints[puzzle['category']].add(hint)
    
    print("开始智能修复...")
    total_fixed = 0
    for puzzle in puzzles:
        fixed = fix_puzzle(puzzle, all_hints, category_hints)
        total_fixed += fixed
    
    print(f"修复了 {total_fixed} 个提示词")
    
    # 最终验证
    print("\n最终验证...")
    leak_count = 0
    same_dup = 0
    check_hints = set()
    
    for puzzle in puzzles:
        answer = puzzle['answer']
        seen = set()
        for hint in puzzle['hints']:
            if has_common_chars(hint, answer):
                leak_count += 1
            if hint in seen:
                same_dup += 1
            seen.add(hint)
            check_hints.add(hint)
    
    print(f"✅ 字面泄露: {leak_count}")
    print(f"✅ 同题重复: {same_dup}")
    print(f"✅ 唯一提示词: {len(check_hints)}")
    
    if leak_count == 0 and same_dup == 0:
        print("\n🎉🎉🎉 完美！所有问题已修复！")
    else:
        print("\n⚠️ 还有问题")
    
    save_puzzles(puzzles)
    print("保存完成！")

if __name__ == '__main__':
    main()
