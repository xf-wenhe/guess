import json
import re
from pathlib import Path
from collections import Counter, defaultdict
import random
import sys

def get_dimension_pools_from_script(script_path: Path) -> dict[str, str]:
    """
    Parses the selfcheck_hint_skill_v2.py script to extract all hint dimension pools.
    Returns a flat dictionary mapping a hint to its dimension.
    """
    if not script_path.exists():
        print(f"Validation script not found at {script_path}", file=sys.stderr)
        return {}

    content = script_path.read_text(encoding='utf-8')
    
    # Regex to find all _DIMENSION_POOLS assignments
    pool_regex = re.compile(r"(\w+_DIMENSION_POOLS)\s*=\s*\{([^}]+)\}", re.DOTALL)
    
    hint_to_dimension = {}
    
    for match in pool_regex.finditer(content):
        pool_name = match.group(1)
        dimension_name = pool_name.replace('_DIMENSION_POOLS', '').lower()
        
        # Regex to find all hints within the set strings
        hints_str = match.group(2)
        hint_regex = re.compile(r"\"(.*?)\"|'(.*?)'")
        
        for hint_match in hint_regex.finditer(hints_str):
            hint = hint_match.group(1) or hint_match.group(2)
            if hint:
                hint_to_dimension[hint] = dimension_name
                
    return hint_to_dimension

def get_puzzle_hint_dimensions(puzzle_hints: list[str], hint_to_dimension: dict[str, str]) -> list[str]:
    """Gets the dimensions for a list of hints."""
    return [hint_to_dimension.get(h, 'unknown') for h in puzzle_hints]

def diversify_hints():
    """
    Reads the self-check report, identifies puzzles with adjacency and cap errors,
    and attempts to fix them by replacing hints from over-represented dimensions
    with hints from under-represented dimensions.
    """
    repo_root = Path(__file__).resolve().parents[1]
    puzzles_path = repo_root / "assets" / "puzzles.json"
    report_path = repo_root / "tmp" / "selfcheck_hint_skill_v2.json"
    script_path = repo_root / "scripts" / "selfcheck_hint_skill_v2.py"

    # 1. Load all necessary data
    if not report_path.exists() or not puzzles_path.exists():
        print("Error: Report or puzzles file not found.", file=sys.stderr)
        return 1

    with report_path.open('r', encoding='utf-8') as f:
        report = json.load(f)
    with puzzles_path.open('r', encoding='utf-8') as f:
        puzzles = json.load(f)
    
    hint_to_dimension = get_dimension_pools_from_script(script_path)
    if not hint_to_dimension:
        print("Error: Could not build hint-to-dimension mapping.", file=sys.stderr)
        return 1

    all_known_hints = list(hint_to_dimension.keys())
    puzzles_map = {p['answer']: p for p in puzzles}

    # 2. Identify all puzzles that need fixing
    answers_to_fix = set()
    for hit in report.get("adjacent_same_dimension_hits", []):
        answers_to_fix.add(hit['answer'])
    for hit in report.get("per_dimension_cap_hits", []):
        answers_to_fix.add(hit['answer'])

    if not answers_to_fix:
        print("No adjacency or cap errors found to fix.")
        return 0

    print(f"Found {len(answers_to_fix)} puzzles with errors. Starting diversification...")
    fix_count = 0

    # 3. Iterate and fix each problematic puzzle
    for answer in answers_to_fix:
        if answer not in puzzles_map:
            continue

        puzzle = puzzles_map[answer]
        original_hints = puzzle.get('hints', [])
        if len(original_hints) < 7:
            continue

        hints = original_hints[:7]
        
        # Find the most common dimension in this puzzle's hints
        current_dims = get_puzzle_hint_dimensions(hints, hint_to_dimension)
        dim_counts = Counter(d for d in current_dims if d != 'unknown')
        if not dim_counts:
            continue
        
        most_common_dim, count = dim_counts.most_common(1)[0]
        
        # Only proceed if a dimension is clearly over-represented
        if count > 1:
            # Find an index of a hint with the most common dimension to replace
            indices_to_replace = [i for i, dim in enumerate(current_dims) if dim == most_common_dim]
            if not indices_to_replace:
                continue
            
            idx_to_replace = random.choice(indices_to_replace)
            
            # Find a replacement hint from a dimension not currently used in the puzzle
            used_dimensions = set(current_dims)
            
            # Build a pool of candidate hints
            candidate_hints = [
                h for h in all_known_hints 
                if hint_to_dimension[h] not in used_dimensions and h not in hints
            ]
            
            if not candidate_hints:
                # Fallback: use any hint not already present
                candidate_hints = [h for h in all_known_hints if h not in hints]

            if candidate_hints:
                replacement_hint = random.choice(candidate_hints)
                
                # Replace the hint
                hints[idx_to_replace] = replacement_hint
                puzzle['hints'][:7] = hints
                fix_count += 1
                print(f"  - Diversified '{answer}': Replaced hint in dimension '{most_common_dim}' with new hint '{replacement_hint}'")

    # 4. Save the changes
    if fix_count > 0:
        print(f"\nDiversified hints for {fix_count} puzzles.")
        with puzzles_path.open('w', encoding='utf-8') as f:
            json.dump(puzzles, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated {puzzles_path}")
    else:
        print("No puzzles were modified.")
        
    return 0

if __name__ == "__main__":
    sys.exit(diversify_hints())
