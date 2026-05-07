#!/usr/bin/env python3
"""直接加载v7模型并测试"""
import sys
sys.path.insert(0, '/Users/fengye/work/flutter/guess')

from sentence_transformers import SentenceTransformer
import numpy as np

print("\n加载v7模型...")
model = SentenceTransformer("models/bge-m3-finetuned-v7", device='cpu')

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

test_pairs = [
    ("猫咪", "猫", 0.90),
    ("诸葛亮", "孔明", 0.90),
    ("啊哈哈", "刘备", 0.05),
    ("火影", "海贼王", 0.80),
    ("陆游", "月份", 0.10),
    ("演员", "阿萨德", 0.05),
]

print("=" * 70)
print("v7 模型直接测试 (使用本地模型，无网络调用)")
print("=" * 70)
print(f"{'词对':<24} {'预测相似度':>12} {'目标相似度':>12} {'误差':>10}")
print("-" * 70)

for word1, word2, expected in test_pairs:
    emb1 = model.encode(word1, normalize_embeddings=True)
    emb2 = model.encode(word2, normalize_embeddings=True)
    
    similarity = cosine_similarity(emb1, emb2)
    diff = abs(similarity - expected)
    
    pair = f"{word1} / {word2}"
    status = "✓" if diff < 0.15 else "✗"
    print(f"{pair:<24} {similarity:>12.4f} {expected:>12.2f} {diff:>10.4f} {status}")

print("=" * 70)
