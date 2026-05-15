
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from collections import defaultdict

def load_puzzles():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def load_calibration():
    with open('data/semantic_calibration_v27_semreal_anchor.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_calibrated_score(raw_score, calibration_data):
    x_pred = calibration_data['x_pred']
    y_calibrated = calibration_data['y_calibrated']
    return np.interp(raw_score * 100, x_pred, y_calibrated)

def analyze_monotonicity():
    print("Loading model onto CPU for deterministic results...")
    model = SentenceTransformer('models/bge-m3-finetuned-v27-semreal-anchor', device='cpu')
    print("Model loaded on CPU.")
    
    puzzles = load_puzzles()
    calibration_data = load_calibration()
    
    category_issues = defaultdict(list)
    
    print(f"Analyzing {len(puzzles)} puzzles...")
    
    for puzzle in puzzles:
        answer = puzzle['answer']
        hints = puzzle['hints']
        category = puzzle.get('category', '未分类')
        
        if len(hints) < 2:
            continue
            
        texts_to_embed = [answer] + hints
        embeddings = model.encode(texts_to_embed, normalize_embeddings=True)
        answer_embedding = embeddings[0]
        hint_embeddings = embeddings[1:]
        
        scores = [np.dot(answer_embedding, hint_embedding) for hint_embedding in hint_embeddings]
        calibrated_scores = [get_calibrated_score(score, calibration_data) for score in scores]
        
        is_monotonic = all(calibrated_scores[i] <= calibrated_scores[i+1] for i in range(len(calibrated_scores)-1))
        
        if not is_monotonic:
            category_issues[category].append({
                'answer': answer,
                'scores': [round(s, 1) for s in calibrated_scores]
            })
            
    print("\n--- Monotonicity Analysis Complete ---")
    
    sorted_categories = sorted(category_issues.items(), key=lambda item: len(item[1]), reverse=True)
    
    for category, issues in sorted_categories:
        print(f"Category '{category}': {len(issues)} non-monotonic puzzles")
        # for issue in issues[:3]: # Print first 3 examples
        #     print(f"  - {issue['answer']}: {issue['scores']}")

if __name__ == "__main__":
    analyze_monotonicity()
