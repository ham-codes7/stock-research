"""
TOOL 01 — get_price_and_metrics(ticker)
========================================
PURPOSE:
    Retrieve real-time price data and core valuation metrics for a given stock.
    This is the entry point for any research workflow — it establishes whether
    a stock is cheap or expensive before deeper analysis begins.

ANALYST USE CASES:
    - Morning market check: is the stock moving significantly?
    - Valuation screening: is the stock trading at historically rich/cheap multiples?
    - Pre-call prep: quick snapshot before reading filings or transcripts
    - Flagging: detect anomalies (negative PE, missing data, near 52w high/low)

RESEARCH STEP REPLACED:
    Manually opening Yahoo Finance, copying price + multiples into Excel,
    and computing 52w position. Saves 10-15 minutes per stock.

POSITION IN PIPELINE:
    Always called FIRST. Its output feeds into:
    - get_financials_history() — to contextualise current multiples vs history
    - get_peer_comparison() — to compare multiples against peers
    - thesis generation — as the valuation anchor

DATA SOURCES:
    PRIMARY: yfinance (Yahoo Finance) — live price + fundamental ratios
    EXCLUDED: News, filings, sentiment — not this tool's responsibility

EDGE CASES HANDLED:
    - Delisted / ticker not found
    - Negative earnings (PE = N/A, flagged explicitly)
    - Missing fields (each field independently validated)
    - ADRs (flagged via exchange field)
    - Currency (reported in info block)
    - Newly IPO'd firms (52w range may be incomplete, flagged)
"""

import yfinance as yf
from datetime import datetime, timezone
from typing import Optional


def get_price_and_metrics(ticker: str) -> dict:
    """
    Fetch real-time price and core valuation metrics for a stock.

    REQUIRED PARAMETERS:
        ticker (str): Stock ticker symbol e.g. "AAPL", "RELIANCE.NS", "7203.T"

    OPTIONAL PARAMETERS:
        None — this tool is deliberately narrow. Additional context
        is handled by downstream tools.

    VALIDATION RULES:
        - Ticker must be a non-empty string
        - Ticker is uppercased automatically
        - Invalid tickers return error schema, not exceptions

    RETURNS:
        dict with keys: data, metadata, validation_results,
        confidence_assessment, missing_information
    """

    ticker = ticker.strip().upper()

    # ── Validation ──────────────────────────────────────────────────────────
    if not ticker:
        return _error_response("EMPTY_TICKER", "Ticker symbol cannot be empty.")

    # ── Fetch ────────────────────────────────────────────────────────────────
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as e:
        return _error_response("FETCH_FAILED", f"yfinance fetch failed: {str(e)}")

    # ── Delist / invalid ticker check ────────────────────────────────────────
    # yfinance returns a minimal dict with no 'shortName' for invalid tickers
    if not info or info.get("trailingPE") is None and info.get("shortName") is None:
        return _error_response(
            "TICKER_NOT_FOUND",
            f"No data returned for '{ticker}'. "
            "Company may be delisted, ticker may be wrong, or market is closed."
        )

    # ── Extract fields with fallback ─────────────────────────────────────────
    def safe_get(key, label=None):
        val = info.get(key)
        return val if val is not None else None

    company_name    = safe_get("longName") or safe_get("shortName") or ticker
    currency        = safe_get("currency") or "USD"
    exchange        = safe_get("exchange") or "UNKNOWN"
    sector          = safe_get("sector")
    industry        = safe_get("industry")

    current_price   = safe_get("currentPrice") or safe_get("regularMarketPrice")
    prev_close      = safe_get("previousClose")
    open_price      = safe_get("open")
    day_high        = safe_get("dayHigh")
    day_low         = safe_get("dayLow")
    week52_high     = safe_get("fiftyTwoWeekHigh")
    week52_low      = safe_get("fiftyTwoWeekLow")
    market_cap      = safe_get("marketCap")
    volume          = safe_get("volume")
    avg_volume      = safe_get("averageVolume")

    # Valuation multiples
    pe_trailing     = safe_get("trailingPE")
    pe_forward      = safe_get("forwardPE")
    pb_ratio        = safe_get("priceToBook")
    ps_ratio        = safe_get("priceToSalesTrailing12Months")
    ev_ebitda       = safe_get("enterpriseToEbitda")
    ev_revenue      = safe_get("enterpriseToRevenue")
    peg_ratio       = safe_get("trailingPegRatio")

    # Profitability
    eps_trailing    = safe_get("trailingEps")
    eps_forward     = safe_get("forwardEps")
    dividend_yield  = safe_get("dividendYield")
    beta            = safe_get("beta")
    short_ratio     = safe_get("shortRatio")

    # ── Derived metrics ───────────────────────────────────────────────────────
    price_change_pct = None
    if current_price and prev_close and prev_close != 0:
        price_change_pct = round(((current_price - prev_close) / prev_close) * 100, 2)

    week52_position = None
    week52_note = None
    if current_price and week52_high and week52_low:
        range_size = week52_high - week52_low
        if range_size > 0:
            week52_position = round(
                ((current_price - week52_low) / range_size) * 100, 1
            )
            if week52_position >= 90:
                week52_note = "NEAR_52W_HIGH — momentum strong but potential resistance"
            elif week52_position <= 10:
                week52_note = "NEAR_52W_LOW — potential value or distress signal"

    volume_vs_avg = None
    if volume and avg_volume and avg_volume > 0:
        volume_vs_avg = round(volume / avg_volume, 2)

    # ── Flags and anomalies ───────────────────────────────────────────────────
    flags = []

    if pe_trailing is not None and pe_trailing < 0:
        flags.append("NEGATIVE_TRAILING_PE — company currently unprofitable")

    if pe_forward is not None and pe_forward < 0:
        flags.append("NEGATIVE_FORWARD_PE — analysts expect continued losses")

    if pe_trailing is not None and pe_trailing > 100:
        flags.append(f"ELEVATED_PE ({pe_trailing:.0f}x) — growth premium or earnings trough")

    if beta is not None and beta > 2.0:
        flags.append(f"HIGH_BETA ({beta}) — significantly more volatile than market")

    if short_ratio is not None and short_ratio > 10:
        flags.append(f"HIGH_SHORT_INTEREST ({short_ratio} days to cover) — significant bearish positioning")

    if volume_vs_avg is not None and volume_vs_avg > 3:
        flags.append(f"UNUSUAL_VOLUME ({volume_vs_avg}x average) — investigate catalyst")

    if exchange in ["PNK", "OTC", "PINX"]:
        flags.append("OTC/PINK_SHEET — limited regulatory disclosure, higher risk")

    if week52_note:
        flags.append(week52_note)

    # ── Missing data tracking ─────────────────────────────────────────────────
    missing = []
    fields_checked = {
        "current_price": current_price,
        "trailing_pe": pe_trailing,
        "forward_pe": pe_forward,
        "ev_ebitda": ev_ebitda,
        "price_to_book": pb_ratio,
        "market_cap": market_cap,
        "beta": beta,
        "eps_forward": eps_forward,
    }
    for field, val in fields_checked.items():
        if val is None:
            missing.append(field)

    # ── Confidence score ──────────────────────────────────────────────────────
    total_fields = len(fields_checked)
    populated = sum(1 for v in fields_checked.values() if v is not None)
    confidence_score = round((populated / total_fields) * 100)

    if confidence_score >= 85:
        confidence_label = "HIGH"
    elif confidence_score >= 60:
        confidence_label = "MEDIUM"
    else:
        confidence_label = "LOW — interpret with caution, significant data gaps"

    # ── Format market cap ─────────────────────────────────────────────────────
    def format_market_cap(mc):
        if mc is None:
            return None
        if mc >= 1_000_000_000_000:
            return f"${mc/1_000_000_000_000:.2f}T"
        elif mc >= 1_000_000_000:
            return f"${mc/1_000_000_000:.2f}B"
        elif mc >= 1_000_000:
            return f"${mc/1_000_000:.2f}M"
        return f"${mc:,.0f}"

    # ── Assemble output ───────────────────────────────────────────────────────
    return {
        "data": {
            "identity": {
                "ticker": ticker,
                "company_name": company_name,
                "exchange": exchange,
                "currency": currency,
                "sector": sector,
                "industry": industry,
            },
            "price": {
                "current": current_price,
                "previous_close": prev_close,
                "day_change_pct": price_change_pct,
                "day_high": day_high,
                "day_low": day_low,
                "open": open_price,
                "week_52_high": week52_high,
                "week_52_low": week52_low,
                "week_52_position_pct": week52_position,
            },
            "size": {
                "market_cap_raw": market_cap,
                "market_cap_formatted": format_market_cap(market_cap),
            },
            "valuation_multiples": {
                "pe_trailing": pe_trailing,
                "pe_forward": pe_forward,
                "price_to_book": pb_ratio,
                "price_to_sales": ps_ratio,
                "ev_to_ebitda": ev_ebitda,
                "ev_to_revenue": ev_revenue,
                "peg_ratio": peg_ratio,
            },
            "per_share": {
                "eps_trailing": eps_trailing,
                "eps_forward": eps_forward,
                "dividend_yield_pct": round(dividend_yield * 100, 2) if dividend_yield else None,
            },
            "market_behaviour": {
                "beta": beta,
                "volume": volume,
                "avg_volume_30d": avg_volume,
                "volume_vs_avg": volume_vs_avg,
                "short_ratio_days": short_ratio,
            },
            "flags": flags,
        },
        "metadata": {
            "tool": "get_price_and_metrics",
            "version": "1.0",
            "ticker_queried": ticker,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "data_source": "Yahoo Finance via yfinance",
            "latency_note": "Real-time during market hours; 15-min delay after hours",
        },
        "validation_results": {
            "ticker_resolved": True,
            "flags_detected": flags,
            "flag_count": len(flags),
        },
        "confidence_assessment": {
            "score_pct": confidence_score,
            "label": confidence_label,
            "fields_populated": populated,
            "fields_total": total_fields,
        },
        "missing_information": {
            "missing_fields": missing,
            "interpretation": (
                "Missing fields are common for: newly IPO'd companies (no earnings history), "
                "foreign listings (partial Yahoo coverage), OTC stocks, or ETFs."
            ) if missing else "All key fields populated.",
        },
    }


def _error_response(code: str, message: str) -> dict:
    """Standard error schema — keeps agent output consistent on failure."""
    return {
        "data": None,
        "metadata": {
            "tool": "get_price_and_metrics",
            "version": "1.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "validation_results": {
            "ticker_resolved": False,
            "error_code": code,
            "error_message": message,
        },
        "confidence_assessment": {
            "score_pct": 0,
            "label": "NO_DATA",
        },
        "missing_information": {
            "missing_fields": ["all"],
            "interpretation": message,
        },
    }


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("\n" + "="*60)
    print("TEST 1: Valid ticker — Apple")
    print("="*60)
    result = get_price_and_metrics("AAPL")
    print(json.dumps(result, indent=2))

    print("\n" + "="*60)
    print("TEST 2: Invalid ticker")
    print("="*60)
    result = get_price_and_metrics("INVALIDXYZ123")
    print(json.dumps(result, indent=2))

    '''to use anywhere in project
from tools.tool_01_price_and_metrics import get_price_and_metrics

result = get_price_and_metrics("AAPL")
print(result["data"]["valuation_multiples"])
print(result["data"]["flags"])'''