"""
eval_test.py — Evaluate the fine-tuned model on the test split.
"""

import numpy as np
from datasets import load_dataset, concatenate_datasets
from sklearn.metrics import accuracy_score, f1_score
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    Trainer,
    DataCollatorWithPadding,
    TrainingArguments,
)

MODEL_DIR     = "./finbert-finetuned"
DATASET_NAME  = "FinanceMTEB/financial_phrasebank"
SEED          = 42
MAX_SEQ_LEN   = 128

PHRASEBANK_INT_TO_STR = {0: "negative", 1: "neutral", 2: "positive"}


def main():
    print(f"Loading tokenizer and model from '{MODEL_DIR}' ...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model     = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)

    label2id = {k.lower(): v for k, v in model.config.label2id.items()}
    print(f"Model label2id: {label2id}")

    print(f"Loading dataset '{DATASET_NAME}' ...")
    raw = load_dataset(DATASET_NAME)

    full = concatenate_datasets([raw["train"], raw["test"]]).shuffle(seed=SEED)
    n    = len(full)
    n_test = int(n * 0.15)
    n_val  = int(n * 0.15)
    n_train = n - n_val - n_test

    # Select the exact same test split
    ds_test = full.select(range(n_train + n_val, n))
    print(f"Test split size: {len(ds_test)}")

    def remap(example):
        phrase_str   = PHRASEBANK_INT_TO_STR[example["label"]]
        example["label"] = label2id[phrase_str]
        return example

    print("Preprocessing and tokenizing ...")
    ds_test = ds_test.map(remap)
    ds_test = ds_test.map(
        lambda batch: tokenizer(batch["text"], truncation=True, max_length=MAX_SEQ_LEN),
        batched=True,
        remove_columns=["text", "label_text"],
    )
    ds_test = ds_test.rename_column("label", "labels")
    ds_test.set_format("torch")

    # Define minimal TrainingArguments for evaluation
    training_args = TrainingArguments(
        output_dir="./eval_temp",
        per_device_eval_batch_size=16,
        report_to="none",
    )

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc   = accuracy_score(labels, preds)
        f1    = f1_score(labels, preds, average="macro")
        return {"accuracy": acc, "macro_f1": f1}

    trainer = Trainer(
        model           = model,
        args            = training_args,
        eval_dataset    = ds_test,
        processing_class = tokenizer,
        data_collator   = DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics = compute_metrics,
    )

    print("Evaluating ...")
    results = trainer.evaluate()

    acc = results.get("eval_accuracy", float("nan"))
    f1  = results.get("eval_macro_f1", float("nan"))

    print("\n" + "=" * 60)
    print("HELD-OUT TEST SPLIT RESULTS")
    print("=" * 60)
    print(f"  Accuracy : {acc:.4f}  ({acc*100:.2f}%)")
    print(f"  Macro F1 : {f1:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
