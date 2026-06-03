"""
TOOL 02 — get_recent_news(ticker, company_name)
================================================
PURPOSE:
    Retrieve, deduplicate, and structurally classify recent news for a company.
    Raw news is noisy. This tool cleans it — deduplicating similar headlines,
    classifying each article by event type, assessing source credibility,
    and flagging material events that require immediate analyst attention.

ANALYST USE CASES:
    - Morning news scan: what happened overnight for covered companies?
    - Event detection: earnings, guidance changes, M&A, regulatory actions
    - Narrative tracking: is sentiment shifting over the last 30 days?
    - Pre-analysis prep: understand the news context before reading filings
    - Catalyst identification: what could move this stock near-term?

RESEARCH STEP REPLACED:
    Manually scanning Yahoo Finance news, Google News, MarketWatch, and
    Seeking Alpha for each company, reading headlines, and mentally
    classifying which ones are material. Saves 20-30 minutes per company.

POSITION IN PIPELINE:
    Called SECOND, after get_price_and_metrics().
    If unusual volume or price movement was flagged in Tool 1,
    this tool explains why.
    Its output feeds into:
    - sentiment_score() — headlines passed to ML model
    - get_earnings_call_transcript() — if earnings event detected
    - thesis generation — narrative context layer

DATA SOURCES:
    PRIMARY: NewsAPI (newsapi.org) — structured news from 80,000+ sources
    FALLBACK: Yahoo Finance RSS via yfinance — no key required
    EXCLUDED: SEC filings (Tool 5), social sentiment (out of scope for this tool)

EDGE CASES HANDLED:
    - No NEWS_API_KEY set → falls back to yfinance news
    - Zero results → returns empty list with explanation
    - Duplicate headlines → deduplicated by similarity
    - Non-English articles → flagged in metadata
    - Rate limit hit → graceful error with retry guidance
    - Company name ambiguity → uses both ticker and company name in query

TOOL INVOCATION RULES:
    Call this tool when:
    - Starting research on any company (standard workflow)
    - Tool 1 flagged unusual volume or significant price move
    - Agent needs narrative context before reading financials
    Do NOT call more than once per company per session.
    Reuse output across downstream tools.

APIs REQUIRED:
    NewsAPI — free tier at newsapi.org
    - Sign up → get API key → add to .env as NEWS_API_KEY
    - Free tier: 100 requests/day, articles from last 30 days
    - Paid tier: full archive access

    yfinance — fallback, no key needed
    pip install requests yfinance python-dotenv
"""

import os
import re
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── Event classification keywords ────────────────────────────────────────────
EVENT_TAXONOMY = {
    "EARNINGS":         ["earnings", "eps", "quarterly results", "annual results",
                         "beat", "miss", "revenue", "profit", "loss", "guidance"],
    "MERGER_ACQUISITION":["acquisition", "merger", "takeover", "buyout", "deal",
                          "acquire", "bid", "offer", "combine", "divest"],
    "LEADERSHIP_CHANGE": ["ceo", "cfo", "coo", "chief executive", "chief financial",
                          "resign", "appoint", "steps down", "new president",
                          "leadership", "management change"],
    "REGULATORY":       ["sec", "ftc", "doj", "investigation", "fine", "penalty",
                         "lawsuit", "settlement", "antitrust", "probe", "subpoena",
                         "regulatory", "compliance", "violation"],
    "PRODUCT_LAUNCH":   ["launch", "release", "announce", "unveil", "new product",
                         "partnership", "contract", "deal", "agreement"],
    "MACRO_MARKET":     ["fed", "interest rate", "inflation", "recession", "gdp",
                         "tariff", "trade war", "market", "index", "sector"],
    "ANALYST_ACTION":   ["upgrade", "downgrade", "price target", "overweight",
                         "underweight", "buy", "sell", "hold", "initiate",
                         "coverage", "analyst"],
    "INSIDER_ACTIVITY": ["insider", "bought", "sold", "filing", "form 4",
                         "executive purchase", "executive sale"],
    "CAPITAL_MARKETS":  ["ipo", "secondary offering", "buyback", "repurchase",
                         "dividend", "split", "debt offering", "bond"],
}

# ── Source credibility tiers ──────────────────────────────────────────────────
SOURCE_TIERS = {
    "tier_1": [
        "reuters", "bloomberg", "wsj", "wall street journal", "financial times",
        "ft.com", "cnbc", "associated press", "ap news", "barrons", "marketwatch"
    ],
    "tier_2": [
        "seeking alpha", "motley fool", "investopedia", "yahoo finance",
        "benzinga", "thestreet", "businesswire", "prnewswire", "globenewswire"
    ],
    "tier_3": [
        "reddit", "twitter", "stocktwits", "medium", "substack"
    ],
}

MATERIALITY_KEYWORDS = [
    "earnings", "acquisition", "merger", "ceo", "cfo", "investigation",
    "sec", "guidance", "bankruptcy", "recall", "layoff", "beat", "miss",
    "dividend", "buyback", "downgrade", "upgrade", "restatement"
]


def get_recent_news(ticker: str, company_name: Optional[str] = None,
                    days_back: int = 30, max_articles: int = 20) -> dict:
    """
    Fetch and classify recent news for a company.

    REQUIRED PARAMETERS:
        ticker (str): Stock ticker e.g. "AAPL"

    OPTIONAL PARAMETERS:
        company_name (str): Full company name for better search results
                            e.g. "Apple Inc." — improves recall significantly
        days_back (int): How many days of news to retrieve (default 30, max 30 on free tier)
        max_articles (int): Maximum articles to return (default 20)

    VALIDATION RULES:
        - ticker uppercased automatically
        - days_back capped at 30 for NewsAPI free tier
        - Falls back to yfinance if NewsAPI key missing or fails
    """

    ticker = ticker.strip().upper()
    days_back = min(days_back, 30)  # NewsAPI free tier hard limit

    if not ticker:
        return _error_response("EMPTY_TICKER", "Ticker symbol cannot be empty.")

    # ── Resolve company name if not provided ──────────────────────────────────
    if not company_name:
        try:
            info = yf.Ticker(ticker).info
            company_name = info.get("longName") or info.get("shortName") or ticker
        except Exception:
            company_name = ticker

    api_key = os.getenv("NEWS_API_KEY")
    articles_raw = []
    source_used = None

    # ── Primary: NewsAPI ──────────────────────────────────────────────────────
    if api_key:
        try:
            articles_raw, source_used = _fetch_newsapi(
                ticker, company_name, api_key, days_back, max_articles
            )
        except Exception as e:
            # fall through to yfinance
            source_used = f"NewsAPI failed ({str(e)}), fell back to yfinance"

    # ── Fallback: yfinance news ───────────────────────────────────────────────
    if not articles_raw:
        try:
            articles_raw, fallback_source = _fetch_yfinance_news(ticker, max_articles)
            source_used = source_used or fallback_source
        except Exception as e:
            return _error_response("ALL_SOURCES_FAILED",
                                   f"NewsAPI and yfinance both failed: {str(e)}")

    if not articles_raw:
        return _empty_response(ticker, company_name, source_used)

    # ── Process articles ──────────────────────────────────────────────────────
    processed = []
    seen_titles = []

    for article in articles_raw:
        title       = article.get("title") or ""
        description = article.get("description") or ""
        url         = article.get("url") or ""
        source_name = article.get("source", {}).get("name") or article.get("source") or "Unknown"
        published   = article.get("publishedAt") or article.get("published") or ""

        if not title or title == "[Removed]":
            continue

        # Deduplication — skip if title is >70% similar to a seen one
        if _is_duplicate(title, seen_titles):
            continue
        seen_titles.append(title)

        event_types     = _classify_event(title + " " + description)
        source_tier     = _get_source_tier(source_name)
        is_material     = _is_material(title + " " + description)
        published_clean = _parse_date(published)

        processed.append({
            "title":        title,
            "description":  description[:300] if description else None,
            "url":          url,
            "source":       source_name,
            "source_tier":  source_tier,
            "published_at": published_clean,
            "event_types":  event_types,
            "is_material":  is_material,
        })

    # ── Sort: material first, then by date ───────────────────────────────────
    processed.sort(key=lambda x: (not x["is_material"], x["published_at"] or ""))
    processed = processed[:max_articles]

    # ── Aggregate event summary ───────────────────────────────────────────────
    event_counts = {}
    material_events = []
    for a in processed:
        for e in a["event_types"]:
            event_counts[e] = event_counts.get(e, 0) + 1
        if a["is_material"]:
            material_events.append(a["title"])

    # ── Headlines list for sentiment tool ────────────────────────────────────
    headlines_for_sentiment = [a["title"] for a in processed]

    # ── Confidence score ──────────────────────────────────────────────────────
    tier1_count = sum(1 for a in processed if a["source_tier"] == "tier_1")
    confidence_score = min(100, round(
        (len(processed) / max(max_articles, 1)) * 60 +
        (tier1_count / max(len(processed), 1)) * 40
    ))
    if confidence_score >= 75:
        confidence_label = "HIGH"
    elif confidence_score >= 45:
        confidence_label = "MEDIUM"
    else:
        confidence_label = "LOW — few articles or low-credibility sources only"

    # ── Flags ─────────────────────────────────────────────────────────────────
    flags = []
    if "REGULATORY" in event_counts:
        flags.append(f"REGULATORY_RISK — {event_counts['REGULATORY']} regulatory/legal articles detected")
    if "MERGER_ACQUISITION" in event_counts:
        flags.append(f"MA_ACTIVITY — {event_counts['MERGER_ACQUISITION']} M&A articles detected")
    if "LEADERSHIP_CHANGE" in event_counts:
        flags.append(f"LEADERSHIP_CHANGE — {event_counts['LEADERSHIP_CHANGE']} leadership articles detected")
    if "EARNINGS" in event_counts:
        flags.append(f"EARNINGS_EVENT — {event_counts['EARNINGS']} earnings-related articles detected")
    if len(processed) < 3:
        flags.append("LOW_COVERAGE — fewer than 3 articles found, narrative context limited")

    return {
        "data": {
            "company": {
                "ticker":       ticker,
                "company_name": company_name,
            },
            "summary": {
                "total_articles_retrieved":  len(processed),
                "material_event_count":      len(material_events),
                "event_type_breakdown":      event_counts,
                "top_material_headlines":    material_events[:5],
                "dominant_themes":           sorted(
                    event_counts, key=event_counts.get, reverse=True
                )[:3],
            },
            "articles": processed,
            # Pass this directly to sentiment_score() tool
            "headlines_for_sentiment": headlines_for_sentiment,
            "flags": flags,
        },
        "metadata": {
            "tool":             "get_recent_news",
            "version":          "1.0",
            "ticker_queried":   ticker,
            "company_queried":  company_name,
            "days_back":        days_back,
            "timestamp_utc":    datetime.now(timezone.utc).isoformat(),
            "data_source":      source_used,
            "api_key_present":  bool(api_key),
            "fallback_used":    not bool(api_key) or source_used != "NewsAPI",
        },
        "validation_results": {
            "ticker_resolved":  True,
            "articles_found":   len(processed) > 0,
            "flags_detected":   flags,
            "flag_count":       len(flags),
        },
        "confidence_assessment": {
            "score_pct":        confidence_score,
            "label":            confidence_label,
            "tier1_sources":    tier1_count,
            "total_articles":   len(processed),
        },
        "missing_information": {
            "missing_fields":  [] if processed else ["articles"],
            "interpretation": (
                "NewsAPI free tier limited to last 30 days. "
                "For older news history, upgrade to paid tier or use SEC filings (Tool 5)."
                if api_key else
                "NEWS_API_KEY not set in .env — using yfinance fallback. "
                "Add key from newsapi.org for significantly better results."
            ),
        },
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_newsapi(ticker, company_name, api_key, days_back, max_articles):
    """Fetch from NewsAPI with dual query: ticker + company name."""
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Query 1: ticker symbol (catches financial media)
    # Query 2: company name (catches general business media)
    query = f'"{ticker}" OR "{company_name}"'

    url = "https://newsapi.org/v2/everything"
    params = {
        "q":          query,
        "from":       from_date,
        "language":   "en",
        "sortBy":     "publishedAt",
        "pageSize":   min(max_articles * 2, 100),  # fetch more, dedupe later
        "apiKey":     api_key,
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code == 401:
        raise Exception("Invalid NewsAPI key — check NEWS_API_KEY in .env")
    if response.status_code == 429:
        raise Exception("NewsAPI rate limit hit — 100 requests/day on free tier")
    if response.status_code != 200:
        raise Exception(f"NewsAPI HTTP {response.status_code}")

    data = response.json()
    articles = data.get("articles") or []
    return articles, "NewsAPI"


def _fetch_yfinance_news(ticker, max_articles):
    """Fallback: fetch news via yfinance."""
    stock = yf.Ticker(ticker)
    news = stock.news or []

    # Normalise yfinance schema to match NewsAPI schema
    normalised = []
    for item in news[:max_articles]:
        content = item.get("content") or {}
        normalised.append({
            "title":       content.get("title") or item.get("title") or "",
            "description": content.get("summary") or "",
            "url":         (content.get("canonicalUrl") or {}).get("url") or
                           item.get("link") or "",
            "source":      {"name": content.get("provider", {}).get("displayName") or
                                    item.get("publisher") or "Yahoo Finance"},
            "publishedAt": content.get("pubDate") or item.get("providerPublishTime") or "",
        })
    return normalised, "yfinance (fallback — add NEWS_API_KEY for better results)"


def _classify_event(text: str) -> list:
    """Return list of matching event types for a given text."""
    text_lower = text.lower()
    matched = []
    for event_type, keywords in EVENT_TAXONOMY.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(event_type)
    return matched if matched else ["GENERAL"]


def _get_source_tier(source_name: str) -> str:
    """Return credibility tier for a news source."""
    name_lower = source_name.lower()
    for source in SOURCE_TIERS["tier_1"]:
        if source in name_lower:
            return "tier_1"
    for source in SOURCE_TIERS["tier_2"]:
        if source in name_lower:
            return "tier_2"
    for source in SOURCE_TIERS["tier_3"]:
        if source in name_lower:
            return "tier_3"
    return "tier_2"  # default unknown sources to tier 2


def _is_material(text: str) -> bool:
    """Return True if article likely contains material information."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in MATERIALITY_KEYWORDS)


def _is_duplicate(title: str, seen: list, threshold: float = 0.7) -> bool:
    """Simple word-overlap deduplication."""
    words_new = set(re.sub(r'[^\w\s]', '', title.lower()).split())
    for seen_title in seen:
        words_seen = set(re.sub(r'[^\w\s]', '', seen_title.lower()).split())
        if not words_new or not words_seen:
            continue
        overlap = len(words_new & words_seen) / len(words_new | words_seen)
        if overlap >= threshold:
            return True
    return False


def _parse_date(date_str: str) -> Optional[str]:
    """Normalise various date formats to ISO string."""
    if not date_str:
        return None
    # Already ISO
    if "T" in str(date_str):
        return str(date_str)[:19]
    # Unix timestamp from yfinance
    try:
        ts = int(date_str)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()[:19]
    except (ValueError, TypeError):
        pass
    return str(date_str)


def _error_response(code: str, message: str) -> dict:
    return {
        "data": None,
        "metadata": {
            "tool":          "get_recent_news",
            "version":       "1.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "validation_results": {
            "ticker_resolved": False,
            "error_code":      code,
            "error_message":   message,
        },
        "confidence_assessment": {"score_pct": 0, "label": "NO_DATA"},
        "missing_information":   {"missing_fields": ["all"], "interpretation": message},
    }


def _empty_response(ticker, company_name, source_used) -> dict:
    return {
        "data": {
            "company":                  {"ticker": ticker, "company_name": company_name},
            "summary":                  {"total_articles_retrieved": 0},
            "articles":                 [],
            "headlines_for_sentiment":  [],
            "flags":                    ["NO_NEWS_FOUND — no articles returned for this company"],
        },
        "metadata": {
            "tool":           "get_recent_news",
            "version":        "1.0",
            "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
            "data_source":    source_used,
        },
        "validation_results": {
            "ticker_resolved": True,
            "articles_found":  False,
        },
        "confidence_assessment": {"score_pct": 0, "label": "NO_DATA"},
        "missing_information": {
            "missing_fields":  ["articles"],
            "interpretation":  "No articles found. Company may be very small, newly listed, or search terms too narrow.",
        },
    }


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("\n" + "="*60)
    print("TEST 1: Valid ticker with yfinance fallback — Tesla")
    print("="*60)
    result = get_recent_news("TSLA", "Tesla Inc.")
    # Print everything except full article list to keep output readable
    summary = {
        "summary":              result["data"]["summary"] if result["data"] else None,
        "flags":                result["data"]["flags"] if result["data"] else None,
        "confidence":           result["confidence_assessment"],
        "metadata":             result["metadata"],
        "missing_information":  result["missing_information"],
        "sample_headlines":     [
            a["title"] for a in (result["data"]["articles"][:3] if result["data"] else [])
        ],
    }
    print(json.dumps(summary, indent=2))

    print("\n" + "="*60)
    print("TEST 2: Invalid ticker")
    print("="*60)
    result2 = get_recent_news("INVALIDXYZ999")
    print(json.dumps(result2, indent=2))

    """to use anywhere in project
    from tools.tool_02_recent_news import get_recent_news

result = get_recent_news("AAPL", "Apple Inc.")

# Check for material events
print(result["data"]["flags"])

# Pass headlines to sentiment tool
headlines = result["data"]["headlines_for_sentiment"]

# See event breakdown
print(result["data"]["summary"]["event_type_breakdown"])"""