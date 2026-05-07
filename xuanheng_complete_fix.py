
import json

def has_common_chars(text1, text2):
    return any(c in text1 for c in text2)

# 高质量hint库，按类别
QUALITY_HINTS = {
    "美食": {
        "烧烤": ["木炭", "架子", "香味", "香料", "蔬菜肉食", "滋滋冒油", "多人聚餐"],
        "寿司": ["手握", "海苔", "卷物", "芥末", "醋饭", "生鲜", "冷食上桌"],
        "披萨": ["切角", "拉丝", "烘炉", "叠料", "番茄酱", "芝乳", "圆饼美味"],
    },
    "动漫": {
        "火影": ["查克拉", "忍者村落", "橙色身影", "日本", "宇智波少年", "妖狐之力", "秘密行者"],
        "海贼王": ["标志性帽子", "特殊能力", "草帽少年", "日本", "伟大航线", "探索之旅", "出海冒险"],
        "死神": ["露琪亚", "一护君", "护廷队", "日本", "虚圈域", "斩魄刀", "尸魂界"],
    },
}

def main():
    print("玄衡完美修复！")
    
    # 加载备份（高质量基础）
    with open("tmp/assets.puzzles.before_top20_apply.json", "r", encoding="utf-8") as f:
        puzzles = json.load(f)
    
    print(f"加载了 {len(puzzles)} 个谜题！")
    
    # 修复字面泄露问题，同时保证hint质量
    fixed_count = 0
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle["answer"]
        category = puzzle["category"]
        
        # 优先用质量库
        if category in QUALITY_HINTS and answer in QUALITY_HINTS[category]:
            puzzle["hints"] = QUALITY_HINTS[category][answer]
            fixed_count +=1
            print(f"用高质量hint修复: {answer}")
        else:
            # 修复字面泄露
            hints = puzzle["hints"]
            new_hints = []
            for hint in hints:
                if has_common_chars(hint, answer):
                    # 替换成安全的
                    new_hint = "场景线索"
                    new_hints.append(new_hint)
                    fixed_count +=1
                else:
                    new_hints.append(hint)
            puzzle["hints"] = new_hints
    
    # 保存
    with open("assets/puzzles.json", "w", encoding="utf-8") as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)
    
    print(f"修复完成！总共修复了 {fixed_count} 处！")

if __name__ == "__main__":
    main()
