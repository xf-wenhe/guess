import csv
import json
import random
from pathlib import Path

RANDOM_SEED = 20260227
PAIR_COUNT = 500
INPUT_PATH = Path("assets/puzzles.json")
OUTPUT_PATH = Path("data/semantic_scoring_template.csv")


def main():
    random.seed(RANDOM_SEED)
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    answers = []
    answer_to_category = {}
    for item in data:
        answer = item.get("answer")
        category = item.get("category", "")
        if not answer:
            continue
        answers.append(answer)
        answer_to_category[answer] = category

    pairs = []
    seen = set()
    attempts = 0
    max_attempts = 100000

    while len(pairs) < PAIR_COUNT and attempts < max_attempts:
        attempts += 1
        a, b = random.sample(answers, 2)
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)

        cat_a = answer_to_category.get(a, "")
        cat_b = answer_to_category.get(b, "")

        if cat_a == cat_b:
            expected_range = "60-70"
            relation_tag = "same_category"
        else:
            expected_range = "0-40"
            relation_tag = "cross_category"

        pairs.append(
            {
                "id": len(pairs) + 1,
                "word_a": a,
                "word_b": b,
                "category_a": cat_a,
                "category_b": cat_b,
                "relation_tag": relation_tag,
                "expected_range": expected_range,
                "score_0_100": "",
                "reason": "",
                "reviewer": "",
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "word_a",
                "word_b",
                "category_a",
                "category_b",
                "relation_tag",
                "expected_range",
                "score_0_100",
                "reason",
                "reviewer",
            ],
        )
        writer.writeheader()
        writer.writerows(pairs)

    print(f"written={OUTPUT_PATH} rows={len(pairs)}")


if __name__ == "__main__":
    main()
