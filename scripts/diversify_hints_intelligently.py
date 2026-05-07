import json
import re
from pathlib import Path
from collections import Counter
import random
import sys
import ast

def get_dimension_pools_from_script(script_path: Path) -> dict[str, str]:
    """
    Parses the selfcheck_hint_skill_v2.py script using an Abstract Syntax Tree (AST)
    to safely and accurately extract all hint dimension pools.
    Returns a flat dictionary mapping a hint to its dimension.
    """
    if not script_path.exists():
        print(f"Validation script not found at {script_path}", file=sys.stderr)
        return {}

    content = script_path.read_text(encoding='utf-8')
    hint_to_dimension = {}

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                # Check if the assignment is to a _DIMENSION_POOLS variable
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith('_DIMENSION_POOLS'):
                        # The value of the assignment should be a dictionary
                        if isinstance(node.value, ast.Dict):
                            pools = ast.literal_eval(node.value)
                            for dimension, hints_set in pools.items():
                                if isinstance(hints_set, set):
                                    for hint in hints_set:
                                        hint_to_dimension[hint] = dimension
                        break # Move to the next node once we've processed this assignment
    except SyntaxError as e:
        print(f"Error parsing the syntax of {script_path}: {e}", file=sys.stderr)
        return {}

    return hint_to_dimension

def get_puzzle_hint_dimensions(puzzle_hints: list[str], hint_to_dimension: dict[str, str]) -> list[str]:
    """Gets the dimensions for a list of hints."""
    return [hint_to_dimension.get(h, 'unknown') for h in puzzle_hints]

def get_max_hint_len(repo_root: Path) -> int:
    """Reads the policy file to get the max_chars_per_hint constraint."""
    policy_path = repo_root / "data" / "final_hint_policy_v1.json"
    if not policy_path.exists():
        print("Warning: Policy file not found. Using default max hint length of 5.", file=sys.stderr)
        return 5
    
    try:
        policy = json.loads(policy_path.read_text(encoding='utf-8'))
        return int(policy.get("universal_constraints", {}).get("max_chars_per_hint", 5))
    except (json.JSONDecodeError, KeyError):
        print("Warning: Could not read max_chars_per_hint from policy. Using default of 5.", file=sys.stderr)
        return 5

def diversify_hints_intelligently():
    """
    Reads the self-check report, identifies puzzles with errors, and attempts to fix them
    by replacing hints from over-represented dimensions with hints from under-represented
    dimensions, while avoiding new adjacency and length errors.
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
    
    max_hint_len = get_max_hint_len(repo_root)
    print(f"Using MAX_HINT_LEN: {max_hint_len}")

    hint_to_dimension = get_dimension_pools_from_script(script_path)
    if not hint_to_dimension:
        print("Error: Could not build hint-to-dimension mapping.", file=sys.stderr)
        return 1

    # Filter out hints that are too long
    all_known_hints = [h for h in hint_to_dimension.keys() if len(h) <= max_hint_len]
    puzzles_map = {p['answer']: p for p in puzzles}

    # 2. Identify all puzzles that need fixing
    answers_to_fix = set()
    for hit in report.get("adjacent_same_dimension_hits", []):
        answers_to_fix.add(hit['answer'])
    for hit in report.get("per_dimension_cap_hits", []):
        answers_to_fix.add(hit['answer'])
    
    # Also add puzzles with hints that are too long
    for hit in report.get("max_char_exceeded_hits", []):
        answers_to_fix.add(hit['answer'])

    if not answers_to_fix:
        print("No adjacency or cap errors found to fix.")
        return 0

    print(f"Found {len(answers_to_fix)} puzzles with errors. Starting intelligent diversification...")
    fix_count = 0
    MAX_ITERATIONS_PER_PUZZLE = 5 # Add a loop to try fixing a puzzle multiple times

    # 3. Iterate and fix each problematic puzzle
    for answer in answers_to_fix:
        if answer not in puzzles_map:
            continue

        puzzle = puzzles_map[answer]
        original_hints = puzzle.get('hints', [])
        if len(original_hints) < 7:
            continue

        puzzle_fixed_in_iteration = False
        for i in range(MAX_ITERATIONS_PER_PUZZLE):
            hints = puzzle['hints'][:7] # Use the latest version of hints for the puzzle
            
            current_dims = get_puzzle_hint_dimensions(hints, hint_to_dimension)
            dim_counts = Counter(d for d in current_dims if d != 'unknown')
            if not dim_counts:
                break # Cannot analyze this puzzle

            # Check for long hints first
            long_hint_indices = [i for i, h in enumerate(hints) if len(h) > max_hint_len]
            if long_hint_indices:
                idx_to_replace = random.choice(long_hint_indices)
                offending_dim = "length_violation"
            else: # If no length issues, check for dimension issues
                most_common_dim, count = dim_counts.most_common(1)[0]
                if count <= 1:
                    # This puzzle seems fine now, maybe fixed by a previous iteration
                    break 
                
                indices_to_replace = [i for i, dim in enumerate(current_dims) if dim == most_common_dim]
                if not indices_to_replace:
                    break
                idx_to_replace = random.choice(indices_to_replace)
                offending_dim = most_common_dim

            # --- Find a replacement ---
            used_dimensions = set(d for d in current_dims if d != 'unknown') # Exclude unknown from used dimensions
            candidate_hints = [
                h for h in all_known_hints 
                if hint_to_dimension.get(h) not in used_dimensions and h not in hints
            ]
            if not candidate_hints:
                candidate_hints = [h for h in all_known_hints if h not in hints and hint_to_dimension.get(h) != 'unknown']

            random.shuffle(candidate_hints)
            
            replacement_found = False
            for replacement_hint in candidate_hints:
                replacement_dim = hint_to_dimension[replacement_hint]
                
                if idx_to_replace > 0 and current_dims[idx_to_replace - 1] == replacement_dim:
                    continue
                if idx_to_replace < (len(hints) - 1) and current_dims[idx_to_replace + 1] == replacement_dim:
                    continue

                hints[idx_to_replace] = replacement_hint
                puzzle['hints'][:7] = hints
                
                if not puzzle_fixed_in_iteration:
                    fix_count += 1
                    puzzle_fixed_in_iteration = True

                print(f"  - Fix attempt {i+1} for '{answer}': Replaced hint in dim '{offending_dim}' with '{replacement_hint}' (dim: '{replacement_dim}')")
                replacement_found = True
                break 
            
            if not replacement_found:
                # If we couldn't find a replacement, stop trying for this puzzle
                break

    # 4. Save the changes
    if fix_count > 0:
        print(f"\nDiversified hints for {fix_count} puzzles.")
        with puzzles_path.open('w', encoding='utf-8') as f:
            json.dump(puzzles, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated {puzzles_path}")
    else:
        print("No puzzles were modified (could not find valid non-adjacent replacements).")
        
    return 0

if __name__ == "__main__":
    sys.exit(diversify_hints_intelligently())
