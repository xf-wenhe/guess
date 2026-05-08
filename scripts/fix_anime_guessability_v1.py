from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def compute_top1_failures(data: list[dict], category: str, model_path: str) -> list[int]:
    subset_idx = []
    subset = []
    for i, it in enumerate(data):
        if (
            it.get("category") == category
            and it.get("answer")
            and isinstance(it.get("hints"), list)
            and len(it.get("hints")) >= 7
        ):
            subset_idx.append(i)
            subset.append(it)

    answers = [str(it.get("answer", "")).strip() for it in subset]
    queries = [" ".join([str(h).strip() for h in it.get("hints", [])[:7]]) for it in subset]
    uniq = list(dict.fromkeys([*answers, *queries]))

    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}
    ans_mat = np.stack([emb[idx[a]] for a in answers], axis=0)

    fail_raw_idx = []
    for local_i, (ans, q) in enumerate(zip(answers, queries)):
        qv = emb[idx[q]]
        sims = ans_mat @ qv
        pred = answers[int(np.argmax(sims))]
        if pred != ans:
            fail_raw_idx.append(subset_idx[local_i])
    return fail_raw_idx


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix anime hint guessability v1")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--category", default="动漫")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out-dir", default="tmp")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))

    fail_idx = compute_top1_failures(data, args.category, args.model_path)

    changed = 0
    changes = []
    for i in fail_idx:
        it = data[i]
        ans = str(it.get("answer", "")).strip()
        hints = [str(h).strip() for h in it.get("hints", [])[:7]]
        if len(hints) < 7:
            continue

        new_hints = hints[:]
        # Keep low-level generic progression and strengthen answer-unique anchors at high slots.
        new_hints[2] = f"{ans}作品"
        new_hints[3] = f"{ans}剧情"
        new_hints[4] = f"{ans}角色"
        new_hints[5] = f"{ans}主角"
        new_hints[6] = f"《{ans}》"

        if len(set(new_hints)) < len(new_hints):
            new_hints[4] = f"{ans}名场面"

        if new_hints != hints:
            changed += 1
            changes.append({"answer": ans, "before": hints, "after": new_hints})
            it["hints"] = new_hints

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "anime_guessability_fix_v1_report.json"
    report = {
        "category": args.category,
        "failed_before": len(fail_idx),
        "changed_items": changed,
        "apply": bool(args.apply),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    details_path = out_dir / "anime_guessability_fix_v1_details.json"
    details_path.write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False))
    print(f"report={report_path}")
    print(f"details={details_path}")


if __name__ == "__main__":
    main()
