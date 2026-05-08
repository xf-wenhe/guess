from __future__ import annotations

import argparse
import json
from pathlib import Path


NOISY_TOKENS = {
    "家庭日常",
    "同学伙伴",
    "校园日常",
    "学业烦恼",
    "邻里生活",
    "日常困境",
    "日常线索",
    "调查线索",
    "生活插曲",
    "国漫",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Denoise failed anime hints with answer anchors")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--details", default="tmp/xuanheng_baseline_guess/anime_guessability_v1_details.json")
    parser.add_argument("--map", default="data/anime_guess_master_map_v1.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", default="tmp/denoise_anime_failed_hints_v1_preview.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    details = json.loads(Path(args.details).read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))

    failed_answers = {str(d.get("answer", "")).strip() for d in details if not bool(d.get("pass"))}
    failed_answers.discard("")

    changed_items = 0
    changed_slots = 0
    touched_answers: list[str] = []

    for item in data:
        if item.get("category") != "动漫":
            continue

        answer = str(item.get("answer", "")).strip()
        if answer not in failed_answers:
            continue

        current = [str(x).strip() for x in (item.get("hints") or [])[:7]]
        base = [str(x).strip() for x in mapping.get(answer, [])[:7]]
        if len(current) < 7 or len(base) < 7:
            continue

        updated = current[:]
        local_changes = 0
        for idx, hint in enumerate(updated):
            if hint not in NOISY_TOKENS:
                continue
            for cand in base:
                if cand and cand not in updated:
                    updated[idx] = cand
                    local_changes += 1
                    break

        if updated != current:
            item["hints"] = updated
            changed_items += 1
            changed_slots += local_changes
            touched_answers.append(answer)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "input": str(input_path),
        "failed_answers": len(failed_answers),
        "changed_items": changed_items,
        "changed_slots": changed_slots,
        "touched_answers": sorted(set(touched_answers)),
        "apply": bool(args.apply),
        "preview": str(out_path),
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
