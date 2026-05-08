import os
import shutil
import sys
from math import sqrt
from pathlib import Path

from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

pairs = [
    ("诸葛亮", "三国演义"),
    ("诸葛亮", "孔明"),
    ("诸葛亮", "司马懿"),
    ("诸葛亮", "丞相"),
    ("诸葛亮", "你好"),
    ("诸葛亮", "猫咪"),
    ("猫", "猫咪"),
    ("猫", "狗"),
    ("啊哼", "什么"),
    ("柯南", "工藤新一"),
    ("柯南", "福尔摩斯"),
    ("三心二意", "粗心"),
]

if len(sys.argv) < 3:
    print("Usage: run_similarity_one.py <model_id> <short_name>")
    sys.exit(1)

model_id = sys.argv[1]
short_name = sys.argv[2]

base_dir = Path("/Users/fengye/work/flutter/guess/tmp/model_runs")
base_dir.mkdir(parents=True, exist_ok=True)
local_dir = base_dir / short_name

os.environ["HF_HOME"] = str(local_dir)
os.environ["HF_HUB_CACHE"] = str(local_dir)

if local_dir.exists():
    shutil.rmtree(local_dir)
local_dir.mkdir(parents=True, exist_ok=True)

snapshot_download(
    repo_id=model_id,
    local_dir=str(local_dir),
    local_dir_use_symlinks=False,
    resume_download=True,
)

model = SentenceTransformer(str(local_dir))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    return dot / (na * nb)


print(f"=== {model_id} ===")
cache = {}
for t1, t2 in pairs:
    if t1 not in cache:
        cache[t1] = model.encode(t1, normalize_embeddings=True)
    if t2 not in cache:
        cache[t2] = model.encode(t2, normalize_embeddings=True)
    sim = cosine(cache[t1], cache[t2])
    print(f"{t1}，{t2}: {sim:.6f}")

shutil.rmtree(local_dir, ignore_errors=True)
