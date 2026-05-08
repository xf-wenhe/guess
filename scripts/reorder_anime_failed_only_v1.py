from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def main() -> None:
    parser = argparse.ArgumentParser(description="Reorder failed anime hints only by answer similarity")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--details", default="tmp/xuanheng_pre_apply_guess/anime_guessability_v1_details.json")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", default="tmp/reorder_anime_failed_only_v1_preview.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    details = json.loads(Path(args.details).read_text(encoding="utf-8"))
    failed = {str(d.get("answer", "")).strip() for d in details if not bool(d.get("pass"))}
    failed.discard("")

    target_items = [
        it
        for it in data
        if it.get("category") == "动漫"
        and str(it.get("answer", "")).strip() in failed
        and isinstance(it.get("hints"), list)
        and len(it.get("hints")) >= 7
    ]

    texts: list[str] = []
    for it in target_items:
        texts.append(str(it.get("answer", "")).strip())
        texts.extend([str(h).strip() for h in it.get("hints", [])[:7]])
    uniq = list(dict.fromkeys([x for x in texts if x]))

    model = SentenceTransformer(args.model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    changed_items = 0
    touched_answers: list[str] = []
    for it in target_items:
        answer = str(it.get("answer", "")).strip()
        hints = [str(h).strip() for h in it.get("hints", [])[:7]]
        av = emb[idx[answer]]

        scored: list[tuple[float, str]] = []
        for h in hints:
            hv = emb[idx[h]]
            sim = float(np.dot(av, hv))
            scored.append((sim, h))
        scored.sort(key=lambda x: (x[0], x[1]))

        reordered: list[str] = []
        for _, h in scored:
            if h not in reordered:
                reordered.append(h)

        if len(reordered) == 7 and reordered != hints:
            it["hints"] = reordered
            changed_items += 1
            touched_answers.append(answer)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.apply:
        input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "input": str(input_path),
        "failed_answers": len(failed),
        "changed_items": changed_items,
        "touched_answers": sorted(set(touched_answers)),
        "apply": bool(args.apply),
        "preview": str(out_path),
        "model_path": args.model_path,
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
