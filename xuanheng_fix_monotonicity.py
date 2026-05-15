
import json
import numpy as np
from sentence_transformers import SentenceTransformer
import argparse
import time
from itertools import combinations

# --- Configuration ---
PUZZLES_FILE = 'assets/puzzles.json'
MODEL_PATH = 'models/bge-m3-finetuned-v27-semreal-anchor'
CALIB_PATH = 'data/semantic_calibration_v27_semreal_anchor.json'
TARGET_CATEGORY = '神话'
HINT_CANDIDATE_POOL = ['女娲', '盘古', '夸父', '精卫', '后羿', '嫦娥', '玉皇大帝', '王母娘娘', '孙悟空', '猪八戒', '沙和尚', '唐僧', '白骨精', '牛魔王', '铁扇公主', '红孩儿', '二郎神', '哪吒', '雷公', '电母', '风伯', '雨师', '龙王', '阎王']

# --- Global Objects (to avoid reloading) ---
model = None
calib_data = None
x_pred, y_calibrated = None, None

def load_globals():
    """Load model and calibration data into global variables."""
    global model, calib_data, x_pred, y_calibrated
    if model is None:
        print("Loading model onto CPU for deterministic results...")
        # Force model to use CPU by passing device='cpu'
        model = SentenceTransformer(MODEL_PATH, device='cpu')
        print("Model loaded on CPU.")

    if calib_data is None:
        print("Loading calibration data...")
        with open(CALIB_PATH, 'r', encoding='utf-8') as f:
            calib_data = json.load(f)
        x_pred, y_calibrated = calib_data['x_pred'], calib_data['y_calibrated']

# --- Helper Functions ---
def cos_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_calibrated_percent(raw_cosine):
    raw_percent = raw_cosine * 100
    return np.interp(raw_percent, x_pred, y_calibrated)

def get_scores_for_hints(answer, hints):
    """Calculate calibrated scores for a list of hints against an answer."""
    answer_embedding = model.encode(answer, normalize_embeddings=True)
    hint_embeddings = model.encode(hints, normalize_embeddings=True)
    
    scores = []
    for hint_embedding in hint_embeddings:
        similarity = cos_sim(answer_embedding, hint_embedding)
        calibrated_score = get_calibrated_percent(similarity)
        scores.append(calibrated_score)
    return scores

def validate_category(category):
    """Find and report all non-monotonic puzzles in a category."""
    print(f"\\n--- Running Validation for category: {category} ---")
    with open(PUZZLES_FILE, 'r', encoding='utf-8') as f:
        puzzles = json.load(f)

    category_puzzles = [p for p in puzzles if p.get('category') == category]
    non_monotonic_puzzles = []

    for puzzle in category_puzzles:
        answer = puzzle.get('answer')
        hints = puzzle.get('hints')
        
        if not answer or not hints or len(hints) != 7:
            continue

        scores = get_scores_for_hints(answer, hints)
        is_monotonic = all(scores[i] <= scores[i+1] for i in range(len(scores)-1))
        
        if not is_monotonic:
            non_monotonic_puzzles.append({
                'answer': answer, 
                'scores': [round(s, 1) for s in scores]
            })

    print(f"Found {len(non_monotonic_puzzles)} non-monotonic puzzles in category '{category}'.")
    if non_monotonic_puzzles:
        print('They are:')
        for issue in non_monotonic_puzzles:
            print(f"  - {issue['answer']}: {issue['scores']}")
    print('--- Validation Complete ---')

def fix_puzzle(target_answer):
    """Find the best monotonic hint ladder and patch the JSON file."""
    print(f'\\n--- Running Fix for answer: {target_answer} ---')
    
    # 1. Score all candidates
    print(f'Scoring {len(HINT_CANDIDATE_POOL)} candidates...')
    scored_candidates = []
    answer_embedding = model.encode(target_answer, normalize_embeddings=True)
    for hint in HINT_CANDIDATE_POOL:
        if hint == target_answer: continue
        hint_embedding = model.encode(hint, normalize_embeddings=True)
        similarity = cos_sim(answer_embedding, hint_embedding)
        calibrated_score = get_calibrated_percent(similarity)
        scored_candidates.append({'hint': hint, 'score': calibrated_score})

    scored_candidates.sort(key=lambda x: x['score'])

    # 2. Find the best monotonic 7-hint ladder
    best_ladder = None
    if len(scored_candidates) >= 7:
        # Since candidates are sorted, any 7-item slice is a monotonic ladder.
        # We can iterate through all combinations to find the one with the best properties if needed,
        # but for now, just taking the first valid one is enough to test the process.
        # A simple sliding window is a good enough heuristic for now.
        best_ladder = scored_candidates[:7] # Simplest choice
        
        # A better approach: find the one with the best score spread
        best_spread = -1
        for i in range(len(scored_candidates) - 6):
            ladder = scored_candidates[i:i+7]
            spread = ladder[-1]['score'] - ladder[0]['score']
            if spread > best_spread:
                best_spread = spread
                best_ladder = ladder

    if not best_ladder:
        print(f'FATAL: Could not find any monotonic 7-hint ladder for {target_answer}.')
        return

    new_hints = [item['hint'] for item in best_ladder]
    new_scores = [round(item['score'], 1) for item in best_ladder]

    print(f"Found best monotonic ladder for '{target_answer}':")
    print(f'  Hints: {new_hints}')
    print(f'  Scores: {new_scores}')

    # 3. Patch the puzzles.json file
    with open(PUZZLES_FILE, 'r', encoding='utf-8') as f:
        puzzles = json.load(f)

    found_puzzle = False
    for puzzle in puzzles:
        if puzzle.get('answer') == target_answer:
            print(f'Patching puzzle for {target_answer}.')
            puzzle['hints'] = new_hints
            found_puzzle = True
            break

    if found_puzzle:
        with open(PUZZLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(puzzles, f, ensure_ascii=False, indent=2)
        print(f'Successfully patched {target_answer} in {PUZZLES_FILE}.')
    else:
        print(f"Error: Puzzle with answer '{target_answer}' not found.")
    print('--- Fix Complete ---')


def main():
    parser = argparse.ArgumentParser(description='Validate and fix puzzle hint monotonicity.')
    parser.add_argument('--validate', action='store_true', help='Validate the specified category for monotonicity.')
    parser.add_argument('--fix', type=str, metavar='ANSWER', help='Find and apply a monotonic hint ladder for the given answer.')
    parser.add_argument('--debug_run', type=str, metavar='ANSWER', help='Run scoring 5 times for a fixed answer/hint set to check for non-determinism.')
    
    args = parser.parse_args()

    load_globals()

    if args.validate:
        validate_category(TARGET_CATEGORY)
    elif args.fix:
        fix_puzzle(args.fix)
    elif args.debug_run:
        debug_non_determinism(args.debug_run)
    else:
        print('No action specified. Use --validate, --fix <ANSWER>, or --debug_run <ANSWER>.')

def debug_non_determinism(answer):
    """Run the same scoring 5 times to check for inconsistent output."""
    print(f"--- Debugging Non-Determinism for: {answer} ---")
    # Using the hints that were just applied to '粥品'
    fixed_hints = ['烤鸭', '肉夹馍', '麻辣烫', '螺蛳粉', '馒头', '沙拉', '寿司']
    print(f"Using fixed hints: {fixed_hints}")

    for i in range(5):
        print(f"\\nRun {i+1}:")
        scores = get_scores_for_hints(answer, fixed_hints)
        print(f"  Scores: {[round(s, 1) for s in scores]}")
        time.sleep(1) # Small delay to see if it impacts state

    print("\\n--- Debug Complete ---")


if __name__ == '__main__':
    main()
