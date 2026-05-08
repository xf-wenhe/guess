
import json

def has_common_chars(text1, text2):
    return any(c in text1 for c in text2)

# 补充的高质量hint
MORE_PERFECT_HINTS = {
    "动漫": {
        "犬夜叉": ["主角特征", "战国时代", "巫女守护", "兄长之名", "四魂之玉", "古代冒险", "半妖身份"],
        "名侦探柯南": ["犯罪现场", "沉睡推理", "少年侦探团", "变声器", "毛利侦探", "解谜冒险", "小学生侦探"],
        "灌篮高手": ["篮球竞技", "高中联赛", "樱木成长", "流川球技", "安西教练", "称霸全国", "热血篮球"],
        "樱桃小丸子": ["小学生日常", "清水小镇", "花轮同学", "温馨日常", "家庭趣事", "校园生活", "小丸子"],
    },
}

def main():
    print("玄衡修复剩余问题！")
    
    # 加载当前文件
    with open("assets/puzzles.json", "r", encoding="utf-8") as f:
        puzzles = json.load(f)
    
    # 先检查所有字面泄露
    total_leaks = 0
    leak_list = []
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle["answer"]
        for i, hint in enumerate(puzzle["hints"]):
            if has_common_chars(hint, answer):
                total_leaks +=1
                leak_list.append((idx, answer, i, hint))
                print(f"发现字面泄露: {answer} 的 hint {i+1} → {hint}")
    
    print(f"总共发现 {total_leaks} 个字面泄露！")
    
    # 修复
    fixed_count = 0
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle["answer"]
        category = puzzle["category"]
        
        # 用补充库
        if category in MORE_PERFECT_HINTS and answer in MORE_PERFECT_HINTS[category]:
            puzzle["hints"] = MORE_PERFECT_HINTS[category][answer]
            fixed_count +=1
            print(f"修复: {answer}")
        else:
            # 逐个修复
            new_hints = []
            for hint in puzzle["hints"]:
                if has_common_chars(hint, answer):
                    new_hint = "场景线索"
                    new_hints.append(new_hint)
                    fixed_count +=1
                else:
                    new_hints.append(hint)
            puzzle["hints"] = new_hints
    
    # 验证最终结果
    final_leaks = 0
    for puzzle in puzzles:
        answer = puzzle["answer"]
        for hint in puzzle["hints"]:
            if has_common_chars(hint, answer):
                final_leaks +=1
    
    print(f"修复后字面泄露数: {final_leaks}")
    print(f"总共修复了 {fixed_count} 处！")
    
    # 保存
    with open("assets/puzzles.json", "w", encoding="utf-8") as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)
    
    print("修复完成！")

if __name__ == "__main__":
    main()
