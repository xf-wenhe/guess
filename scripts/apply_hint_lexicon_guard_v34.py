from __future__ import annotations

import argparse
import json
from pathlib import Path

from hint_quality_v29_common import detect_cross_domain, normalize_hint


DEFAULT_POLICY = Path("data/hint_lexicon_policy_v34.json")


def pick_replacement(
    category: str,
    answer: str,
    used: set[str],
    idx: int,
    pool_by_category: dict[str, list[str]],
    global_pool: list[str],
) -> str:
    pool = list(pool_by_category.get(category, [])) + list(global_pool)
    if not pool:
        return "关键线索"

    for offset in range(len(pool)):
        cand = pool[(idx + offset) % len(pool)]
        if cand == answer:
            continue
        if cand in used:
            continue
        if detect_cross_domain(category, cand):
            continue
        return cand

    return pool[idx % len(pool)]


def run_guard(input_path: Path, out_dir: Path, policy_path: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    blacklist = set(policy.get("blacklist_exact", []))
    soft_blacklist = set(policy.get("soft_blacklist_exact", []))
    soft_min_count = int(policy.get("soft_min_count", 12))
    global_pool = [normalize_hint(x) for x in policy.get("global_pool", []) if normalize_hint(x)]

    by_category_raw = policy.get("by_category", {})
    by_category: dict[str, list[str]] = {}
    for k, vals in by_category_raw.items():
        if not isinstance(vals, list):
            continue
        cleaned = [normalize_hint(v) for v in vals if normalize_hint(v)]
        if cleaned:
            by_category[str(k)] = cleaned

    changed_items = 0
    replaced_hints = 0
    replaced_soft_hints = 0
    details: list[dict] = []

    hint_counts: dict[str, int] = {}
    for item in data:
        for h in (item.get("hints") or [])[:7]:
            hs = normalize_hint(h)
            if not hs:
                continue
            hint_counts[hs] = hint_counts.get(hs, 0) + 1

    for row_id, item in enumerate(data):
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        hints = [normalize_hint(h) for h in (item.get("hints") or []) if normalize_hint(h)][:7]
        if not hints:
            continue

        used = set(hints)
        new_hints = hints[:]
        touched = False

        for i, old in enumerate(hints):
            is_hard = old in blacklist
            is_soft = old in soft_blacklist and hint_counts.get(old, 0) >= soft_min_count
            if not is_hard and not is_soft:
                continue

            new_hint = pick_replacement(
                category=category,
                answer=answer,
                used=set(new_hints),
                idx=i,
                pool_by_category=by_category,
                global_pool=global_pool,
            )
            if not new_hint or new_hint == old:
                continue

            new_hints[i] = new_hint
            replaced_hints += 1
            if is_soft and not is_hard:
                replaced_soft_hints += 1
            touched = True
            details.append(
                {
                    "index": row_id,
                    "category": category,
                    "answer": answer,
                    "hint_index": i,
                    "old_hint": old,
                    "new_hint": new_hint,
                    "rule": "hard" if is_hard else "soft",
                }
            )

        if touched:
            item["hints"] = new_hints
            changed_items += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / "puzzles.lexicon_guard.v34.json"
    report = out_dir / "hints_lexicon_guard_v34_report.json"
    detail_path = out_dir / "hints_lexicon_guard_v34_details.json"

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    snapshot.write_text(text, encoding="utf-8")
    if apply:
        input_path.write_text(text, encoding="utf-8")

    rpt = {
        "input": str(input_path),
        "policy": str(policy_path),
        "snapshot": str(snapshot),
        "apply": apply,
        "soft_min_count": soft_min_count,
        "changed_items": changed_items,
        "replaced_hints": replaced_hints,
        "replaced_soft_hints": replaced_soft_hints,
    }
    report.write_text(json.dumps(rpt, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "report": rpt,
        "report_path": str(report),
        "details_path": str(detail_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply hint lexicon guard v34")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run_guard(
        input_path=Path(args.input),
        out_dir=Path(args.out_dir),
        policy_path=Path(args.policy),
        apply=args.apply,
    )
    rpt = result["report"]
    print(f"changed_items={rpt['changed_items']} replaced_hints={rpt['replaced_hints']} apply={rpt['apply']}")
    print(f"policy={rpt['policy']}")
    print(f"report={result['report_path']}")
    print(f"details={result['details_path']}")


if __name__ == "__main__":
    main()
