#!/bin/bash

echo ""
echo "======================================================================"
echo "v6 模型测试结果 (基于人工标注锚点训练)"
echo "======================================================================"

# Function to compute cosine similarity
compute_similarity() {
    word1="$1"
    word2="$2"
    expected="$3"
    
    # Get embeddings
    emb1=$(curl -s -X POST http://127.0.0.1:8000/embed -H "Content-Type: application/json" -d "{\"text\": \"$word1\"}" | python3 -c "import sys, json; print(json.load(sys.stdin)['embedding'])")
    sleep 0.5
    emb2=$(curl -s -X POST http://127.0.0.1:8000/embed -H "Content-Type: application/json" -d "{\"text\": \"$word2\"}" | python3 -c "import sys, json; print(json.load(sys.stdin)['embedding'])")
    
    # Compute similarity
    similarity=$(python3 -c "
import numpy as np
emb1 = np.array($emb1)
emb2 = np.array($emb2)
sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
print(f'{sim:.4f}')
")
    
    diff=$(python3 -c "print(f'{abs($similarity - $expected):.4f}')")
    status=$(python3 -c "print('✓' if abs($similarity - $expected) < 0.15 else '✗')")
    
    printf "%-24s %12s %12.2f %10s %s\n" "$word1 / $word2" "$similarity" "$expected" "$diff" "$status"
}

printf "%-24s %12s %12s %10s\n" "词对" "实际相似度" "期望相似度" "差异"
echo "----------------------------------------------------------------------"

compute_similarity "猫咪" "猫" 0.90
compute_similarity "诸葛亮" "孔明" 0.90
compute_similarity "啊哈哈" "刘备" 0.05
compute_similarity "火影" "海贼王" 0.80
compute_similarity "陆游" "月份" 0.10
compute_similarity "演员" "阿萨德" 0.05

echo "======================================================================"
echo ""
echo "说明:"
echo "  ✓ = 差异 < 0.15 (符合预期)"
echo "  ✗ = 差异 ≥ 0.15 (需要调整)"
echo ""
