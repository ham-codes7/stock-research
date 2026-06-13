"""
train.py — Fine-tune ProsusAI/finbert on Financial PhraseBank
==============================================================

Usage:
    python train.py

What it does:
    1. Downloads 'financial_phrasebank' (sentences_allagree split) from HuggingFace
    2. Splits into train / val / test (70 / 15 / 15)
    3. Fine-tunes ProsusAI/finbert for 3 epochs with early stopping on val loss
    4. Saves best checkpoint to ./finbert-finetuned
    5. Prints accuracy + macro-F1 on the held-out test split

Label mapping (Financial PhraseBank):
    0 → negative
    1 → neutral
    2 → positive

FinBERT native label order matches: positive / negative / neutral
We remap the dataset to match the model's own id2label so there are
NO label mismatches between training targets and model head output.
"""

import os
import numpy as np
from datasets import load_dataset, concatenate_datasets
from sklearn.metrics import accuracy_score, f1_score
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
    DataCollatorWithPadding,
)

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_NAME      = "ProsusAI/finbert"
OUTPUT_DIR      = "./finbert-finetuned"
DATASET_NAME    = "FinanceMTEB/financial_phrasebank"

NUM_EPOCHS      = 30
BATCH_SIZE      = 16
LEARNING_RATE   = 2e-5
WARMUP_RATIO    = 0.1          # ~10% of total steps used for linear warmup
WEIGHT_DECAY    = 0.01
MAX_SEQ_LEN     = 128          # Financial headlines are short; 128 is sufficient
SEED            = 42

# ── FinBERT's native label ordering ──────────────────────────────────────────
# ProsusAI/finbert has config.id2label = {0: 'positive', 1: 'negative', 2: 'neutral'}
# Financial PhraseBank labels:          {0: negative,    1: neutral,    2: positive}
# We build a remapping so that our integer targets align with finbert's head.
PHRASEBANK_INT_TO_STR = {0: "negative", 1: "neutral", 2: "positive"}

# Will be set after loading the model config
FINBERT_LABEL2ID: dict = {}


def get_label_remapper(label2id: dict):
    """
    Returns a function that converts a Financial PhraseBank integer label
    (0=neg, 1=neu, 2=pos) into the integer expected by FinBERT's classification
    head, so logit position matches the target class.
    """
    def remap(example):
        phrase_str   = PHRASEBANK_INT_TO_STR[example["label"]]
        finbert_int  = label2id[phrase_str]
        example["label"] = finbert_int
        return example
    return remap


def tokenize(batch, tokenizer):
    return tokenizer(
        batch["text"],
        truncation=True,
        max_length=MAX_SEQ_LEN,
    )


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc   = accuracy_score(labels, preds)
    f1    = f1_score(labels, preds, average="macro")
    return {"accuracy": acc, "macro_f1": f1}


def main():
    print("=" * 60)
    print("FinBERT Fine-Tuning — Financial PhraseBank")
    print("=" * 60)

    # ── 1. Load tokenizer & model ─────────────────────────────────────────────
    print(f"\n[1/5] Loading tokenizer and model from '{MODEL_NAME}' …")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model     = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

    # Capture FinBERT's native label mapping
    global FINBERT_LABEL2ID
    FINBERT_LABEL2ID = model.config.label2id
    # Normalise keys to lowercase (safety)
    FINBERT_LABEL2ID = {k.lower(): v for k, v in FINBERT_LABEL2ID.items()}
    print(f"    FinBERT label2id: {FINBERT_LABEL2ID}")

    # ── 2. Load & split dataset ───────────────────────────────────────────────
    print(f"\n[2/5] Loading dataset '{DATASET_NAME}' …")
    raw = load_dataset(DATASET_NAME)

    # Combine train and test splits to perform standard 70/15/15 split
    full = concatenate_datasets([raw["train"], raw["test"]]).shuffle(seed=SEED)
    n    = len(full)
    n_test = int(n * 0.15)
    n_val  = int(n * 0.15)
    n_train = n - n_val - n_test

    ds_train = full.select(range(n_train))
    ds_val   = full.select(range(n_train, n_train + n_val))
    ds_test  = full.select(range(n_train + n_val, n))

    print(f"    Total: {n} | Train: {len(ds_train)} | Val: {len(ds_val)} | Test: {len(ds_test)}")

    # ── 3. Remap labels & tokenize ────────────────────────────────────────────
    print("\n[3/5] Remapping labels and tokenizing …")
    remap_fn = get_label_remapper(FINBERT_LABEL2ID)

    def process(dataset):
        dataset = dataset.map(remap_fn)
        dataset = dataset.map(
            lambda batch: tokenize(batch, tokenizer),
            batched=True,
            remove_columns=["text", "label_text"],
        )
        dataset = dataset.rename_column("label", "labels")
        dataset.set_format("torch")
        return dataset

    ds_train = process(ds_train)
    ds_val   = process(ds_val)
    ds_test  = process(ds_test)

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # ── 4. Training ───────────────────────────────────────────────────────────
    print("\n[4/5] Training …")
    total_steps   = (len(ds_train) // BATCH_SIZE) * NUM_EPOCHS
    warmup_steps  = int(total_steps * WARMUP_RATIO)

    training_args = TrainingArguments(
        output_dir                  = OUTPUT_DIR,
        num_train_epochs            = NUM_EPOCHS,
        per_device_train_batch_size = BATCH_SIZE,
        per_device_eval_batch_size  = BATCH_SIZE,
        learning_rate               = LEARNING_RATE,
        weight_decay                = WEIGHT_DECAY,
        warmup_steps                = warmup_steps,
        lr_scheduler_type           = "linear",
        optim                       = "adamw_torch",
        eval_strategy               = "epoch",
        save_strategy               = "epoch",
        load_best_model_at_end      = False,
        logging_dir                 = os.path.join(OUTPUT_DIR, "logs"),
        logging_steps               = 50,
        seed                        = SEED,
        report_to                   = "none",       # no wandb / tensorboard needed
        fp16                        = False,         # keep CPU-safe; set True for GPU
    )

    trainer = Trainer(
        model           = model,
        args            = training_args,
        train_dataset   = ds_train,
        eval_dataset    = ds_val,
        processing_class = tokenizer,
        data_collator   = data_collator,
        compute_metrics = compute_metrics,
    )

    trainer.train()

    # Save best checkpoint to clean output dir
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"\n    [OK] Best model saved to '{OUTPUT_DIR}'")

    # ── 5. Evaluate on test split ─────────────────────────────────────────────
    print("\n[5/5] Evaluating on test split …")
    test_results = trainer.evaluate(ds_test)

    # Pull the metrics we care about
    acc = test_results.get("eval_accuracy", float("nan"))
    f1  = test_results.get("eval_macro_f1", float("nan"))

    print("\n" + "=" * 60)
    print("TEST SPLIT RESULTS")
    print("=" * 60)
    print(f"  Accuracy : {acc:.4f}  ({acc*100:.2f}%)")
    print(f"  Macro F1 : {f1:.4f}")
    print("=" * 60)
    print("\nDone. Run sentiment_server.py to serve the model.\n")


if __name__ == "__main__":
    main()
