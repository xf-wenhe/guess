#!/usr/bin/env python3
"""
使用新训练数据微调 bge-m3 模型
102 对训练数据，基于 puzzles.json 生成
"""
import pandas as pd
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
import os
import shutil

def main():
    # 配置
    train_file = 'data/similarity_train_v4.csv'
    output_dir = 'models/bge-m3-finetuned-v4'
    
    # 读取训练数据
    train_df = pd.read_csv(train_file)
    print(f"✓ 加载训练数据: {len(train_df)} 对")
    print(f"  相似度范围: {train_df['score'].min():.2f} - {train_df['score'].max():.2f}")
    
    # 加载原始模型
    print("\n正在加载 BAAI/bge-m3 (首次下载约 2.2GB)...")
    # 使用 CPU 避免 MPS 显存不足
    model = SentenceTransformer('BAAI/bge-m3', device='cpu')
    
    # 准备训练数据
    train_examples = []
    for _, row in train_df.iterrows():
        example = InputExample(
            texts=[row['text_a'], row['text_b']], 
            label=float(row['score'])
        )
        train_examples.append(example)
    
    # 配置训练
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=8)
    train_loss = losses.CosineSimilarityLoss(model)
    
    # 微调
    print("\n开始微调 (10 epochs)...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=10,
        warmup_steps=50,
        show_progress_bar=True
    )
    
    # 保存模型
    print(f"\n保存模型到: {output_dir}")
    model.save(output_dir)
    
    print("✓ 微调完成!")
    
    # 清理缓存中的模型文件（释放空间）
    print("\n清理缓存...")
    cache_dir = os.path.expanduser('~/.cache/huggingface/hub')
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir)
            print("✓ 缓存已清理")
        except:
            pass

if __name__ == '__main__':
    main()
