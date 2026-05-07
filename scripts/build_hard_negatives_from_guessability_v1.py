from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDNAMES = [
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
]


def add_row(rows: list[dict], seen: set[tuple[str, str]], answer: str, guess: str, reason: str) -> None:
    key = (answer, guess)
    if not answer or not guess or answer == guess or key in seen:
        return
    seen.add(key)
    rows.append(
        {
            "id": "",
            "answer": answer,
            "user_input": guess,
            "answer_category": "动漫",
            "input_category_guess": "动漫",
            "relation_tag": "hard_negative_low",
            "expected_range": "0-25",
            "score_0_100": "15",
            "reason": reason,
            "reviewer": "hard_negative_miner_v1",
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hard-negative training rows from guessability details")
    parser.add_argument(
        "--details",
        default="tmp/xuanheng_current_check_guess/anime_guessability_v1_details.json",
        help="guessability details json path",
    )
    parser.add_argument(
        "--out",
        default="data/hard_negatives_from_guessability_v1.csv",
        help="output csv path",
    )
    parser.add_argument("--max-rows", type=int, default=300)
    args = parser.parse_args()

    details_path = Path(args.details)
    if not details_path.exists():
        raise SystemExit(f"missing details: {details_path}")

    details = json.loads(details_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for item in details:
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue
        if bool(item.get("pass")):
            continue

        pred_top1 = str(item.get("pred_top1", "")).strip()
        add_row(rows, seen, answer, pred_top1, "failed_top1_confusion")

        for idx, cand in enumerate(item.get("top3") or []):
            guess = str(cand).strip()
            add_row(rows, seen, answer, guess, f"failed_top3_confusion_rank{idx+1}")

        if len(rows) >= args.max_rows:
            break

    for i, row in enumerate(rows, start=1):
        row["id"] = str(i)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows[: args.max_rows])

    print(
        json.dumps(
            {
                "details": str(details_path),
                "written": str(out_path),
                "rows": min(len(rows), args.max_rows),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
