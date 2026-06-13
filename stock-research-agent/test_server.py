"""
test_server.py — Quick smoke tests for the sentiment server.

Usage:
    1. Start the server:   python sentiment_server.py
    2. In another terminal: python test_server.py

Tests:
    1. /health endpoint returns 200
    2. /predict with sample headlines returns correct schema
    3. /predict with empty list returns empty predictions
    4. /predict with missing field returns 400
    5. Timing check — each headline should be < 200ms
"""

import time
import json
import requests

BASE_URL = "http://127.0.0.1:8001"

PASSED = 0
FAILED = 0


def report(name: str, ok: bool, detail: str = ""):
    global PASSED, FAILED
    status = "[PASS]" if ok else "[FAIL]"
    if ok:
        PASSED += 1
    else:
        FAILED += 1
    print(f"  {status}  {name}")
    if detail and not ok:
        print(f"         -> {detail}")


def test_health():
    print("\n-- Test 1: GET /health --")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        data = r.json()
        report("Status code is 200", r.status_code == 200, f"Got {r.status_code}")
        report("status == 'ok'", data.get("status") == "ok", f"Got {data}")
        report("model == 'finbert'", data.get("model") == "finbert", f"Got {data}")
    except requests.ConnectionError:
        report("Server reachable", False, "Connection refused - is sentiment_server.py running?")


def test_predict_normal():
    print("\n-- Test 2: POST /predict (normal) --")
    headlines = [
        "Apple reports record quarterly earnings, raises dividend",
        "Tesla faces SEC investigation over accounting practices",
        "Microsoft Azure revenue grows 35% year over year",
        "Netflix subscriber growth disappoints investors",
        "Nvidia beats estimates on strong AI chip demand",
    ]

    try:
        t0 = time.perf_counter()
        r = requests.post(
            f"{BASE_URL}/predict",
            json={"headlines": headlines},
            timeout=30,
        )
        elapsed = time.perf_counter() - t0

        report("Status code is 200", r.status_code == 200, f"Got {r.status_code}")

        data = r.json()
        preds = data.get("predictions", [])

        report("'predictions' key exists", "predictions" in data)
        report("Correct number of predictions", len(preds) == len(headlines),
               f"Expected {len(headlines)}, got {len(preds)}")
        report("'model_name' == 'finbert'", data.get("model_name") == "finbert",
               f"Got {data.get('model_name')}")
        report("'model_version' == '1.0'", data.get("model_version") == "1.0",
               f"Got {data.get('model_version')}")

        # Check each prediction's schema
        valid_labels = {"positive", "negative", "neutral"}
        schema_ok    = True
        label_ok     = True
        probs_ok     = True

        for p in preds:
            if not all(k in p for k in ("headline", "label", "score", "probabilities")):
                schema_ok = False
            if p.get("label") not in valid_labels:
                label_ok = False
            probs = p.get("probabilities", {})
            if not all(k in probs for k in ("positive", "neutral", "negative")):
                probs_ok = False

        report("All predictions have correct keys", schema_ok)
        report("All labels are lowercase + valid", label_ok)
        report("All probabilities have 3 keys", probs_ok)

        per_headline_ms = (elapsed * 1000) / len(headlines)
        report(
            f"Latency < 200ms/headline ({per_headline_ms:.0f}ms)",
            per_headline_ms < 200,
            f"Total {elapsed*1000:.0f}ms for {len(headlines)} headlines",
        )

        # Pretty-print predictions
        print("\n  Predictions:")
        for p in preds:
            lbl   = p["label"].upper()
            score = p["score"]
            text  = p["headline"][:60]
            print(f"    [{lbl:8s}] {score:.4f}  {text}")

    except requests.ConnectionError:
        report("Server reachable", False, "Connection refused")


def test_predict_empty():
    print("\n-- Test 3: POST /predict (empty list) --")
    try:
        r = requests.post(f"{BASE_URL}/predict", json={"headlines": []}, timeout=5)
        data = r.json()
        report("Status code is 200", r.status_code == 200, f"Got {r.status_code}")
        report("Predictions list is empty", data.get("predictions") == [])
    except requests.ConnectionError:
        report("Server reachable", False, "Connection refused")


def test_predict_bad_request():
    print("\n-- Test 4: POST /predict (missing 'headlines') --")
    try:
        r = requests.post(f"{BASE_URL}/predict", json={"text": "hello"}, timeout=5)
        report("Status code is 400", r.status_code == 400, f"Got {r.status_code}")
    except requests.ConnectionError:
        report("Server reachable", False, "Connection refused")


def main():
    print("=" * 55)
    print("  Sentiment Server - Smoke Tests")
    print(f"  Target: {BASE_URL}")
    print("=" * 55)

    test_health()
    test_predict_normal()
    test_predict_empty()
    test_predict_bad_request()

    print("\n" + "=" * 55)
    print(f"  Results:  {PASSED} passed,  {FAILED} failed")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
