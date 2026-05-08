#!/usr/bin/env python3
"""
Fine-tune BGE-M3 model with human-curated semantic similarity anchors.
This version uses human judgement instead of automated heuristics.
"""

import os
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

import csv
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
import pandas as pd

# Human-curated training data with real semantic relationships
HUMAN_ANCHORS = [
    # Synonyms/near-synonyms (high similarity ~0.90)
    ("猫咪", "猫", 0.90),
    ("猫", "猫咪", 0.90),
    ("诸葛亮", "孔明", 0.90),
    ("孔明", "诸葛亮", 0.90),
    
    # Dissimilar pairs (low similarity ~0.05)
    ("啊哈哈", "刘备", 0.05),
    ("刘备", "啊哈哈", 0.05),
    ("演员", "阿萨德", 0.05),
    ("阿萨德", "演员", 0.05),
    ("陆游", "月份", 0.10),
    ("月份", "陆游", 0.10),
    
    # Related but not synonymous (~0.80)
    ("火影", "海贼王", 0.80),
    ("海贼王", "火影", 0.80),
]

print("=" * 70)
print("训练数据: 人工标注语义相似度")
print("=" * 70)
print(f"{'词对':<20} {'相似度':>10}")
print("-" * 70)

for word1, word2, score in HUMAN_ANCHORS:
    print(f"{word1} / {word2:<16} {score:>10.2f}")

print("-" * 70)
print(f"总共: {len(HUMAN_ANCHORS)} 对")
print()

# Load base model
print("加载基础模型: models/bge-m3-finetuned-v5")
model = SentenceTransformer("models/bge-m3-finetuned-v5", device='cpu')

# Prepare training examples
train_examples = [
    InputExample(texts=[word1, word2], label=score)
    for word1, word2, score in HUMAN_ANCHORS
]

train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=4)
train_loss = losses.CosineSimilarityLoss(model=model)

# Fine-tune with more aggressive parameters for smaller dataset
print("\n开始微调 (epochs=20, 使用所有12个锚点对)...")
print("=" * 70)

model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=20,
    warmup_steps=10,
    show_progress_bar=True,
    weight_decay=0.01,
    optimizer_params={'lr': 5e-5}
)

# Save the model using sentence_transformers API with error handling
output_path = "models/bge-m3-finetuned-v7"
print(f"\n保存模型到: {output_path}")

try:
    model.save(output_path)
except Exception as e:
    print(f"[WARNING] Save failed ({e}), trying alternative method...")
    import shutil
    import os
    base_path = "models/bge-m3-finetuned-v5"
    # Copy base model structure
    shutil.copytree(base_path, output_path, dirs_exist_ok=True)
    # Save just the transformer weights
    model[0].auto_model.save_pretrained(output_path, safe_serialization=True)
    print("  [OK] Model weights saved")

print("✓ 微调完成!")
print()

# Test on anchor pairs
print("=" * 70)
print("验证模型性能 (在训练数据上)")
print("=" * 70)

import numpy as np

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

print(f"{'词对':<20} {'预测相似度':>12} {'目标相似度':>12} {'误差':>10}")
print("-" * 70)

for word1, word2, target_score in HUMAN_ANCHORS[:12]:  # Show unique pairs
    emb1 = model.encode(word1, normalize_embeddings=True)
    emb2 = model.encode(word2, normalize_embeddings=True)
    
    predicted = cosine_similarity(emb1, emb2)
    error = abs(predicted - target_score)
    
    pair = f"{word1} / {word2}"
    status = "✓" if error < 0.15 else "✗"
    print(f"{pair:<20} {predicted:>12.4f} {target_score:>12.2f} {error:>10.4f} {status}")

print("=" * 70)
