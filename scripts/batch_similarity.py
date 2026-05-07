from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download
from math import sqrt
from pathlib import Path

pairs = [
    ('诸葛亮','三国演义'),
    ('诸葛亮','孔明'),
    ('诸葛亮','司马懿'),
    ('诸葛亮','丞相'),
    ('诸葛亮','你好'),
    ('诸葛亮','猫咪'),
    ('猫','猫咪'),
    ('猫','狗'),
    ('啊哼','什么'),
    ('柯南','工藤新一'),
    ('柯南','福尔摩斯'),
    ('三心二意','粗心'),
]

models = [
    ("BAAI/bge-large-zh-v1.5", "models/bge-large-zh-v1.5"),
    ("BAAI/bge-m3", "models/bge-m3"),
    ("moka-ai/m3e-base", "models/m3e-base"),
    ("shibing624/text2vec-large-chinese", "models/text2vec-large-chinese"),
]


def cosine(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na = sqrt(sum(x*x for x in a))
    nb = sqrt(sum(y*y for y in b))
    return dot / (na * nb)


for model_id, local_dir in models:
    print(f"\n=== {model_id} ===")
    local_path = Path(local_dir)
    if not local_path.exists():
        local_path.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=model_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
    model = SentenceTransformer(local_dir)
    cache = {}
    for t1, t2 in pairs:
        if t1 not in cache:
            cache[t1] = model.encode(t1, normalize_embeddings=True)
        if t2 not in cache:
            cache[t2] = model.encode(t2, normalize_embeddings=True)
        sim = cosine(cache[t1], cache[t2])
        print(f"{t1}，{t2}: {sim:.6f}")
