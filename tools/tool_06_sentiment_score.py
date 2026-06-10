"""
TOOL 06 — sentiment_score(headlines)
======================================

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THIS FILE DOES (READ THIS FIRST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This file is the BRIDGE between your agent and your ML teammate's model.

Think of it in two halves:

HALF 1 — YOUR CODE (what you build and own):
    - Receives a list of financial news headlines
    - Cleans and preprocesses them
    - Sends them to your ML teammate's model via an HTTP API call
    - Falls back to a rule-based scorer if the model is unavailable
    - Structures the output into the standard agent schema
    - Returns sentiment scores + labels + confidence the agent can reason over

HALF 2 — YOUR ML TEAMMATE'S CODE (what they build):
    - A Python script that loads a trained sentiment model
    - Wraps it in a simple Flask/FastAPI server
    - Exposes one POST endpoint: /predict
    - Accepts a list of headlines, returns scores and labels
    - Runs locally on their machine (or shared server) during hackathon

The two halves talk to each other over HTTP.
Your code sends a request → their server responds → you process the response.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO TELL YOUR ML TEAMMATE (COPY THIS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tell them exactly this:

"I need you to build a sentiment API server that does the following:

1. DATASET TO USE:
   Download the Financial PhraseBank dataset from Hugging Face:
   https://huggingface.co/datasets/financial_phrasebank
   Use the 'sentences_allagree' split — these are the highest quality labels.
   Labels: 0 = negative, 1 = neutral, 2 = positive

2. MODEL TO TRAIN (or use pretrained):
   Option A (recommended — faster, better):
     Use FinBERT — a BERT model pretrained on financial text.
     It's already on Hugging Face: 'ProsusAI/finbert'
     Fine-tune it on Financial PhraseBank for 3-5 epochs.
     This will give you ~92% accuracy with minimal work.

   Option B (from scratch):
     Train a simple classifier on top of sentence-transformers
     using Financial PhraseBank. Use sklearn's LogisticRegression
     or a small PyTorch linear head. Simpler but less accurate (~80%).

3. WHAT THE SERVER MUST DO:
   Run a Flask or FastAPI server on http://localhost:8001
   Expose one endpoint: POST /predict
   
   Input JSON format (what I will send):
   {
     "headlines": [
       "Apple reports record quarterly earnings",
       "Tesla faces SEC investigation",
       "Microsoft revenue misses estimates"
     ]
   }
   
   Output JSON format (what you must return):
   {
     "predictions": [
       {
         "headline": "Apple reports record quarterly earnings",
         "label": "positive",
         "score": 0.94,
         "probabilities": {
           "positive": 0.94,
           "neutral":  0.04,
           "negative": 0.02
         }
       },
       {
         "headline": "Tesla faces SEC investigation",
         "label": "negative",
         "score": 0.88,
         "probabilities": {
           "positive": 0.05,
           "neutral":  0.07,
           "negative": 0.88
         }
       }
     ],
     "model_name": "finbert-finetuned",
     "model_version": "1.0"
   }

4. HOW TO RUN IT:
   python sentiment_server.py
   Server must be running on port 8001 before the agent starts.
   
5. STARTER CODE FOR THEIR SERVER (give them this):

   from flask import Flask, request, jsonify
   from transformers import pipeline

   app = Flask(__name__)
   
   # Load FinBERT (downloads automatically from HuggingFace)
   classifier = pipeline(
       'text-classification',
       model='ProsusAI/finbert',
       return_all_scores=True
   )
   
   @app.route('/predict', methods=['POST'])
   def predict():
       data = request.json
       headlines = data.get('headlines', [])
       predictions = []
       for headline in headlines:
           scores = classifier(headline[:512])[0]  # FinBERT max 512 tokens
           score_map = {s['label'].lower(): s['score'] for s in scores}
           top = max(scores, key=lambda x: x['score'])
           predictions.append({
               'headline': headline,
               'label': top['label'].lower(),
               'score': round(top['score'], 4),
               'probabilities': {k: round(v, 4) for k, v in score_map.items()}
           })
       return jsonify({
           'predictions': predictions,
           'model_name': 'finbert',
           'model_version': '1.0'
       })
   
   if __name__ == '__main__':
       app.run(host='0.0.0.0', port=8001)

That's everything they need. Their job is to:
   a) Install transformers, flask, torch
   b) Run that server file
   c) Test it with curl or Postman before integration day
"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW THE CONNECTION WORKS (THE ACTUAL FLOW)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: Tool 2 (get_recent_news) runs and returns:
        result["data"]["headlines_for_sentiment"] = [
            "Apple beats earnings estimates",
            "SEC probes Tesla accounting",
            ...
        ]

Step 2: Agent passes that list to THIS tool:
        sentiment_score(headlines=result["data"]["headlines_for_sentiment"])

Step 3: THIS tool sends those headlines to your ML teammate's server:
        POST http://localhost:8001/predict
        Body: {"headlines": [...]}

Step 4: Their server runs the model, returns predictions JSON

Step 5: THIS tool processes the predictions:
        - Computes an aggregate sentiment score (0.0 to 1.0)
        - Counts positive / neutral / negative headlines
        - Flags high-conviction signals (score > 0.85)
        - Returns everything in the standard agent schema

Step 6: Agent uses sentiment output in thesis generation:
        "News sentiment is bearish (0.31/1.0) — 7 of 12 headlines negative,
         with high-conviction signals around regulatory risk."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FALLBACK WHEN ML SERVER IS NOT RUNNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If your ML teammate's server is down or hasn't been integrated yet,
this tool automatically falls back to a rule-based keyword scorer.
It's not as accurate as the trained model but it's better than nothing.
The agent will know which mode was used via the metadata.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APIS REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YOUR SIDE:
    requests — pip install requests
    No API key needed

ML TEAMMATE'S SIDE:
    transformers — pip install transformers
    torch        — pip install torch
    flask        — pip install flask
    (or fastapi + uvicorn if they prefer FastAPI)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import requests
from datetime import datetime, timezone
from typing import Optional


# ── Configuration ─────────────────────────────────────────────────────────────
# This is your ML teammate's server address.
# During hackathon on same machine: http://localhost:8001
# If on different machines on same network: http://<their-ip>:8001
ML_SERVER_URL    = "http://localhost:8001"
ML_PREDICT_PATH  = "/predict"
ML_TIMEOUT_SECS  = 10  # how long to wait before falling back


# ── Rule-based fallback keywords ─────────────────────────────────────────────
# Used ONLY when ML server is unavailable.
# These are financial-domain specific — NOT generic sentiment words.
POSITIVE_KEYWORDS = [
    "beat", "beats", "record", "growth", "grew", "surge", "surged",
    "profit", "gains", "raised", "upgrade", "upgraded", "buy",
    "strong", "outperform", "expand", "expansion", "innovation",
    "partnership", "deal", "dividend", "buyback", "milestone",
    "exceeded", "exceeds", "above", "ahead", "overweight",
    "recovery", "momentum", "robust", "solid", "positive",
]

NEGATIVE_KEYWORDS = [
    "miss", "misses", "missed", "loss", "losses", "decline", "declined",
    "fell", "fall", "drop", "dropped", "cut", "downgrade", "downgraded",
    "sell", "underperform", "weak", "below", "disappointing", "warning",
    "investigation", "lawsuit", "fine", "penalty", "recall", "layoff",
    "bankruptcy", "debt", "default", "concern", "risk", "volatile",
    "uncertainty", "headwind", "slowdown", "contraction", "negative",
]


def sentiment_score(headlines: list,
                    ticker: Optional[str] = None) -> dict:
    """
    Score sentiment of financial news headlines using ML model or fallback.

    REQUIRED PARAMETERS:
        headlines (list): List of headline strings from Tool 2's output.
                         Pass result["data"]["headlines_for_sentiment"] directly.

    OPTIONAL PARAMETERS:
        ticker (str): Ticker context for metadata e.g. "AAPL"

    VALIDATION RULES:
        - Empty list returns zero-score result, not an error
        - Headlines over 512 chars are truncated (FinBERT model limit)
        - Duplicate headlines deduplicated before scoring
        - ML server timeout falls back to rule-based scorer automatically
    """

    if not headlines:
        return _empty_response(ticker)

    # ── Clean and deduplicate headlines ───────────────────────────────────────
    cleaned = []
    seen    = set()
    for h in headlines:
        h = str(h).strip()
        if not h or h.lower() in seen:
            continue
        seen.add(h.lower())
        cleaned.append(h[:512])  # FinBERT max token limit

    if not cleaned:
        return _empty_response(ticker)

    # ── Attempt ML server ─────────────────────────────────────────────────────
    predictions  = None
    model_used   = None
    server_error = None

    try:
        predictions, model_used = _call_ml_server(cleaned)
    except Exception as e:
        server_error = str(e)

    # ── Fallback to rule-based if ML server failed ────────────────────────────
    if predictions is None:
        predictions = _rule_based_score(cleaned)
        model_used  = "rule_based_fallback"

    # ── Aggregate scoring ─────────────────────────────────────────────────────
    aggregate    = _compute_aggregate(predictions)

    # ── High conviction signals ───────────────────────────────────────────────
    # These are headlines where the model is very confident — worth flagging
    CONVICTION_THRESHOLD = 0.85
    high_conviction = [
        p for p in predictions
        if p.get("score", 0) >= CONVICTION_THRESHOLD
    ]

    # ── Dominant themes in negative headlines ─────────────────────────────────
    negative_headlines = [
        p["headline"] for p in predictions
        if p.get("label") == "negative"
    ]
    negative_themes = _extract_negative_themes(negative_headlines)

    # ── Flags ─────────────────────────────────────────────────────────────────
    flags = []

    if model_used == "rule_based_fallback":
        flags.append(
            "ML_SERVER_OFFLINE — using rule-based fallback scorer. "
            f"Start ML server at {ML_SERVER_URL} for accurate predictions. "
            + (f"Error: {server_error}" if server_error else "")
        )

    sentiment_label = aggregate["overall_label"]

    if sentiment_label == "BEARISH" and aggregate["score"] < 0.3:
        flags.append(
            f"STRONG_BEARISH_SIGNAL — aggregate score {aggregate['score']:.2f}/1.0. "
            f"{aggregate['negative_count']} of {aggregate['total']} headlines negative."
        )
    elif sentiment_label == "BULLISH" and aggregate["score"] > 0.75:
        flags.append(
            f"STRONG_BULLISH_SIGNAL — aggregate score {aggregate['score']:.2f}/1.0. "
            f"{aggregate['positive_count']} of {aggregate['total']} headlines positive."
        )

    if negative_themes:
        flags.append(
            f"NEGATIVE_THEMES_DETECTED — recurring themes: {', '.join(negative_themes)}"
        )

    if len(high_conviction) >= 3:
        flags.append(
            f"HIGH_CONVICTION_SIGNALS — {len(high_conviction)} headlines with "
            f">={int(CONVICTION_THRESHOLD*100)}% model confidence."
        )

    # ── Confidence score ──────────────────────────────────────────────────────
    # Higher confidence when: more headlines, ML model used, consistent signal
    base_confidence = min(100, len(cleaned) * 10)  # 10% per headline, capped at 100
    if model_used != "rule_based_fallback":
        model_bonus = 20
    else:
        model_bonus = 0

    # Penalise if signal is very mixed (lots of both positive and negative)
    pos = aggregate["positive_count"]
    neg = aggregate["negative_count"]
    neu = aggregate["neutral_count"]
    total = aggregate["total"]
    if total > 0 and pos > 0 and neg > 0:
        mix_penalty = -int((min(pos, neg) / total) * 30)
    else:
        mix_penalty = 0

    confidence_score = max(0, min(100, base_confidence + model_bonus + mix_penalty))
    confidence_label = (
        "HIGH"   if confidence_score >= 70 else
        "MEDIUM" if confidence_score >= 40 else
        "LOW — few headlines or mixed signal, interpret with caution"
    )

    return {
        "data": {
            "context": {
                "ticker":            ticker,
                "headlines_scored":  len(cleaned),
                "headlines_input":   len(headlines),
                "duplicates_removed": len(headlines) - len(cleaned),
            },
            "aggregate": aggregate,
            "per_headline_predictions": predictions,
            "high_conviction_signals":  high_conviction,
            "negative_themes":          negative_themes,
            "flags":                    flags,

            # ── Ready-made agent prompt insert ────────────────────────────────
            # Pass this string directly into the agent's synthesis prompt.
            # The agent uses this line in the research brief automatically.
            "agent_summary_line": _build_agent_summary(
                ticker, aggregate, negative_themes, model_used
            ),
        },
        "metadata": {
            "tool":              "sentiment_score",
            "version":           "1.0",
            "ticker_context":    ticker,
            "timestamp_utc":     datetime.now(timezone.utc).isoformat(),
            "model_used":        model_used,
            "ml_server_url":     ML_SERVER_URL,
            "ml_server_online":  model_used != "rule_based_fallback",
            "conviction_threshold": CONVICTION_THRESHOLD,
        },
        "validation_results": {
            "headlines_received": len(headlines),
            "headlines_scored":   len(cleaned),
            "model_responded":    model_used != "rule_based_fallback",
            "flags_detected":     flags,
            "flag_count":         len(flags),
        },
        "confidence_assessment": {
            "score_pct":   confidence_score,
            "label":       confidence_label,
            "model_used":  model_used,
            "note": (
                "Confidence reflects headline volume + model quality + signal consistency. "
                "Rule-based fallback is less accurate than trained FinBERT model."
            ),
        },
        "missing_information": {
            "missing_fields":  [] if predictions else ["predictions"],
            "interpretation": (
                "All headlines scored successfully."
                if predictions else
                "No predictions generated — check ML server or headline input."
            ),
        },
    }


# ── ML server call ────────────────────────────────────────────────────────────

def _call_ml_server(headlines: list) -> tuple:
    """
    POST headlines to your ML teammate's sentiment server.

    WHAT THIS DOES:
        Sends a JSON request to http://localhost:8001/predict
        Expects the response format your ML teammate agreed to implement.
        Times out after ML_TIMEOUT_SECS and raises exception for fallback.

    Returns (predictions_list, model_name) or raises Exception.
    """
    url     = ML_SERVER_URL + ML_PREDICT_PATH
    payload = {"headlines": headlines}

    response = requests.post(
        url,
        json=payload,
        timeout=ML_TIMEOUT_SECS,
    )

    if response.status_code != 200:
        raise Exception(
            f"ML server returned HTTP {response.status_code}: {response.text[:200]}"
        )

    data = response.json()

    # ── Validate response schema ───────────────────────────────────────────────
    # Your ML teammate's server MUST return 'predictions' as a list.
    # Each prediction MUST have: headline, label, score
    if "predictions" not in data:
        raise Exception(
            "ML server response missing 'predictions' key. "
            "Ask ML teammate to match the agreed output schema."
        )

    raw_predictions = data["predictions"]
    model_name      = data.get("model_name", "unknown_model")

    # Normalise each prediction to standard schema
    normalised = []
    for pred in raw_predictions:
        label = str(pred.get("label", "neutral")).lower()
        # Ensure label is one of three valid values
        if label not in ("positive", "negative", "neutral"):
            label = "neutral"

        normalised.append({
            "headline":      pred.get("headline", ""),
            "label":         label,
            "score":         round(float(pred.get("score", 0.5)), 4),
            "probabilities": pred.get("probabilities", {
                "positive": 0.33,
                "neutral":  0.34,
                "negative": 0.33,
            }),
            "scored_by":     "ml_model",
        })

    return normalised, model_name


# ── Rule-based fallback scorer ────────────────────────────────────────────────

def _rule_based_score(headlines: list) -> list:
    """
    Simple keyword-based scorer used when ML server is unavailable.

    HOW IT WORKS:
        For each headline, count positive and negative financial keywords.
        Score = positive_count / (positive_count + negative_count + epsilon)
        This is NOT as accurate as FinBERT but provides a directional signal.

    IMPORTANT FOR YOUR ML TEAMMATE:
        The fallback produces results in the SAME schema as the ML model.
        So downstream code works identically regardless of which scorer runs.
        This is the key design decision — schema consistency means the agent
        never needs to know which scorer was used.
    """
    predictions = []

    for headline in headlines:
        words     = set(re.sub(r'[^\w\s]', '', headline.lower()).split())
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in words)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in words)

        total = pos_count + neg_count + 1e-9  # epsilon avoids zero division

        pos_prob  = round(pos_count / total, 4)
        neg_prob  = round(neg_count / total, 4)
        neu_prob  = round(max(0, 1 - pos_prob - neg_prob), 4)

        if pos_count > neg_count:
            label = "positive"
            score = round(pos_prob, 4)
        elif neg_count > pos_count:
            label = "negative"
            score = round(neg_prob, 4)
        else:
            label = "neutral"
            score = round(neu_prob, 4)

        predictions.append({
            "headline":      headline,
            "label":         label,
            "score":         score,
            "probabilities": {
                "positive": pos_prob,
                "neutral":  neu_prob,
                "negative": neg_prob,
            },
            "scored_by": "rule_based_fallback",
        })

    return predictions


# ── Aggregate computation ─────────────────────────────────────────────────────

def _compute_aggregate(predictions: list) -> dict:
    """
    Compute aggregate sentiment from per-headline predictions.

    AGGREGATE SCORE (0.0 to 1.0):
        1.0 = fully bullish
        0.5 = neutral
        0.0 = fully bearish

    LABEL:
        > 0.6  → BULLISH
        < 0.4  → BEARISH
        else   → NEUTRAL

    This is what the agent puts in the research brief.
    """
    if not predictions:
        return {
            "score":          0.5,
            "overall_label":  "NEUTRAL",
            "positive_count": 0,
            "neutral_count":  0,
            "negative_count": 0,
            "total":          0,
        }

    label_map = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}

    scores = [
        label_map.get(p.get("label", "neutral"), 0.5)
        for p in predictions
    ]

    aggregate_score = round(sum(scores) / len(scores), 4)

    positive_count = sum(1 for p in predictions if p.get("label") == "positive")
    neutral_count  = sum(1 for p in predictions if p.get("label") == "neutral")
    negative_count = sum(1 for p in predictions if p.get("label") == "negative")
    total          = len(predictions)

    if aggregate_score > 0.6:
        overall_label = "BULLISH"
    elif aggregate_score < 0.4:
        overall_label = "BEARISH"
    else:
        overall_label = "NEUTRAL"

    return {
        "score":          aggregate_score,
        "overall_label":  overall_label,
        "positive_count": positive_count,
        "neutral_count":  neutral_count,
        "negative_count": negative_count,
        "total":          total,
        "pct_positive":   round(positive_count / total * 100, 1) if total else 0,
        "pct_negative":   round(negative_count / total * 100, 1) if total else 0,
    }


# ── Negative theme extractor ──────────────────────────────────────────────────

def _extract_negative_themes(negative_headlines: list) -> list:
    """
    Identify recurring themes in negative headlines.
    Helps the agent understand WHY sentiment is negative, not just THAT it is.
    """
    THEME_KEYWORDS = {
        "regulatory":    ["sec", "investigation", "probe", "fine", "penalty",
                          "lawsuit", "antitrust", "regulatory"],
        "earnings_miss": ["miss", "missed", "below", "disappointing", "weak",
                          "shortfall", "guidance cut"],
        "leadership":    ["ceo", "cfo", "resign", "departure", "steps down",
                          "management"],
        "macro":         ["recession", "inflation", "rate", "fed", "tariff",
                          "slowdown", "gdp"],
        "competition":   ["competition", "market share", "competitor", "rival",
                          "disruption"],
        "financial":     ["debt", "default", "bankruptcy", "liquidity",
                          "write-down", "impairment"],
    }

    theme_counts = {}
    all_text     = " ".join(negative_headlines).lower()

    for theme, keywords in THEME_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in all_text)
        if count > 0:
            theme_counts[theme] = count

    # Return top 3 themes sorted by keyword frequency
    sorted_themes = sorted(theme_counts, key=theme_counts.get, reverse=True)
    return sorted_themes[:3]


# ── Agent summary line builder ────────────────────────────────────────────────

def _build_agent_summary(ticker, aggregate, negative_themes, model_used) -> str:
    """
    Build a ready-made one-line summary the agent pastes into the research brief.

    Example output:
    "News sentiment for AAPL is BEARISH (score: 0.31/1.0) — 7 of 10 headlines
     negative, with recurring themes around regulatory risk and earnings miss.
     [rule-based fallback — start ML server for higher accuracy]"
    """
    score   = aggregate.get("score", 0.5)
    label   = aggregate.get("overall_label", "NEUTRAL")
    pos     = aggregate.get("positive_count", 0)
    neg     = aggregate.get("negative_count", 0)
    total   = aggregate.get("total", 0)
    ticker_str = f" for {ticker}" if ticker else ""

    theme_str = ""
    if negative_themes:
        theme_str = (
            f", with recurring themes around "
            + " and ".join(negative_themes)
        )

    model_note = (
        " [ML model scored]"
        if model_used != "rule_based_fallback"
        else " [rule-based fallback — start ML server for higher accuracy]"
    )

    return (
        f"News sentiment{ticker_str} is {label} "
        f"(score: {score:.2f}/1.0) — "
        f"{neg} of {total} headlines negative, "
        f"{pos} of {total} headlines positive"
        f"{theme_str}."
        f"{model_note}"
    )


# ── Empty response ────────────────────────────────────────────────────────────

def _empty_response(ticker) -> dict:
    return {
        "data": {
            "context":                  {"ticker": ticker, "headlines_scored": 0},
            "aggregate":                {"score": 0.5, "overall_label": "NEUTRAL", "total": 0},
            "per_headline_predictions": [],
            "high_conviction_signals":  [],
            "negative_themes":          [],
            "flags":                    ["NO_HEADLINES — empty headline list provided"],
            "agent_summary_line":       "No headlines available for sentiment scoring.",
        },
        "metadata": {
            "tool":           "sentiment_score",
            "version":        "1.0",
            "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
            "model_used":     None,
            "ml_server_url":  ML_SERVER_URL,
            "ml_server_online": False,
        },
        "validation_results": {
            "headlines_received": 0,
            "headlines_scored":   0,
            "model_responded":    False,
            "flags_detected":     ["NO_HEADLINES"],
        },
        "confidence_assessment": {
            "score_pct": 0,
            "label":     "NO_DATA",
        },
        "missing_information": {
            "missing_fields":  ["headlines"],
            "interpretation":  "Pass headlines from Tool 2's headlines_for_sentiment field.",
        },
    }


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # Simulate what Tool 2 would pass in
    mock_headlines = [
        "Apple beats earnings estimates by 12%, raises guidance",
        "Tesla faces SEC investigation over self-driving claims",
        "Microsoft Azure revenue surges 35% in strong quarterly results",
        "Netflix subscriber growth disappoints, shares fall 8%",
        "Amazon announces record Prime Day sales, stock rises",
        "Meta faces antitrust lawsuit from FTC over Instagram acquisition",
        "Nvidia reports blowout earnings, raises full-year outlook",
        "Intel cuts dividend amid ongoing market share losses",
        "Google parent Alphabet announces $70 billion buyback program",
        "Goldman Sachs downgrades sector citing recession risk",
    ]

    print("\n" + "="*60)
    print("TEST 1: Rule-based fallback (ML server offline)")
    print("="*60)
    result = sentiment_score(mock_headlines, ticker="TECH_SECTOR")

    if result["data"]:
        print(json.dumps({
            "aggregate":         result["data"]["aggregate"],
            "agent_summary":     result["data"]["agent_summary_line"],
            "negative_themes":   result["data"]["negative_themes"],
            "high_conviction":   [
                {"headline": h["headline"][:60], "label": h["label"], "score": h["score"]}
                for h in result["data"]["high_conviction_signals"]
            ],
            "flags":             result["data"]["flags"],
            "model_used":        result["metadata"]["model_used"],
            "confidence":        result["confidence_assessment"],
        }, indent=2))

    print("\n" + "="*60)
    print("TEST 2: Per-headline predictions sample")
    print("="*60)
    for pred in result["data"]["per_headline_predictions"][:5]:
        print(
            f"  [{pred['label'].upper():8}] "
            f"score={pred['score']:.2f} | "
            f"{pred['headline'][:65]}"
        )

    print("\n" + "="*60)
    print("TEST 3: Empty headlines list")
    print("="*60)
    result3 = sentiment_score([])
    print(json.dumps(result3["data"]["flags"], indent=2))

    print("\n" + "="*60)
    print("TEST 4: Integration with Tool 2 output format")
    print("="*60)
    print("In your agent, connect Tool 2 → Tool 6 like this:")
    print()
    print("  news_result = get_recent_news('AAPL', 'Apple Inc.')")
    print("  headlines   = news_result['data']['headlines_for_sentiment']")
    print("  sentiment   = sentiment_score(headlines, ticker='AAPL')")
    print("  print(sentiment['data']['agent_summary_line'])")
    print("  print(sentiment['data']['aggregate'])")

    print("\n" + "="*60)
    print("TEST 5: When ML server IS running (test manually)")
    print("="*60)
    print("Start your ML teammate's server first:")
    print("  python sentiment_server.py")
    print()
    print("Then run:")
    print("  result = sentiment_score(mock_headlines, ticker='AAPL')")
    print("  print(result['metadata']['ml_server_online'])  # should be True")
    print("  print(result['metadata']['model_used'])        # should be 'finbert'")

    """
from tools.tool_02_recent_news    import get_recent_news
from tools.tool_06_sentiment_score import sentiment_score

# Tool 2 output feeds directly into Tool 6
news      = get_recent_news("AAPL", "Apple Inc.")
headlines = news["data"]["headlines_for_sentiment"]
sentiment = sentiment_score(headlines, ticker="AAPL")

# What the agent uses
print(sentiment["data"]["agent_summary_line"])
print(sentiment["data"]["aggregate"])
print(sentiment["data"]["negative_themes"])
    """