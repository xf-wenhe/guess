#!/usr/bin/env python3
import os
import pandas as pd
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

# 离线模式，避免下载
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

train_file = 'data/similarity_train_v6.csv'
output_dir = 'models/bge-m3-finetuned-v6'
base_model_dir = 'models/bge-m3-finetuned-v4'  # 使用本地模型作为起点

train_df = pd.read_csv(train_file)
print(f"训练数据: {len(train_df)} 对")

print(f"加载本地模型: {base_model_dir}")
model = SentenceTransformer(base_model_dir, device='cpu')

train_examples = [
    InputExample(texts=[row['text_a'], row['text_b']], label=float(row['score']))
    for _, row in train_df.iterrows()
]

train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=8)
train_loss = losses.CosineSimilarityLoss(model)

print("开始微调 (epochs=5)...")
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=5,
    warmup_steps=50,
    show_progress_bar=True
)

print(f"保存模型到: {output_dir}")
model.save(output_dir)
print("✓ 微调完成")
