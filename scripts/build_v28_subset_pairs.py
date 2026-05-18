import csv
import json
import random
from pathlib import Path

PUZZLES_JSON = Path('assets/puzzles.json')
OUTPUT = Path('data/subset_relation_pairs_v28.csv')
FIELDNAMES = ['id', 'answer', 'user_input', 'score_0_100', 'relation_tag', 'reason']

MANUAL_SUBSET_PAIRS = [
    ("手机", "手机壳", 30, "设备vs配件"),
    ("手机", "手机膜", 25, "设备vs配件"),
    ("手机", "手机号", 35, "设备vs关联概念"),
    ("电脑", "电脑桌", 25, "设备vs家具"),
    ("电脑", "电脑包", 30, "设备vs配件"),
    ("电脑", "电脑椅", 25, "设备vs家具"),
    ("书包", "书包带", 25, "物品vs部件"),
    ("书包", "书包扣", 20, "物品vs部件"),
    ("茶", "奶茶", 50, "原料vs成品(弱包含)"),
    ("茶", "绿茶", 55, "上位词vs下位词"),
    ("茶", "红茶", 55, "上位词vs下位词"),
    ("茶", "花茶", 50, "上位词vs下位词"),
    ("猫", "波斯猫", 55, "上位词vs下位词"),
    ("猫", "猫粮", 25, "动物vs关联物品"),
    ("猫", "猫窝", 25, "动物vs关联物品"),
    ("猫", "猫砂", 25, "动物vs关联物品"),
    ("猫", "猫耳朵", 20, "动物vs同名词其他含义"),
    ("狗", "哈士奇", 55, "上位词vs下位词"),
    ("狗", "狗窝", 25, "动物vs关联物品"),
    ("狗", "狗粮", 25, "动物vs关联物品"),
    ("花", "花朵", 65, "同义词缩略"),
    ("花", "花园", 35, "事物vs场所"),
    ("花", "花瓶", 30, "事物vs容器"),
    ("花", "花茶", 35, "事物vs制品"),
    ("花", "花店", 30, "事物vs场所"),
    ("花", "花生", 20, "同字不同义：花vs花生(食物)"),
    ("水", "水瓶", 30, "物质vs容器"),
    ("水", "水果", 35, "物质vs含该物质的事物"),
    ("水", "水壶", 30, "物质vs容器"),
    ("水", "水面", 40, "物质vs形态"),
    ("风", "风之谷", 25, "自然现象vs作品名"),
    ("风", "风扇", 25, "自然现象vs设备"),
    ("风", "风筝", 30, "自然现象vs利用该现象的物品"),
    ("风", "风景", 35, "自然现象vs衍生概念"),
    ("龙", "龙卷风", 25, "神话生物vs自然现象(含同字)"),
    ("龙", "龙眼", 20, "神话生物vs水果(同字不同义)"),
    ("龙", "龙虾", 20, "神话生物vs动物(同字不同义)"),
    ("龙", "龙舟", 35, "神话生物vs文化物品"),
    ("龙", "龙袍", 30, "神话生物vs文化物品"),
    ("车", "汽车", 60, "上位词vs下位词"),
    ("车", "车库", 25, "物品vs场所"),
    ("车", "车站", 25, "物品vs场所"),
    ("车", "车牌", 25, "物品vs部件"),
    ("书", "书店", 25, "物品vs场所"),
    ("书", "书架", 30, "物品vs家具"),
    ("书", "书包", 30, "物品vs容器"),
    ("书", "书法", 30, "物品vs艺术(同字不同义)"),
    ("火", "火锅", 30, "自然现象vs烹饪方式"),
    ("火", "火车", 20, "自然现象vs交通工具(同字不同义)"),
    ("火", "火灾", 30, "自然现象vs事件"),
    ("火", "火焰", 55, "同义/近义"),
    ("金", "金鱼", 20, "金属vs动物(同字不同义)"),
    ("金", "金子", 60, "同义词"),
    ("月", "月饼", 25, "天体vs食品(关联)"),
    ("月", "月亮", 65, "缩写vs全称"),
    ("海", "海洋", 65, "缩写vs全称"),
    ("海", "海鲜", 35, "地点vs产地产品"),
    ("海", "海滩", 40, "地点vs组成部分"),
    ("雪", "雪花", 65, "同义词"),
    ("雪", "雪人", 30, "自然现象vs利用该现象的物品"),
    ("雪", "滑雪", 35, "自然现象vs相关活动"),
    ("雨", "雨伞", 25, "自然现象vs应对物品"),
    ("雨", "雨衣", 25, "自然现象vs应对物品"),
    ("雨", "雨季", 40, "自然现象vs时间概念"),
    ("灯", "灯泡", 40, "整体vs部件"),
    ("灯", "灯笼", 40, "通用vs具体类型"),
    ("门", "门把手", 30, "整体vs部件"),
    ("门", "门槛", 35, "整体vs部件"),
    ("树", "树叶", 45, "整体vs部分"),
    ("树", "树根", 45, "整体vs部分"),
    ("树", "树林", 45, "个体vs群体"),
    ("鱼", "金鱼", 50, "上位词vs下位词"),
    ("鱼", "鱼缸", 25, "动物vs容器"),
    ("鱼", "鱼竿", 25, "动物vs捕捞工具"),
    ("鸟", "鸟巢", 30, "动物vs住所"),
    ("鸟", "鸟笼", 25, "动物vs容器"),
    ("星", "星星", 65, "缩写vs口语全称"),
    ("星", "星空", 40, "天体vs景观"),
    ("星", "星座", 35, "天体vs概念"),
    ("冰", "冰块", 55, "物质vs形态"),
    ("冰", "冰激凌", 25, "物质vs食品"),
    ("冰", "冰箱", 20, "物质vs设备(同字不同义)"),
    ("石", "石头", 60, "缩写vs全称"),
    ("石", "石桥", 35, "材料vs建筑"),
]

def main():
    seen = set()
    rows = []

    def push(a, b, score, tag, reason):
        for ans, inp in [(a, b), (b, a)]:
            key = (ans, inp)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'answer': ans, 'user_input': inp,
                'score_0_100': str(score),
                'relation_tag': tag, 'reason': reason,
            })

    for a, b, score, reason in MANUAL_SUBSET_PAIRS:
        if score >= 50:
            tag = 'subset_relation_high'
        elif score >= 30:
            tag = 'subset_relation_mid'
        else:
            tag = 'subset_relation_low'
        push(a, b, score, tag, reason)

    # Auto-mine subset pairs from puzzles
    puzzles = json.loads(PUZZLES_JSON.read_text(encoding='utf-8'))
    answers = list(set(p.get('answer', '') for p in puzzles if p.get('answer')))

    for ans in answers:
        for other in answers:
            if ans == other or len(ans) >= len(other):
                continue
            if other.startswith(ans) and len(other) - len(ans) <= 2:
                key = (ans, other)
                if key not in seen:
                    score = 25
                    tag = 'subset_relation_low'
                    reason = f'前缀包含关系(自动): {ans} ⊂ {other}'
                    push(ans, other, score, tag, reason)

    random.seed(20260515)
    random.shuffle(rows)
    for i, row in enumerate(rows, 1):
        row['id'] = str(i)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    manual_count = len(MANUAL_SUBSET_PAIRS) * 2
    auto_count = len(rows) - manual_count
    print(f'subset_relation_pairs_v28: {len(rows)} rows (manual~{manual_count} auto={auto_count})')

if __name__ == '__main__':
    main()
