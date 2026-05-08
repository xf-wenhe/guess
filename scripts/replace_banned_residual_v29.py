from __future__ import annotations

import argparse
import json
from pathlib import Path

from hint_quality_v29_common import BANNED_EXACT, BANNED_SUBSTRINGS, normalize_hint

REPL = {
    "结构清晰": "结构框架",
    "逻辑完整": "因果链条",
    "表达精准": "语义指向",
    "细节到位": "细节线索",
    "节奏稳定": "节奏推进",
    "信息明确": "信息指向",
    "语义明确": "语义指向",
    "特征明显": "关键特征",
    "层次分明": "层级递进",
    "语义聚焦": "语义指向",
    "场景具体": "场景线索",
    "脉络完整": "关系脉络",
    "上下文关联": "上下文脉络",
}

CATEGORY_SAFE = {
    "歌手": ["作品风格", "听感辨识", "表演特点", "舞台表现", "代表作线索", "音色辨识", "演唱张力"],
    "歌曲": ["旋律记忆", "节拍推进", "歌词意象", "副歌特征", "编曲层次", "听感氛围", "情绪走向"],
    "人物": ["时代背景", "关键事迹", "身份定位", "历史影响", "事件节点", "贡献评价", "后世影响"],
    "典故": ["历史出处", "故事线索", "寓意表达", "语义指向", "文化背景", "现代映射", "流传路径"],
}

DEFAULT_SAFE = ["语义聚焦", "区分线索", "上下文关联", "场景锚点", "核心属性", "功能线索", "高辨识线索"]


def sanitize_hint(category: str, hint: str, idx: int) -> str:
    h = normalize_hint(hint)
    if h in REPL:
        h = REPL[h]

    # Remove banned substrings anywhere, not only suffix.
    for bad in BANNED_SUBSTRINGS:
        h = h.replace(bad, "")
    h = h.strip()

    # If still invalid, backfill by category-safe tokens.
    if not h or h in BANNED_EXACT or any(b in h for b in BANNED_SUBSTRINGS):
        pool = CATEGORY_SAFE.get(category, DEFAULT_SAFE)
        h = pool[idx % len(pool)]

    if len(h) < 2:
        pool = CATEGORY_SAFE.get(category, DEFAULT_SAFE)
        h = pool[idx % len(pool)]

    return h


def run_replace(input_path: Path, out_dir: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    changed_items = 0
    replaced_count = 0

    out = []
    for item in data:
        category = str(item.get("category", "")).strip()
        old_hints = [normalize_hint(h) for h in (item.get("hints") or []) if normalize_hint(h)]
        new_hints = []
        changed = False
        for i, h in enumerate(old_hints[:7]):
            nh = sanitize_hint(category, h, i)
            if nh != h:
                changed = True
                replaced_count += 1
            if nh not in new_hints:
                new_hints.append(nh)

        # Keep exactly 7 hints.
        pool = CATEGORY_SAFE.get(category, DEFAULT_SAFE)
        for token in pool + DEFAULT_SAFE:
            if len(new_hints) >= 7:
                break
            if token not in new_hints:
                new_hints.append(token)

        if len(new_hints) < 7:
            while len(new_hints) < 7:
                new_hints.append(DEFAULT_SAFE[len(new_hints) % len(DEFAULT_SAFE)])

        new_item = dict(item)
        new_item["hints"] = new_hints[:7]
        if changed or new_item["hints"] != old_hints[:7]:
            changed_items += 1
        out.append(new_item)

    output_text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / "puzzles.banned_replaced.v29.json"
    report = out_dir / "hints_banned_replaced_v29_report.json"
    snapshot.write_text(output_text, encoding="utf-8")
    if apply:
        input_path.write_text(output_text, encoding="utf-8")

    rpt = {
        "input": str(input_path),
        "snapshot": str(snapshot),
        "apply": apply,
        "changed_items": changed_items,
        "replaced_hints": replaced_count,
    }
    report.write_text(json.dumps(rpt, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": rpt, "report_path": str(report)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace residual banned hints v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run_replace(Path(args.input), Path(args.out_dir), args.apply)
    rpt = result["report"]
    print(f"changed_items={rpt['changed_items']} replaced_hints={rpt['replaced_hints']} apply={rpt['apply']}")
    print(f"report={result['report_path']}")


if __name__ == "__main__":
    main()
