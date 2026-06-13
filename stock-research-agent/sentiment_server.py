"""
sentiment_server.py — Flask sentiment inference server
=======================================================

Port  : 8001
Model : ./finbert-finetuned  (falls back to ProsusAI/finbert if not found)

Endpoints
---------
GET  /health   → { "status": "ok", "model": "finbert" }
POST /predict  → accepts { "headlines": [...] }
                 returns the agreed contract schema (see below)

/predict response contract (DO NOT DEVIATE — tool_06 validates this schema):
{
  "predictions": [
    {
      "headline":      "...",
      "label":         "positive",          # always lowercase
      "score":         0.94,
      "probabilities": {
        "positive": 0.94,
        "neutral":  0.04,
        "negative": 0.02
      }
    }
  ],
  "model_name":    "finbert",
  "model_version": "1.0"
}

Label mapping
-------------
FinBERT's config.id2label = {0: "positive", 1: "negative", 2: "neutral"}
We normalise ALL labels to lowercase before returning so the consumer
never receives mixed-case strings.

Performance
-----------
The pipeline is loaded once at startup and reused across requests.
Headline texts are truncated to 512 characters before tokenisation.
Target: <200 ms / headline on CPU.

Usage
-----
    python sentiment_server.py
    # or with gunicorn for production:
    # gunicorn -w 1 -b 0.0.0.0:8001 sentiment_server:app
"""

import os
import time
import logging
from flask import Flask, request, jsonify
from transformers import pipeline

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
FINETUNED_PATH   = "./finbert-finetuned"
FALLBACK_MODEL   = "ProsusAI/finbert"
SERVER_PORT      = 8001
MODEL_VERSION    = "1.0"
MAX_HEADLINE_LEN = 512       # FinBERT hard limit (characters before tokenisation)
VALID_LABELS     = {"positive", "negative", "neutral"}

# ── Model loading ─────────────────────────────────────────────────────────────

def _load_pipeline():
    """
    Attempt to load the fine-tuned model from FINETUNED_PATH.
    Falls back to the base ProsusAI/finbert if the fine-tuned model is not ready.
    Wrapped in try/except so the server always starts.
    """
    # Check if fine-tuned model directory exists and is non-empty
    if os.path.isdir(FINETUNED_PATH) and os.listdir(FINETUNED_PATH):
        model_path = FINETUNED_PATH
        log.info(f"Loading fine-tuned model from '{FINETUNED_PATH}' ...")
    else:
        model_path = FALLBACK_MODEL
        log.warning(
            f"Fine-tuned model not found at '{FINETUNED_PATH}'. "
            f"Falling back to '{FALLBACK_MODEL}'. "
            "Run train.py first to generate the fine-tuned model."
        )

    try:
        clf = pipeline(
            task               = "text-classification",
            model              = model_path,
            tokenizer          = model_path,
            top_k              = None,
            device             = -1,      # -1 → CPU; set to 0 for first GPU
        )
        log.info(f"Model loaded successfully from '{model_path}'.")
        return clf, model_path
    except Exception as exc:
        log.error(
            f"Failed to load model from '{model_path}': {exc}. "
            "Server is starting without a model - /predict will return 503."
        )
        return None, None


# Load at module level (once, on startup)
_classifier, _model_path = _load_pipeline()

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)


# ── /health ───────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    """
    Liveness probe.
    Returns 200 if model is loaded, 503 if model failed to load.
    """
    if _classifier is None:
        return jsonify({
            "status": "error",
            "model":  "finbert",
            "detail": "Model failed to load — see server logs.",
        }), 503

    return jsonify({
        "status": "ok",
        "model":  "finbert",
    }), 200


# ── /predict ──────────────────────────────────────────────────────────────────
@app.route("/predict", methods=["POST"])
def predict():
    """
    Accepts: { "headlines": ["headline 1", "headline 2", ...] }
    Returns: the agreed contract schema (see module docstring).

    Edge cases handled:
    - Missing / non-list 'headlines' key → 400
    - Empty headlines list               → 200 with empty predictions list
    - Model not loaded                   → 503
    - Individual inference error         → neutral prediction with score 0.33
    """
    # ── Guard: model must be loaded ───────────────────────────────────────────
    if _classifier is None:
        return jsonify({
            "error": "Model is not loaded. Check server logs.",
        }), 503

    # ── Parse request ─────────────────────────────────────────────────────────
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    headlines = body.get("headlines")
    if headlines is None:
        return jsonify({"error": "Missing required field: 'headlines'."}), 400
    if not isinstance(headlines, list):
        return jsonify({"error": "'headlines' must be a JSON array."}), 400

    # ── Guard: Batch size limit ───────────────────────────────────────────────
    if len(headlines) > 50:
        return jsonify({"error": "Batch size exceeds maximum limit of 50 headlines."}), 400

    # ── Guard: Verify all elements are strings or numbers ─────────────────────
    for i, h in enumerate(headlines):
        if h is None or isinstance(h, (dict, list)):
            return jsonify({"error": f"Headline at index {i} must be a string or primitive value."}), 400

    # ── Empty input — valid, returns empty predictions ─────────────────────────
    if len(headlines) == 0:
        return jsonify({
            "predictions":   [],
            "model_name":    "finbert",
            "model_version": MODEL_VERSION,
        }), 200

    # ── Truncate & coerce headlines ───────────────────────────────────────────
    clean_headlines = [str(h).strip()[:MAX_HEADLINE_LEN] for h in headlines]

    # ── Inference ─────────────────────────────────────────────────────────────
    predictions = []
    t_start     = time.perf_counter()

    try:
        # Pass the entire list of clean_headlines to run batched inference in PyTorch
        batch_results = _classifier(clean_headlines)
    except Exception as exc:
        log.error(f"Batch inference error: {exc}")
        batch_results = [None] * len(clean_headlines)

    for i, original in enumerate(headlines):
        try:
            raw_scores = batch_results[i]
            if raw_scores is None:
                raise ValueError("Batch inference returned None for this item")

            # Build a label → score map, normalising labels to lowercase
            score_map: dict[str, float] = {
                s["label"].lower(): round(float(s["score"]), 4)
                for s in raw_scores
            }

            # Ensure all three keys are always present (defensive)
            for lbl in VALID_LABELS:
                score_map.setdefault(lbl, 0.0)

            # Top label = the one with the highest probability
            top_label = max(score_map, key=score_map.__getitem__)
            top_score = score_map[top_label]

            # Normalise to a known-valid label (guard against unexpected output)
            if top_label not in VALID_LABELS:
                top_label = "neutral"
                top_score = score_map.get("neutral", 0.33)

            predictions.append({
                "headline":      str(original),
                "label":         top_label,
                "score":         top_score,
                "probabilities": {
                    "positive": score_map.get("positive", 0.0),
                    "neutral":  score_map.get("neutral",  0.0),
                    "negative": score_map.get("negative", 0.0),
                },
            })

        except Exception as exc:
            log.error(f"Inference error for headline '{clean_headlines[i][:60]}...': {exc}")
            # Graceful degradation — return a neutral prediction rather than 500
            predictions.append({
                "headline":      str(original),
                "label":         "neutral",
                "score":         0.33,
                "probabilities": {
                    "positive": 0.33,
                    "neutral":  0.34,
                    "negative": 0.33,
                },
            })

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    per_head   = elapsed_ms / max(len(clean_headlines), 1)
    log.info(
        f"Processed {len(clean_headlines)} headline(s) in "
        f"{elapsed_ms:.1f} ms ({per_head:.1f} ms/headline)."
    )

    return jsonify({
        "predictions":   predictions,
        "model_name":    "finbert",
        "model_version": MODEL_VERSION,
    }), 200


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(f"Starting sentiment server on http://0.0.0.0:{SERVER_PORT} ...")
    app.run(
        host  = "0.0.0.0",
        port  = SERVER_PORT,
        debug = False,          # never True in production
    )
