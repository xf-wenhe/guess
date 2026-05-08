import json
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

path = Path('assets/puzzles.json')
text = path.read_text(encoding='utf-8')
data = json.loads(text)

REPLACEMENTS = {
    ("海贼王", "海盗"): "水匪",
    ("海贼王", "航海"): "远航",
    ("海贼王", "大海"): "汪洋",
    ("死神", "死神"): "冥使",
    ("名侦探柯南", "侦探"): "破案者",
    ("灌篮高手", "篮球"): "球赛",
    ("樱桃小丸子", "小学"): "低年级",
    ("蜡笔小新", "小孩"): "孩童",
    ("哆啦A梦", "梦想"): "愿望",
    ("数码宝贝", "数码"): "电子",
    ("美少女战士", "少女"): "花季",
    ("美少女战士", "战斗"): "对决",
    ("刀剑神域", "剑术"): "武技",
    ("一拳超人", "怪人"): "妖物",
    ("东京喰种", "喰种"): "食尸者",
    ("全职猎人", "猎人"): "狩者",
    ("黑执事", "执事"): "管家",
    ("黑执事", "黑暗"): "昏暗",
    ("进击的巨人", "巨人"): "庞然",
    ("进击的巨人", "人类"): "凡众",
    ("青之驱魔师", "驱魔"): "祓邪",
    ("青之驱魔师", "恶魔"): "邪灵",
    ("鬼灭之刃", "斩鬼"): "退妖",
    ("咒术回战", "咒术"): "法门",
    ("咒术回战", "战斗"): "交锋",
    ("咒术回战", "诅咒"): "邪语",
    ("排球少年", "排球"): "拦网",
    ("排球少年", "少年"): "青春",
    ("网球王子", "网球"): "挥拍",
    ("夏目友人帐", "友人帐"): "契约簿",
    ("风之谷", "风"): "气流",
    ("魔女宅急便", "魔女"): "巫师",
    ("天气之子", "天气"): "晴雨",
    ("铃芽之旅", "旅途"): "行程",
    ("狐妖小红娘", "狐妖"): "灵兽",
    ("狐妖小红娘", "红线"): "姻线",
    ("罗小黑战记", "战斗"): "对抗",
    ("刺客伍六七", "刺客"): "杀手",
    ("大鱼海棠", "海底"): "深渊",
    ("白蛇缘起", "白蛇"): "灵蟒",
    ("斗罗大陆", "战斗"): "对战",
    ("斗破苍穹", "斗气"): "气劲",
    ("全职高手", "职业"): "行当",
    ("喜羊羊", "羊"): "牧畜",
    ("熊出没", "熊"): "棕兽",
    ("秦时明月", "秦汉"): "古朝",
    ("画江湖", "江湖"): "武林",
    ("刘德华", "华语"): "国语",
    ("晴天", "蓝天"): "蔚空",
    ("告白气球", "表白"): "倾诉",
    ("告白气球", "气球"): "彩囊",
    ("夜曲", "夜晚"): "深宵",
    ("演员", "表演"): "舞台",
    ("告白", "表白"): "倾诉",
    ("平凡之路", "公路"): "旅程",
    ("起风了", "风"): "气流",
    ("最美的期待", "期待"): "盼望",
    ("青花瓷", "瓷器"): "陶器",
}

model = SentenceTransformer("models/bge-m3-finetuned-v7", device='cpu')

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

updated_hints = []
for item in data:
    answer = item.get('answer', '')
    hints = item.get('hints', [])
    new_hints = [REPLACEMENTS.get((answer, h), h) for h in hints]

    ans_vec = model.encode(answer, normalize_embeddings=True)
    scored = []
    for hint in new_hints:
        hint_vec = model.encode(hint, normalize_embeddings=True)
        scored.append((cosine(ans_vec, hint_vec), hint))
    scored.sort(key=lambda x: x[0])
    ordered = [h for _, h in scored]

    a_chars = set(answer)
    for hint in ordered:
        if any(ch in a_chars for ch in hint):
            raise SystemExit(f"overlap remains: answer={answer} hint={hint}")

    updated_hints.append(ordered)

for item, hints in zip(data, updated_hints):
    item["hints"] = hints

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
print(f"updated_items={len(updated_hints)}")
