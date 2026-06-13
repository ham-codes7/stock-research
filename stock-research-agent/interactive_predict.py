# interactive_predict.py
# Run this in your terminal:
#   python interactive_predict.py
#
# This script will load the fine-tuned FinBERT model and let you input
# custom financial sentences/headlines to see the predicted sentiment
# and confidence scores in real-time.

import os
import sys

# Suppress Hugging Face warnings to keep the console output clean
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

try:
    from transformers import pipeline
except ImportError:
    print("Error: The 'transformers' package is not installed. Please run:")
    print("  pip install -r requirements_ml.txt")
    sys.exit(1)

MODEL_DIR = "./finbert-finetuned"
FALLBACK_MODEL = "ProsusAI/finbert"

def main():
    print("=" * 60)
    print("        FinBERT Sentiment Analysis Interactive Demo")
    print("=" * 60)
    
    # 1. Determine model path
    if os.path.isdir(MODEL_DIR) and os.path.exists(os.path.join(MODEL_DIR, "config.json")):
        model_path = MODEL_DIR
        print(f"Loading fine-tuned model from local directory '{MODEL_DIR}' ...")
    else:
        model_path = FALLBACK_MODEL
        print(f"Fine-tuned model not found at '{MODEL_DIR}'.")
        print(f"Loading base pretrained model '{FALLBACK_MODEL}' instead ...")

    # 2. Load the classification pipeline
    try:
        classifier = pipeline(
            task="text-classification",
            model=model_path,
            tokenizer=model_path,
            top_k=None,
            device=-1,  # Force CPU to avoid CUDA initialization delays
        )
        print("Model loaded successfully!")
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

    print("=" * 60)
    print("Type a headline or sentence to analyze its sentiment.")
    print("Type 'quit', 'exit', or 'q' to stop.")
    print("=" * 60)

    # 3. Interactive Loop
    while True:
        try:
            user_input = input("\nEnter text: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting demo.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("Exiting demo. Good luck with your hackathon!")
            break

        # Run inference
        try:
            results = classifier(user_input)[0]
            
            # Extract scores and convert keys to lowercase
            score_map = {item["label"].lower(): float(item["score"]) for item in results}
            
            # Handle standard labels (positive, negative, neutral)
            for label in ("positive", "negative", "neutral"):
                score_map.setdefault(label, 0.0)
                
            # Get the top label and its score
            top_label = max(score_map, key=score_map.get)
            top_score = score_map[top_label]
            
            # Print results beautifully using ASCII formatting
            print("-" * 50)
            print(f"Input: {user_input}")
            print(f"Predicted Sentiment: {top_label.upper()} (Confidence: {top_score * 100:.2f}%)")
            
            print("\nSentiment Signals:")
            print(f"  - \"{user_input}\" -> {top_label.upper()} sentiment detected")
            
            print("\nProbability Distribution:")
            for label, prob in sorted(score_map.items(), key=lambda x: x[1], reverse=True):
                # Simple progress bar using ASCII
                bar_len = int(prob * 20)
                bar = "#" * bar_len + " " * (20 - bar_len)
                print(f"  - {label:<9}: [{bar}] {prob * 100:.2f}%")
            print("-" * 50)

        except Exception as e:
            print(f"Error analyzing text: {e}")

if __name__ == "__main__":
    main()
