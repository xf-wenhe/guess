#!/usr/bin/env python3
import requests
import numpy as np

def compute_cosine_similarity(emb1, emb2):
    return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

def get_embedding(text):
    resp = requests.post("http://127.0.0.1:8000/embed", json={"text": text}, timeout=30)
    if resp.status_code != 200:
        print(f"[ERROR] Status: {resp.status_code}, Text: {resp.text[:200]}")
        raise Exception(f"HTTP {resp.status_code}")
    return np.array(resp.json()["embedding"])

test_pairs = [
    ("猫咪", "猫", 0.90),
    ("诸葛亮", "孔明", 0.90),
    ("啊哈哈", "刘备", 0.05),
    ("火影", "海贼王", 0.80),
    ("陆游", "月份", 0.10),
    ("演员", "阿萨德", 0.05),
]

print("\n" + "=" * 70)
print("v6 模型测试结果 (基于人工标注锚点训练)")
print("=" * 70)
print(f"{'词对':<24} {'实际相似度':>12} {'期望相似度':>12} {'差异':>10}")
print("-" * 70)

for word1, word2, expected in test_pairs:
    emb1 = get_embedding(word1)
    emb2 = get_embedding(word2)
    
    similarity = compute_cosine_similarity(emb1, emb2)
    diff = abs(similarity - expected)
    
    pair = f"{word1} / {word2}"
    status = "✓" if diff < 0.15 else "✗"
    print(f"{pair:<24} {similarity:>12.4f} {expected:>12.2f} {diff:>10.4f} {status}")

print("=" * 70)
print("\n说明:")
print("  ✓ = 差异 < 0.15 (符合预期)")
print("  ✗ = 差异 ≥ 0.15 (需要调整)")
print()
