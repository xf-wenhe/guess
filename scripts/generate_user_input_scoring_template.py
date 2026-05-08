import csv
import json
import random
import re
from pathlib import Path

RANDOM_SEED = 20260227
PAIR_COUNT = 800
INPUT_PATH = Path("assets/puzzles.json")
OUTPUT_PATH = Path("data/semantic_scoring_user_input_template.csv")

CHINESE_RE = re.compile(r"^[\u4e00-\u9fff]{2,5}$")

# 模拟真实用户常见输入（无关/吐槽/口语）
COMMON_USER_INPUTS = [
    "不知道", "随便猜", "乱猜", "不会", "不懂", "啥呀", "这个", "那个", "好难", "瞎猜",
    "啊啊", "哈哈", "无语", "离谱", "你是猪", "怎么猜", "想不出", "没头绪", "提示少", "再来",
]


def is_valid_user_word(text: str) -> bool:
    return bool(text) and CHINESE_RE.fullmatch(text) is not None


def expected_range(tag: str) -> str:
    if tag == "same_answer_exact":
        return "95-100"
    if tag == "hint_like_high":
        return "70-90"
    if tag == "same_category_mid":
        return "60-70"
    if tag == "cross_category_low":
        return "0-30"
    if tag == "nonsense_low":
        return "0-20"
    return "0-100"


def main():
    random.seed(RANDOM_SEED)
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    answers = []
    answer_to_category = {}
    hints_by_answer = {}
    by_category = {}

    all_hint_words = set()

    for item in data:
        answer = item.get("answer", "").strip()
        category = item.get("category", "").strip()
        hints = [h.strip() for h in item.get("hints", []) if isinstance(h, str)]

        if not is_valid_user_word(answer):
            continue

        answers.append(answer)
        answer_to_category[answer] = category

        valid_hints = [h for h in hints if is_valid_user_word(h)]
        hints_by_answer[answer] = valid_hints

        by_category.setdefault(category, []).append(answer)
        all_hint_words.update(valid_hints)

    user_pool = set(answers) | set(COMMON_USER_INPUTS) | all_hint_words
    user_pool = [w for w in user_pool if is_valid_user_word(w)]

    rows = []
    seen = set()

    def push_row(answer: str, user_input: str, relation_tag: str):
        key = (answer, user_input)
        if key in seen:
            return False
        seen.add(key)
        rows.append({
            "id": len(rows) + 1,
            "answer": answer,
            "user_input": user_input,
            "answer_category": answer_to_category.get(answer, ""),
            "input_category_guess": "",
            "relation_tag": relation_tag,
            "expected_range": expected_range(relation_tag),
            "score_0_100": "",
            "reason": "",
            "reviewer": "",
        })
        return True

    # 分层抽样配比（更贴近真实猜词场景）
    target_counts = {
        "same_answer_exact": int(PAIR_COUNT * 0.10),
        "hint_like_high": int(PAIR_COUNT * 0.25),
        "same_category_mid": int(PAIR_COUNT * 0.30),
        "cross_category_low": int(PAIR_COUNT * 0.20),
        "nonsense_low": PAIR_COUNT - int(PAIR_COUNT * 0.10) - int(PAIR_COUNT * 0.25) - int(PAIR_COUNT * 0.30) - int(PAIR_COUNT * 0.20),
    }

    # 1) 精确匹配
    answer_samples = random.sample(answers, k=min(len(answers), target_counts["same_answer_exact"]))
    for a in answer_samples:
        push_row(a, a, "same_answer_exact")

    # 2) 提示词高相关
    while len([r for r in rows if r["relation_tag"] == "hint_like_high"]) < target_counts["hint_like_high"]:
        a = random.choice(answers)
        hints = hints_by_answer.get(a, [])
        if not hints:
            continue
        h = random.choice(hints)
        push_row(a, h, "hint_like_high")

    # 3) 同类中相关（60-70）
    while len([r for r in rows if r["relation_tag"] == "same_category_mid"]) < target_counts["same_category_mid"]:
        a = random.choice(answers)
        cat = answer_to_category.get(a, "")
        pool = [x for x in by_category.get(cat, []) if x != a and is_valid_user_word(x)]
        if not pool:
            continue
        b = random.choice(pool)
        push_row(a, b, "same_category_mid")

    # 4) 跨类低相关
    while len([r for r in rows if r["relation_tag"] == "cross_category_low"]) < target_counts["cross_category_low"]:
        a = random.choice(answers)
        cat = answer_to_category.get(a, "")
        pool = [x for x in answers if answer_to_category.get(x, "") != cat]
        if not pool:
            continue
        b = random.choice(pool)
        push_row(a, b, "cross_category_low")

    # 5) 口语/无意义低相关
    while len([r for r in rows if r["relation_tag"] == "nonsense_low"]) < target_counts["nonsense_low"]:
        a = random.choice(answers)
        b = random.choice(user_pool)
        # 避免把明显正确词塞进无意义分组
        if b == a:
            continue
        if b in hints_by_answer.get(a, []):
            continue
        push_row(a, b, "nonsense_low")

    # 保证条数
    if len(rows) > PAIR_COUNT:
        rows = rows[:PAIR_COUNT]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "answer",
                "user_input",
                "answer_category",
                "input_category_guess",
                "relation_tag",
                "expected_range",
                "score_0_100",
                "reason",
                "reviewer",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"written={OUTPUT_PATH} rows={len(rows)}")


if __name__ == "__main__":
    main()
