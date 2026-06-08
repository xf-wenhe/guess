#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TODO = ROOT / "docs" / "SEMANTIC_TRAINING_TODO.md"
CHECKBOX_RE = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<text>.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize semantic training goal TODO progress.")
    parser.add_argument("--todo", type=Path, default=DEFAULT_TODO)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-completed", action="store_true")
    return parser.parse_args()


def parse_todo(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    current_section = "Preamble"
    sections: dict[str, list[dict[str, object]]] = {}
    last_updated = ""
    goal = ""

    for line in text.splitlines():
        if line.startswith("Last updated:"):
            last_updated = line.split(":", 1)[1].strip()
        elif line.startswith("Goal:"):
            goal = line.split(":", 1)[1].strip()
        elif line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
        else:
            match = CHECKBOX_RE.match(line)
            if match:
                done = match.group("mark").lower() == "x"
                sections.setdefault(current_section, []).append(
                    {
                        "section": current_section,
                        "done": done,
                        "text": match.group("text").strip(),
                    }
                )

    items = [item for section_items in sections.values() for item in section_items]
    done_count = sum(1 for item in items if item["done"])
    pending = [item for item in items if not item["done"]]
    by_section = {}
    for section, section_items in sections.items():
        if not section_items:
            continue
        section_done = sum(1 for item in section_items if item["done"])
        by_section[section] = {
            "done": section_done,
            "total": len(section_items),
            "pending": [item["text"] for item in section_items if not item["done"]],
        }

    return {
        "todo": str(path),
        "last_updated": last_updated,
        "goal": goal,
        "done": done_count,
        "total": len(items),
        "pending": len(pending),
        "percent_done": round((done_count / len(items)) * 100.0, 1) if items else 0.0,
        "by_section": by_section,
        "pending_items": pending,
        "completed_items": [item for item in items if item["done"]],
    }


def print_human(payload: dict[str, object], show_completed: bool) -> None:
    print(f"todo={payload['todo']}")
    print(f"last_updated={payload['last_updated']}")
    print(f"progress={payload['done']}/{payload['total']} ({payload['percent_done']}%)")
    print(f"pending={payload['pending']}")
    print("")
    print("pending_items:")
    pending_items = payload["pending_items"]
    if pending_items:
        for item in pending_items:
            print(f"- [{item['section']}] {item['text']}")
    else:
        print("- none")

    if show_completed:
        print("")
        print("completed_items:")
        for item in payload["completed_items"]:
            print(f"- [{item['section']}] {item['text']}")


def main() -> int:
    args = parse_args()
    payload = parse_todo(args.todo)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload, args.show_completed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
