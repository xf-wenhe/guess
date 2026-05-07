import csv
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

DATA_PATH = Path("/Users/fengye/work/flutter/guess/data/similarity_train.csv")
OUTPUT_DIR = Path("/Users/fengye/work/flutter/guess/models/bge-m3-finetuned")
BASE_MODEL = "BAAI/bge-m3"
BASE_DIR = Path("/Users/fengye/work/flutter/guess/tmp/finetune_base")


def load_examples(path: Path):
    examples = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text_a = row["text_a"].strip()
            text_b = row["text_b"].strip()
            score = float(row["score"])
            examples.append(InputExample(texts=[text_a, text_b], label=score))
    return examples


def main():
    examples = load_examples(DATA_PATH)
    if BASE_DIR.exists():
        shutil.rmtree(BASE_DIR)
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=BASE_MODEL,
        local_dir=str(BASE_DIR),
        local_dir_use_symlinks=False,
        resume_download=True,
    )

    model = SentenceTransformer(str(BASE_DIR))

    shutil.rmtree(BASE_DIR, ignore_errors=True)

    train_dataloader = DataLoader(examples, shuffle=True, batch_size=8)
    train_loss = losses.CosineSimilarityLoss(model=model)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=10,
        warmup_steps=0,
        output_path=str(OUTPUT_DIR),
        show_progress_bar=True,
    )

    print(f"Finetuned model saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
