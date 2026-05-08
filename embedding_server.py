import os
from contextlib import asynccontextmanager
from threading import Lock
from threading import Thread
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download
import uvicorn

# HuggingFace repo to download when fine-tuned model is absent.
# Override with EMBED_HF_REPO env var once the fine-tuned model is published.
# Fine-tuned model path (local):  models/bge-m3-finetuned-v27-semreal-anchor/
HF_REPO = os.getenv("EMBED_HF_REPO", "BAAI/bge-m3")
LOCAL_DIR = os.getenv("EMBED_MODEL_DIR") or "models/bge-m3-finetuned-v27-semreal-anchor"
PRELOAD_ON_START = os.getenv("EMBED_PRELOAD_ON_START", "0") == "1"
WARMUP_ON_HEALTH = os.getenv("EMBED_WARMUP_ON_HEALTH", "1") == "1"
WARMUP_TEXT = os.getenv("EMBED_WARMUP_TEXT", "语义预热")

_model: Optional[SentenceTransformer] = None
_model_lock = Lock()
_warmup_started = False
_warmup_done = False
_warmup_lock = Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if PRELOAD_ON_START:
        model = get_model()
        model.encode(WARMUP_TEXT, normalize_embeddings=True)
        global _warmup_started, _warmup_done
        with _warmup_lock:
            _warmup_started = True
            _warmup_done = True
    yield


app = FastAPI(lifespan=lifespan)


def load_model() -> SentenceTransformer:
    def load_sentence_transformer(path: str) -> SentenceTransformer:
        try:
            return SentenceTransformer(
                path,
                tokenizer_kwargs={"fix_mistral_regex": True},
                local_files_only=True,
            )
        except TypeError:
            return SentenceTransformer(path, local_files_only=True)

    if os.path.isdir(LOCAL_DIR) and os.path.exists(os.path.join(LOCAL_DIR, "config.json")):
        return load_sentence_transformer(LOCAL_DIR)

    os.makedirs(LOCAL_DIR, exist_ok=True)
    print(f"[embedding_server] Model not found at '{LOCAL_DIR}'. Downloading '{HF_REPO}' from HuggingFace...")
    snapshot_download(
        repo_id=HF_REPO,
        local_dir=LOCAL_DIR,
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    return load_sentence_transformer(LOCAL_DIR)


def get_model() -> SentenceTransformer:
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            _model = load_model()
    return _model


def _start_warmup_once() -> None:
    global _warmup_started, _warmup_done
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True

    def _warmup() -> None:
        global _warmup_done
        try:
            model = get_model()
            model.encode(WARMUP_TEXT, normalize_embeddings=True)
        finally:
            with _warmup_lock:
                _warmup_done = True

    Thread(target=_warmup, daemon=True).start()


def _ready_state() -> bool:
    if _warmup_done:
        return True
    if not WARMUP_ON_HEALTH and _model is not None:
        return True
    return False


class EmbedRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    if WARMUP_ON_HEALTH:
        _start_warmup_once()
    return {"status": "ok", "warmup_started": _warmup_started, "warmup_done": _warmup_done}


@app.get("/ready")
def ready():
    if WARMUP_ON_HEALTH:
        _start_warmup_once()
    ready_ok = _ready_state()
    return {
        "status": "ok" if ready_ok else "warming",
        "ready": ready_ok,
        "warmup_started": _warmup_started,
        "warmup_done": _warmup_done,
    }


@app.post("/embed")
def embed(req: EmbedRequest):
    embedding = get_model().encode(req.text, normalize_embeddings=True)
    return {"embedding": embedding.tolist()}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
