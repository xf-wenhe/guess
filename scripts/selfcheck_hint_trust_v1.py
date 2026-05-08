#!/usr/bin/env python3
import argparse
import collections
import json
import sys
from pathlib import Path


BANNED_GENERIC = {
    "关键线索",
    "阶段线索",
    "状态线索",
    "情境线索",
    "现场变化",
    "过程观察",
    "执行过程",
    "步骤推进",
    "方向判断",
    "细节变化",
    "常见场景",
    "整体节奏",
    "结果走向",
    "临场处理",
    "过程细节",
    "先后顺序",
}


def norm(text: str) -> str:
    return str(text).replace(" ", "")


def load_game_special(repo_root: Path):
    sys.path.append(str(repo_root / "scripts"))
    import rewrite_game_hints_v29 as rg  # pylint: disable=import-error

    return rg.GAME_SPECIAL


def main() -> int:
    parser = argparse.ArgumentParser(description="Hint trust self-check (strict gates)")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--report", default="tmp/selfcheck_hint_trust_v1.json")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_path = repo_root / args.input
    report_path = repo_root / args.report

    arr = json.loads(data_path.read_text(encoding="utf-8"))
    anime_map = json.loads((repo_root / "data/anime_guess_master_map_v1.json").read_text(encoding="utf-8"))
    food_map = json.loads((repo_root / "data/food_hint_style_map_v2.json").read_text(encoding="utf-8"))
    game_map = load_game_special(repo_root)

    # 1) repeated full sets
    full_sets = collections.Counter(tuple((it.get("hints") or [])[:7]) for it in arr)
    repeated_sets = [(list(k), v) for k, v in full_sets.items() if v >= 2]

    # 2) banned generic tokens
    generic_hits = []
    for it in arr:
        cat = str(it.get("category", ""))
        ans = str(it.get("answer", ""))
        for idx, hint in enumerate((it.get("hints") or [])[:7], start=1):
            if norm(hint) in BANNED_GENERIC:
                generic_hits.append({"category": cat, "answer": ans, "slot": idx, "hint": hint})

    # 3) early-anchor proxy (slots 1-6 exact hit in answer-specific anchor pools)
    proxy_rules = {
        "动漫": anime_map,
        "美食": food_map,
        "游戏": game_map,
    }
    early_hits = {"动漫": [], "美食": [], "游戏": []}
    totals = {"动漫": 0, "美食": 0, "游戏": 0}
    for it in arr:
        cat = str(it.get("category", "")).strip()
        if cat not in proxy_rules:
            continue
        totals[cat] += 1
        ans = str(it.get("answer", "")).strip()
        anchors = {norm(x) for x in proxy_rules[cat].get(ans, [])}
        hints = [str(x) for x in (it.get("hints") or [])[:7]]
        hit_slots = []
        for i, h in enumerate(hints[:6], start=1):
            if norm(h) in anchors:
                hit_slots.append(i)
        if hit_slots:
            early_hits[cat].append(
                {
                    "answer": ans,
                    "hit_slots": hit_slots,
                    "hints": hints,
                }
            )

    report = {
        "items": len(arr),
        "repeated_full_set_count": len(repeated_sets),
        "repeated_full_sets": repeated_sets[:100],
        "banned_generic_hit_count": len(generic_hits),
        "banned_generic_hits": generic_hits[:300],
        "early_anchor_proxy": {
            cat: {
                "total": totals[cat],
                "offender_count": len(early_hits[cat]),
                "offenders": early_hits[cat],
            }
            for cat in ["动漫", "美食", "游戏"]
        },
        "thresholds": {
            "repeated_full_set_count": 0,
            "banned_generic_hit_count": 0,
            "early_anchor_proxy_anime": 0,
            "early_anchor_proxy_food": 0,
            "early_anchor_proxy_game": 0,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fail = []
    if report["repeated_full_set_count"] > 0:
        fail.append(f"repeated_full_set_count={report['repeated_full_set_count']}")
    if report["banned_generic_hit_count"] > 0:
        fail.append(f"banned_generic_hit_count={report['banned_generic_hit_count']}")
    if len(early_hits["动漫"]) > 0:
        fail.append(f"early_anchor_proxy_anime={len(early_hits['动漫'])}")
    if len(early_hits["美食"]) > 0:
        fail.append(f"early_anchor_proxy_food={len(early_hits['美食'])}")
    if len(early_hits["游戏"]) > 0:
        fail.append(f"early_anchor_proxy_game={len(early_hits['游戏'])}")

    print(f"report={report_path}")
    if fail:
        print("result=FAIL")
        print("reasons=" + ", ".join(fail))
        return 1

    print("result=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
