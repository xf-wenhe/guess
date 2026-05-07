#!/usr/bin/env python3
import os
import sys

os.chdir('/Users/fengye/work/flutter/guess')
sys.path.insert(0, '/Users/fengye/work/flutter/guess')

import pandas as pd
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

# 加载数据
train_df = pd.read_csv('data/similarity_train_v4.csv')
print(f'训练数据: {len(train_df)} 对')

# 加载原始模型
print('加载 BAAI/bge-m3...')
model = SentenceTransformer('BAAI/bge-m3', device='cpu')

# 准备数据
train_examples = [
    InputExample(texts=[row['text_a'], row['text_b']], label=float(row['score']))
    for _, row in train_df.iterrows()
]

# 微调
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=8)
train_loss = losses.CosineSimilarityLoss(model)

print('微调中...')
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=10,
    warmup_steps=50,
    show_progress_bar=False
)

# 保存
output_dir = 'models/bge-m3-finetuned-v4'
print(f'保存到: {output_dir}')
model.save(output_dir)
print('✓ 完成')
