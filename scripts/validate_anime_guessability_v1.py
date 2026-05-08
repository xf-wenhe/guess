from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


META_TERMS = {
    "标志性冲突",
    "代表性设定",
    "核心母题",
    "高光桥段",
    "知名剧情节点",
    "粉丝高共识",
    "答案锁定线索",
    "唯一锚点",
    "终局指向",
    "强辨识设定",
}


def run_validate(input_path: Path, category: str, model_path: str, out_dir: Path) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    subset = [
        it
        for it in data
        if it.get("category") == category
        and it.get("answer")
        and isinstance(it.get("hints"), list)
        and len(it.get("hints")) >= 7
    ]

    answers = [str(it.get("answer", "")).strip() for it in subset]
    queries = [" ".join([str(h).strip() for h in it.get("hints", [])[:7]]) for it in subset]

    uniq = list(dict.fromkeys([*answers, *queries]))
    model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
    emb = model.encode(uniq, normalize_embeddings=True, batch_size=256)
    idx = {t: i for i, t in enumerate(uniq)}

    ans_mat = np.stack([emb[idx[a]] for a in answers], axis=0)

    passed = 0
    leak_hits = 0
    char_overlap_hits = 0
    meta_descriptor_hits = 0
    details = []
    for it, ans, q in zip(subset, answers, queries):
        qv = emb[idx[q]]
        sims = ans_mat @ qv
        rank = np.argsort(-sims)
        pred = answers[int(rank[0])]
        top3 = [answers[int(i)] for i in rank[:3]]
        hints7 = it.get("hints", [])[:7]
        has_leak = any((ans in str(h)) or (f"《{ans}》" in str(h)) for h in hints7)
        if has_leak:
            leak_hits += 1

        ans_chars = {ch for ch in ans if ch.strip()}
        has_char_overlap = False
        for h in hints7:
            h_chars = {ch for ch in str(h) if ch.strip()}
            if ans_chars & h_chars:
                has_char_overlap = True
                break
        if has_char_overlap:
            char_overlap_hits += 1

        has_meta_descriptor = any(str(h).strip() in META_TERMS for h in hints7)
        if has_meta_descriptor:
            meta_descriptor_hits += 1

        ok = (pred == ans) and (not has_leak) and (not has_char_overlap) and (not has_meta_descriptor)
        if ok:
            passed += 1
        details.append(
            {
                "answer": ans,
                "hints": hints7,
                "pred_top1": pred,
                "top3": top3,
                "answer_leak": has_leak,
                "char_overlap": has_char_overlap,
                "meta_descriptor": has_meta_descriptor,
                "pass": ok,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "input": str(input_path),
        "category": category,
        "total": len(subset),
        "passed": passed,
        "ratio": round(passed / len(subset), 4) if subset else 0.0,
        "answer_leak_hits": leak_hits,
        "char_overlap_hits": char_overlap_hits,
        "meta_descriptor_hits": meta_descriptor_hits,
        "method": "top1_over_answer_set",
        "model_path": model_path,
    }
    rp = out_dir / "anime_guessability_v1_report.json"
    dp = out_dir / "anime_guessability_v1_details.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dp.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": report, "report_path": str(rp), "details_path": str(dp)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate anime hint guessability v1")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--category", default="动漫")
    parser.add_argument("--model-path", default="models/bge-m3-finetuned-v27-semreal-anchor")
    parser.add_argument("--out-dir", default="tmp")
    args = parser.parse_args()

    out = run_validate(
        input_path=Path(args.input),
        category=args.category,
        model_path=args.model_path,
        out_dir=Path(args.out_dir),
    )
    r = out["report"]
    print(f"category={r['category']} total={r['total']} passed={r['passed']} ratio={r['ratio']}")
    print(f"report={out['report_path']}")
    print(f"details={out['details_path']}")


if __name__ == "__main__":
    main()
