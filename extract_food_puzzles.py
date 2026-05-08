#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取美食分类的谜题
"""
import json


def main():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        puzzles = json.load(f)
    
    food_puzzles = [p for p in puzzles if p['category'] == '美食']
    
    print(f"找到 {len(food_puzzles)} 个美食分类谜题")
    for p in food_puzzles:
        print(f"- {p['answer']}")


if __name__ == "__main__":
    main()
