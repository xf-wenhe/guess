import json
from pathlib import Path
import random
from collections import defaultdict

def fix_adjacency_and_cap_errors():
    """
    Reads the self-check report, identifies puzzles with adjacency and cap errors,
    and attempts to fix them by shuffling the hints of the problematic puzzles.
    """
    repo_root = Path(__file__).resolve().parents[1]
    puzzles_path = repo_root / "assets" / "puzzles.json"
    report_path = repo_root / "tmp" / "selfcheck_hint_skill_v2.json"

    if not report_path.exists():
        print(f"Error: Report file not found at {report_path}")
        return

    if not puzzles_path.exists():
        print(f"Error: Puzzles file not found at {puzzles_path}")
        return

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    with open(puzzles_path, 'r', encoding='utf-8') as f:
        puzzles = json.load(f)

    puzzles_map = {p['answer']: p for p in puzzles}
    
    answers_to_fix = set()

    # Collect all unique answers that have errors
    for hit in report.get("adjacent_same_dimension_hits", []):
        answers_to_fix.add(hit['answer'])
    
    for hit in report.get("per_dimension_cap_hits", []):
        answers_to_fix.add(hit['answer'])

    if not answers_to_fix:
        print("No adjacency or cap errors found to fix.")
        return

    print(f"Found {len(answers_to_fix)} puzzles with adjacency or cap errors. Attempting to shuffle hints...")

    fix_count = 0
    for answer in answers_to_fix:
        if answer in puzzles_map:
            puzzle = puzzles_map[answer]
            if 'hints' in puzzle and len(puzzle['hints']) > 1:
                # Simple shuffle of the first 7 hints
                hints_to_shuffle = puzzle['hints'][:7]
                random.shuffle(hints_to_shuffle)
                puzzle['hints'][:7] = hints_to_shuffle
                fix_count += 1
                print(f"  - Shuffled hints for: {puzzle.get('category')}/{answer}")

    if fix_count > 0:
        print(f"\nShuffled hints for {fix_count} puzzles.")
        # Write the modified puzzles back to the file
        with open(puzzles_path, 'w', encoding='utf-8') as f:
            json.dump(puzzles, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated {puzzles_path}")
    else:
        print("No puzzles were modified.")

if __name__ == "__main__":
    fix_adjacency_and_cap_errors()
