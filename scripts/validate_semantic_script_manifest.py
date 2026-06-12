#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "scripts" / "semantic_script_manifest.json"
DEFAULT_README = ROOT / "scripts" / "README.md"

EXISTING_GROUPS = (
    "current_entrypoints",
    "nightly_pipeline",
    "review_data_loop",
    "source_dataset_builders",
    "manual_or_historical",
)

DOCUMENTED_GROUPS = (
    "current_entrypoints",
    "nightly_pipeline",
    "review_data_loop",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the maintained semantic script inventory.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def validate(manifest_path: Path, readme_path: Path) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    readme = readme_path.read_text(encoding="utf-8")
    scripts_dir = manifest_path.parent

    if manifest.get("schema_version") != 1:
        issues.append({"type": "schema_version", "detail": f"expected schema_version=1, got {manifest.get('schema_version')!r}"})

    seen: dict[str, str] = {}
    for group in EXISTING_GROUPS + ("removed_obsolete",):
        for script_name in manifest.get(group, []):
            previous = seen.get(script_name)
            if previous:
                issues.append({"type": "duplicate", "detail": f"{script_name} appears in both {previous} and {group}"})
            seen[script_name] = group

    for group in EXISTING_GROUPS:
        for script_name in manifest.get(group, []):
            if not (scripts_dir / script_name).exists():
                issues.append({"type": "missing_script", "detail": f"{group}: {script_name}"})

    for script_name in manifest.get("removed_obsolete", []):
        if (scripts_dir / script_name).exists():
            issues.append({"type": "obsolete_present", "detail": script_name})

    for group in DOCUMENTED_GROUPS:
        for script_name in manifest.get(group, []):
            if f"`{script_name}`" not in readme:
                issues.append({"type": "readme_missing", "detail": f"{group}: {script_name}"})

    if "semantic_script_manifest.json" not in readme:
        issues.append({"type": "readme_missing", "detail": "semantic_script_manifest.json"})

    return {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "manifest": str(manifest_path),
        "readme": str(readme_path),
    }


def main() -> int:
    args = parse_args()
    result = validate(args.manifest, args.readme)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ok={result['ok']}")
        print(f"issue_count={result['issue_count']}")
        for issue in result["issues"]:
            print(f"- {issue['type']}: {issue['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
