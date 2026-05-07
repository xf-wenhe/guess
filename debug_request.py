#!/usr/bin/env python3
import requests

# Simple debug test
resp = requests.post("http://127.0.0.1:8000/embed", json={"text": "猫咪"}, timeout=30)
print(f"Status code: {resp.status_code}")
print(f"Response text (first 500 chars): {resp.text[:500]}")
print(f"Response headers: {resp.headers}")

if resp.status_code == 200:
    try:
        data = resp.json()
        print(f"JSON parsed successfully, embedding length: {len(data['embedding'])}")
    except Exception as e:
        print(f"JSON parse error: {e}")
else:
    print("Request failed")
