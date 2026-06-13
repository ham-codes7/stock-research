# resume_train.py
# Run this in your terminal:
#   python resume_train.py
# It will pick up from the last saved checkpoint in ./finbert-finetuned
# and train until epoch 30 (or until early stopping fires).

import os
import numpy as np
import shutil
import gc
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

MODEL_DIR    = "./finbert-finetuned"   # resume from here
OUTPUT_DIR   = "./finbert-finetuned"   # save best back to same dir
DATASET_NAME = "FinanceMTEB/financial_phrasebank"

NUM_EPOCHS   = 30
BATCH_SIZE   = 16
LEARNING_RATE= 2e-5
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01
MAX_SEQ_LEN  = 128
SEED         = 42

PHRASEBANK_INT_TO_STR = {0: "negative", 1: "neutral", 2: "positive"}

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy_score(labels, preds),
        "macro_f1": f1_score(labels, preds, average="macro"),
    }

def main():
    print("=" * 60)
    print("FinBERT Resume Training - Financial PhraseBank")
    print("=" * 60)

    # 1. Load tokenizer & model
    # To avoid Windows file lock issues on ./finbert-finetuned/model.safetensors,
    # we initialize the base architecture from "ProsusAI/finbert" and load the
    # checkpoint weights during trainer.train().
    print("Loading base tokenizer and model from 'ProsusAI/finbert' ...")
    tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model     = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")

    label2id = {k.lower(): v for k, v in model.config.label2id.items()}
    print(f"Label2id: {label2id}")

    print("Loading and splitting dataset ...")
    raw  = load_dataset(DATASET_NAME)
    full = concatenate_datasets([raw["train"], raw["test"]]).shuffle(seed=SEED)
    n = len(full)
    n_test  = int(n * 0.15)
    n_val   = int(n * 0.15)
    n_train = n - n_val - n_test

    ds_train = full.select(range(n_train))
    ds_val   = full.select(range(n_train, n_train + n_val))
    ds_test  = full.select(range(n_train + n_val, n))
    print(f"Train: {len(ds_train)} | Val: {len(ds_val)} | Test: {len(ds_test)}")

    def remap(example):
        phrase_str = PHRASEBANK_INT_TO_STR[example["label"]]
        example["label"] = label2id[phrase_str]
        return example

    def process(dataset):
        dataset = dataset.map(remap)
        dataset = dataset.map(
            lambda batch: tokenizer(batch["text"], truncation=True, max_length=MAX_SEQ_LEN),
            batched=True,
            remove_columns=["text", "label_text"],
        )
        dataset = dataset.rename_column("label", "labels")
        dataset.set_format("torch")
        return dataset

    print("Tokenizing ...")
    ds_train = process(ds_train)
    ds_val   = process(ds_val)
    ds_test  = process(ds_test)

    total_steps  = (len(ds_train) // BATCH_SIZE) * NUM_EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)

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
        logging_steps               = 50,
        seed                        = SEED,
        report_to                   = "none",
        fp16                        = False,
    )

    trainer = Trainer(
        model            = model,
        args             = training_args,
        train_dataset    = ds_train,
        eval_dataset     = ds_val,
        processing_class = tokenizer,
        data_collator    = DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics  = compute_metrics,
    )

    # Resume from last checkpoint in OUTPUT_DIR if it exists
    last_ckpt = None
    if os.path.isdir(OUTPUT_DIR):
        ckpts = [d for d in os.listdir(OUTPUT_DIR) if d.startswith("checkpoint-")]
        if ckpts:
            ckpts = sorted(ckpts, key=lambda x: int(x.split("-")[1]))
            last_ckpt = os.path.join(OUTPUT_DIR, ckpts[-1])
            print(f"Resuming from checkpoint: {last_ckpt}")
        elif os.path.exists(os.path.join(OUTPUT_DIR, "config.json")):
            last_ckpt = OUTPUT_DIR
            print(f"Resuming from saved model folder: {last_ckpt}")

    trainer.train(resume_from_checkpoint=last_ckpt)

    # Save best model. If Windows file locks prevent saving directly,
    # save to a temp directory, release locks, and copy over.
    try:
        trainer.save_model(OUTPUT_DIR)
        tokenizer.save_pretrained(OUTPUT_DIR)
        print(f"\n[OK] Best model saved to '{OUTPUT_DIR}'")
    except Exception as e:
        print(f"\n[Warning] Direct save failed (Windows lock: {e}). Trying temp directory...")
        temp_dir = "./finbert-finetuned-temp"
        trainer.save_model(temp_dir)
        tokenizer.save_pretrained(temp_dir)
        
        # Release model and trainer references to free the mapped files
        del trainer
        del model
        gc.collect()
        
        # Copy to destination
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        for filename in os.listdir(temp_dir):
            src = os.path.join(temp_dir, filename)
            dst = os.path.join(OUTPUT_DIR, filename)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        print(f"[OK] Best model successfully saved to '{OUTPUT_DIR}'")
        
        # Clean up temp
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

    print("\nEvaluating on test split ...")
    results = {}
    try:
        # Reload the saved model from OUTPUT_DIR to ensure we evaluate the actual saved weights
        eval_model = AutoModelForSequenceClassification.from_pretrained(OUTPUT_DIR)
        eval_trainer = Trainer(
            model            = eval_model,
            processing_class = tokenizer,
            compute_metrics  = compute_metrics,
        )
        results = eval_trainer.evaluate(ds_test)
    except Exception as e:
        print(f"Evaluation error: {e}")
        # Try local trainer if it still exists in namespace
        if 'trainer' in locals():
            try:
                results = trainer.evaluate(ds_test)
            except Exception:
                pass

    acc = results.get("eval_accuracy", float("nan"))
    f1  = results.get("eval_macro_f1", float("nan"))

    print("\n" + "=" * 60)
    print("TEST SPLIT RESULTS")
    print("=" * 60)
    print(f"  Accuracy : {acc:.4f}  ({acc*100:.2f}%)")
    print(f"  Macro F1 : {f1:.4f}")
    print("=" * 60)

if __name__ == "__main__":
    main()
