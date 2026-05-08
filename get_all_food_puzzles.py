#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取所有美食谜题
"""
import json


def main():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        puzzles = json.load(f)
    
    food_puzzles = []
    for puzzle in puzzles:
        if puzzle['category'] == '美食':
            food_puzzles.append(puzzle)
            print(f"- {puzzle['answer']}")
            print(f"  Hints: {puzzle['hints']}")
            print()
    print(f"Total: {len(food_puzzles)}")


if __name__ == "__main__":
    main()
