
import json

def has_common_chars(text1, text2):
    return any(c in text1 for c in text2)

# 高质量的安全替代表，既无字面泄露，又有语义
SAFE_REPLACEMENTS = {
    # 火影相关
    "鸣人": "橙色身影",
    "佐助": "宇智波少年",
    "木叶": "忍者村落",
    "火影": "橙色身影",
    "查克拉": "能量流动",
    "九尾": "妖狐之力",
    "忍者": "秘密行者",
    
    # 海贼王相关
    "路飞": "草帽少年",
    "草帽": "标志性帽子",
    "果实": "特殊能力",
    "新世界": "伟大航线",
    "伟大航路": "探索之旅",
    "远航": "出海冒险",
    
    # 美食相关
    "串": "烤制美味",
    "寿司": "醋饭美味",
    "披萨": "圆饼美味",
    "烧烤": "烟火美味",
}

def main():
    print("玄衡开始修复！")
    
    # 加载当前文件
    with open("assets/puzzles.json", "r", encoding="utf-8") as f:
        puzzles = json.load(f)
    
    fixed_count = 0
    
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle["answer"]
        hints = puzzle["hints"]
        new_hints = []
        
        # 检查并修复字面泄露
        for hint in hints:
            if has_common_chars(hint, answer):
                # 找安全替代
                if hint in SAFE_REPLACEMENTS:
                    new_hint = SAFE_REPLACEMENTS[hint]
                else:
                    new_hint = "场景线索"
                new_hints.append(new_hint)
                fixed_count +=1
                print(f"修复 {answer} 的 hint: {hint} → {new_hint}")
            else:
                new_hints.append(hint)
        
        # 更新谜题
        puzzle["hints"] = new_hints
    
    # 保存
    with open("assets/puzzles.json", "w", encoding="utf-8") as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)
    
    print(f"总共修复了 {fixed_count} 个问题！")
    print("修复完成！")

if __name__ == "__main__":
    main()
