#!/usr/bin/env python3
"""
Merge approved error-review cases into the gold training splits.

Reads  : data/semantic_error_review_template_v1.csv
         (new rows where review_status == "approved")
         (repair rows where review_status == "merged" but the pair is missing
          from both gold and holdout outputs)

Outputs:
  data/gold_v26_manual_anchor.csv  ← appends train + calib rows (80:20 split)
  data/semantic_holdout_v1.csv     ← appends holdout rows (20 % of approved)

Split ratio: 60 % train  |  20 % calib  |  20 % holdout
  (train + calib go into gold_v26_manual_anchor.csv;
   holdout goes into semantic_holdout_v1.csv and is NEVER used for training)

Usage:
    python scripts/merge_error_review_into_gold_v1.py [--dry-run]

After running, retrain with:
    bash scripts/nightly_train_v26.sh
"""

import argparse, csv, random, sys
from pathlib import Path

REVIEW_CSV  = Path("data/semantic_error_review_template_v1.csv")
GOLD_CSV    = Path("data/gold_v26_manual_anchor.csv")
HOLDOUT_CSV = Path("data/semantic_holdout_v1.csv")

GOLD_FIELDS = [
    "id", "answer", "user_input",
    "answer_category", "input_category_guess",
    "relation_tag", "expected_range",
    "score_0_100", "reason", "reviewer",
]

HOLDOUT_FIELDS = [
    "case_id", "split", "answer", "user_input",
    "score_0_100", "relation_tag",
    "error_type", "rationale", "reviewer", "status",
]

RANDOM_SEED = 42

# ── score → expected_range helper ────────────────────────────────────────────

def score_to_range(s: int) -> str:
    if s <= 10:   return "0-10"
    if s <= 25:   return "11-25"
    if s <= 40:   return "26-40"
    if s <= 55:   return "41-55"
    if s <= 70:   return "56-70"
    if s <= 85:   return "71-85"
    if s <= 95:   return "86-95"
    return "96-100"


# ── dedup helpers ─────────────────────────────────────────────────────────────

def load_existing_pairs(path: Path) -> set:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {(r.get("answer", ""), r.get("user_input", "")) for r in rows}

def max_id_in(path: Path, id_col: str) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return max((int(r[id_col]) for r in rows if r.get(id_col, "").isdigit()), default=0)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be written without writing")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()

    if not REVIEW_CSV.exists():
        print(f"[error] {REVIEW_CSV} not found", file=sys.stderr)
        sys.exit(1)

    # Load review rows
    with REVIEW_CSV.open(encoding="utf-8", newline="") as f:
        all_rows = list(csv.DictReader(f))

    existing_gold    = load_existing_pairs(GOLD_CSV)
    existing_holdout = load_existing_pairs(HOLDOUT_CSV)

    approved = [r for r in all_rows if r.get("review_status", "").strip().lower() == "approved"]
    repair_gold = [
        r for r in all_rows
        if r.get("review_status", "").strip().lower() == "merged"
        and (r["answer"], r["user_input"]) not in existing_gold
        and (r["answer"], r["user_input"]) not in existing_holdout
    ]
    print(
        f"[read]  total rows={len(all_rows)}  approved={len(approved)}"
        f"  repair_gold={len(repair_gold)}"
    )

    if not approved and not repair_gold:
        print("[done]  No approved rows and no repair rows — nothing to merge.")
        print("        Set review_status='approved' for new rows or keep merged rows materialized.")
        return

    # Shuffle + split only for newly approved rows.
    rng = random.Random(args.seed)
    rng.shuffle(approved)
    n        = len(approved)
    n_hold   = max(1, round(n * 0.20))
    n_calib  = max(1, round(n * 0.20))
    n_train  = n - n_hold - n_calib

    holdout_rows = approved[:n_hold]
    calib_rows   = approved[n_hold : n_hold + n_calib]
    train_rows   = approved[n_hold + n_calib :]

    print(
        f"[split] train={len(train_rows)}  calib={len(calib_rows)}"
        f"  holdout={len(holdout_rows)}  repair_gold={len(repair_gold)}"
    )

    gold_next_id     = max_id_in(GOLD_CSV, "id") + 1
    holdout_next_id  = max_id_in(HOLDOUT_CSV, "case_id") + 1

    def to_gold_row(r, split_label):
        pair = (r["answer"], r["user_input"])
        if pair in existing_gold:
            return None
        existing_gold.add(pair)
        nonlocal gold_next_id
        cid = gold_next_id; gold_next_id += 1
        score = int(r["corrected_score"])
        return {
            "id":                  cid,
            "answer":              r["answer"],
            "user_input":          r["user_input"],
            "answer_category":     "",
            "input_category_guess": "",
            "relation_tag":        r["error_type"],
            "expected_range":      score_to_range(score),
            "score_0_100":         score,
            "reason":              r["why_wrong"][:80],
            "reviewer":            f"error_review_v1_{split_label}",
        }

    def to_holdout_row(r):
        pair = (r["answer"], r["user_input"])
        if pair in existing_gold:
            return None
        if pair in existing_holdout:
            return None
        existing_holdout.add(pair)
        nonlocal holdout_next_id
        cid = holdout_next_id; holdout_next_id += 1
        return {
            "case_id":      cid,
            "split":        "holdout",
            "answer":       r["answer"],
            "user_input":   r["user_input"],
            "score_0_100":  int(r["corrected_score"]),
            "relation_tag": r["error_type"],
            "error_type":   r["error_type"],
            "rationale":    r["why_wrong"][:80],
            "reviewer":     r.get("reviewer", "") or "error_review_v1",
            "status":       "frozen",
        }

    gold_new = []
    for r in repair_gold:
        row = to_gold_row(r, "repair")
        if row: gold_new.append(row)
    for r in train_rows:
        row = to_gold_row(r, "train")
        if row: gold_new.append(row)
    for r in calib_rows:
        row = to_gold_row(r, "calib")
        if row: gold_new.append(row)

    hold_new = []
    for r in holdout_rows:
        row = to_holdout_row(r)
        if row: hold_new.append(row)

    # ── dry-run output ──────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n[dry-run] Would append {len(gold_new)} rows → {GOLD_CSV}")
        for row in gold_new[:5]:
            print(f"  {row['answer']:8s} vs {row['user_input']:10s}  score={row['score_0_100']:3d}  {row['relation_tag']}")
        if len(gold_new) > 5:
            print(f"  ... (+{len(gold_new)-5} more)")
        print(f"\n[dry-run] Would append {len(hold_new)} rows → {HOLDOUT_CSV}")
        for row in hold_new[:3]:
            print(f"  {row['answer']:8s} vs {row['user_input']:10s}  score={row['score_0_100']:3d}")
        return

    # ── write gold ──────────────────────────────────────────────────────────
    gold_write_header = not GOLD_CSV.exists()
    with GOLD_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=GOLD_FIELDS)
        if gold_write_header:
            w.writeheader()
        w.writerows(gold_new)
    print(f"[gold]    appended {len(gold_new)} rows → {GOLD_CSV}")

    # ── write holdout ───────────────────────────────────────────────────────
    hold_write_header = not HOLDOUT_CSV.exists()
    with HOLDOUT_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HOLDOUT_FIELDS)
        if hold_write_header:
            w.writeheader()
        w.writerows(hold_new)
    print(f"[holdout] appended {len(hold_new)} rows → {HOLDOUT_CSV}")

    # ── mark rows as merged in review CSV ───────────────────────────────────
    with REVIEW_CSV.open(encoding="utf-8", newline="") as f:
        orig_rows = list(csv.DictReader(f))
        orig_fields = orig_rows[0].keys() if orig_rows else []

    merged_pairs = {(r["answer"], r["user_input"]) for r in gold_new + hold_new}
    for row in orig_rows:
        if (row["answer"], row["user_input"]) in merged_pairs:
            row["review_status"] = "merged"

    with REVIEW_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(orig_fields))
        w.writeheader()
        w.writerows(orig_rows)
    print(f"[review]  marked {len(merged_pairs)} rows as 'merged' in {REVIEW_CSV}")

    print("\n[next] Run training:")
    print("       bash scripts/nightly_train_v26.sh")
    print("       (or for eval only: .venv/bin/python scripts/eval_v26_gold.py)")


if __name__ == "__main__":
    main()
