from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path

from hint_quality_v29_common import (
    FALLBACK_HINTS,
    dedupe_keep_order,
    is_meta_hint,
    normalize_hint,
    strip_template_suffix,
)


def clean_one_hint(hint: str) -> str:
    text = normalize_hint(hint)
    text = strip_template_suffix(text)
    return text


def run_clean(input_path: Path, out_dir: Path, apply: bool) -> dict:
    raw = input_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    changed_items = 0
    removed_hints = 0
    trimmed_suffix = 0

    cleaned = []
    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        old_hints = [normalize_hint(h) for h in (item.get("hints") or []) if normalize_hint(h)]

        new_hints = []
        for old in old_hints:
            stripped = clean_one_hint(old)
            if stripped != old:
                trimmed_suffix += 1

            bad, _ = is_meta_hint(stripped)
            if bad:
                removed_hints += 1
                continue
            if stripped == answer:
                removed_hints += 1
                continue
            if len(stripped) < 2:
                removed_hints += 1
                continue
            new_hints.append(stripped)

        new_hints = dedupe_keep_order(new_hints)

        fallback = FALLBACK_HINTS.get(category, [])
        for token in fallback:
            if token != answer and token not in new_hints:
                new_hints.append(token)
            if len(new_hints) >= 7:
                break

        if len(new_hints) < 7:
            for token in old_hints:
                token = clean_one_hint(token)
                if token != answer and token not in new_hints and len(token) >= 2:
                    new_hints.append(token)
                if len(new_hints) >= 7:
                    break

        new_hints = new_hints[:7]

        new_item = dict(item)
        if new_hints != old_hints[:7]:
            changed_items += 1
        new_item["hints"] = new_hints
        cleaned.append(new_item)

    cleaned_text = json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n"

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "puzzles.cleaned.v29.json"
    diff_path = out_dir / "puzzles.cleaned.v29.preview.diff"
    report_path = out_dir / "hints_clean_v29_report.json"

    snapshot_path.write_text(cleaned_text, encoding="utf-8")

    diff_lines = list(
        difflib.unified_diff(
            raw.splitlines(),
            cleaned_text.splitlines(),
            fromfile=str(input_path),
            tofile=str(snapshot_path),
            lineterm="",
            n=3,
        )
    )
    diff_path.write_text("\n".join(diff_lines) + ("\n" if diff_lines else ""), encoding="utf-8")

    if apply:
        input_path.write_text(cleaned_text, encoding="utf-8")

    report = {
        "input": str(input_path),
        "snapshot": str(snapshot_path),
        "diff_preview": str(diff_path),
        "apply": apply,
        "items": len(cleaned),
        "changed_items": changed_items,
        "removed_hints": removed_hints,
        "trimmed_suffix": trimmed_suffix,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "report": report,
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mechanical hint cleaner v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true", help="overwrite input file")
    args = parser.parse_args()

    result = run_clean(Path(args.input), Path(args.out_dir), apply=args.apply)
    report = result["report"]
    print(
        "items={items} changed_items={changed_items} removed_hints={removed_hints} trimmed_suffix={trimmed_suffix} apply={apply}".format(
            **report
        )
    )
    print(f"report={result['report_path']}")
    print(f"diff_preview={report['diff_preview']}")


if __name__ == "__main__":
    main()
