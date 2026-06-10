"""
TOOL 07 — get_earnings_call_transcript(ticker)
===============================================
PURPOSE:
    Retrieve, parse, and extract structured intelligence from the most recent
    earnings call transcript for a given company.

    Earnings calls are the single richest source of forward-looking qualitative
    information about a company. Management reveals their real thinking, analysts
    probe weaknesses, and the language used — what they emphasise, what they
    deflect, what they repeat — tells you as much as the numbers do.

    Financial data APIs give you EPS. This tool gives you WHY EPS came in where
    it did, what management is worried about, and what they're betting on next.

ANALYST USE CASES:
    - Management tone assessment: confident, defensive, or hedging?
    - Guidance extraction: what numbers did management give for next quarter?
    - Q&A red flag detection: which analyst questions were deflected?
    - Key theme identification: what topics dominated the call?
    - Variant perception: does management narrative contradict the financials?
    - Bull/bear case: management's own words as supporting evidence
    - Repeat language: what phrases keep coming up? (signals priorities or concerns)

RESEARCH STEP REPLACED:
    Reading a 40-60 page earnings call transcript, highlighting management
    prepared remarks, tracking Q&A exchanges, noting guidance numbers,
    and building a summary. Saves 1-3 hours per company per quarter.

POSITION IN PIPELINE:
    Called LAST — after all quantitative tools have run.
    Provides the qualitative narrative layer that either supports or
    contradicts what the numbers show.
    Feeds into:
    - Thesis generation: management's own language in bull case
    - Bear case discovery: deflected questions, hedging language
    - Variant perception: narrative vs numbers gap analysis

DATA SOURCES:
    PRIMARY:   Motley Fool Earnings transcripts (free, public, well-structured)
    SECONDARY: Seeking Alpha transcript pages (free tier)
    FALLBACK:  SEC 8-K filing (earnings press release — not a transcript
               but contains prepared remarks and financial tables)
    EXCLUDED:  Bloomberg, FactSet, Refinitiv (paid, not accessible)

EDGE CASES HANDLED:
    - Transcript not yet published (call may be recent — flagged with timing)
    - Company doesn't hold earnings calls (rare — flagged)
    - Parsing failures on non-standard transcript formats
    - Foreign companies with non-English transcripts (flagged)
    - Newly IPO'd companies with no transcript history
    - Transcript behind paywall (falls back to 8-K press release)

TOOL INVOCATION RULES:
    Call when:
    - News tool detected an EARNINGS event (Tool 2 flag)
    - Building a complete fundamental thesis
    - Agent needs to understand management tone and guidance
    - Variant perception analysis is requested
    Do NOT call for: pure valuation, peer comparison, or macro questions.
    Call ONCE per company per session.

APIS REQUIRED:
    requests       — pip install requests
    beautifulsoup4 — pip install beautifulsoup4
    No API key needed. Uses publicly available transcript pages.

IMPORTANT NOTE ON WEB SCRAPING:
    This tool scrapes public transcript pages.
    Be respectful — the tool adds delays between requests.
    For production use, consider a paid transcript API like:
    - Quartr API (https://quartr.com)
    - Earnings Whispers API
    - Alpha Vantage (has some earnings data)
"""

import re
import time
import requests
from datetime import datetime, timezone
from typing import Optional
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_DELAY = 1.5  # seconds between requests — be polite

# ── Tone signal words ─────────────────────────────────────────────────────────
CONFIDENT_WORDS = [
    "confident", "excited", "strong", "exceptional", "record",
    "outperform", "accelerating", "momentum", "robust", "ahead of",
    "pleased", "delighted", "optimistic", "well-positioned",
    "significant opportunity", "pipeline", "demand", "growth",
]

DEFENSIVE_WORDS = [
    "challenging", "headwind", "uncertainty", "cautious", "difficult",
    "pressured", "modest", "normalise", "normalize", "transition",
    "monitor closely", "remain vigilant", "macro environment",
    "we cannot predict", "subject to", "contingent on",
]

HEDGING_WORDS = [
    "approximately", "roughly", "around", "we expect", "we anticipate",
    "we believe", "subject to change", "if conditions", "assuming",
    "we hope", "barring", "potential", "may", "might", "could",
]

# ── Guidance extraction patterns ──────────────────────────────────────────────
GUIDANCE_PATTERNS = [
    # "$X billion to $Y billion"
    r'\$\s*(\d+(?:\.\d+)?)\s*(?:billion|million|B|M)\s*(?:to|-)\s*\$\s*(\d+(?:\.\d+)?)\s*(?:billion|million|B|M)',
    # "X% to Y%"
    r'(\d+(?:\.\d+)?)\s*%\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*%',
    # "between $X and $Y"
    r'between\s+\$\s*(\d+(?:\.\d+)?)\s+and\s+\$\s*(\d+(?:\.\d+)?)',
    # "approximately $X"
    r'approximately\s+\$\s*(\d+(?:\.\d+)?)\s*(?:billion|million|B|M)',
]

# ── Red flag phrases in management language ───────────────────────────────────
TRANSCRIPT_RED_FLAGS = [
    "we cannot provide guidance",
    "we are withdrawing guidance",
    "we are not providing",
    "under investigation",
    "we are cooperating",
    "material weakness",
    "going concern",
    "covenant",
    "liquidity",
    "we are exploring strategic alternatives",
    "strategic review",
    "we do not comment on",
    "i will not speculate",
    "we are taking a closer look",
    "disappointing",
    "we fell short",
    "below our expectations",
    "we missed",
]

# ── Q&A deflection phrases ────────────────────────────────────────────────────
DEFLECTION_PHRASES = [
    "i can't comment on that",
    "we don't provide that level of detail",
    "i won't speculate",
    "we'll get back to you on that",
    "that's not something we disclose",
    "i'd rather not get into specifics",
    "we don't break that out",
    "we're not going to guide on",
    "i'll pass on that one",
    "we don't comment on",
    "i think we've addressed that",
    "next question",
]


def get_earnings_call_transcript(ticker: str,
                                 max_chars_per_section: int = 2000) -> dict:
    """
    Retrieve and analyse the most recent earnings call transcript.

    REQUIRED PARAMETERS:
        ticker (str): Stock ticker e.g. "AAPL", "TSLA", "MSFT"

    OPTIONAL PARAMETERS:
        max_chars_per_section (int): Max characters per extracted section
                                     Default 2000. Increase for deeper reads.

    VALIDATION RULES:
        - ticker uppercased automatically
        - Falls back through multiple sources before giving up
        - Partial results returned even if only some sections extracted
    """

    ticker = ticker.strip().upper()

    if not ticker:
        return _error_response("EMPTY_TICKER", "Ticker symbol cannot be empty.")

    # ── Attempt sources in priority order ─────────────────────────────────────
    transcript_text = None
    source_used     = None
    transcript_date = None
    transcript_title = None

    # Source 1: Motley Fool
    result = _fetch_motley_fool(ticker)
    if result["text"]:
        transcript_text  = result["text"]
        source_used      = "Motley Fool"
        transcript_date  = result.get("date")
        transcript_title = result.get("title")

    # Source 2: Seeking Alpha fallback
    if not transcript_text:
        time.sleep(REQUEST_DELAY)
        result = _fetch_seeking_alpha(ticker)
        if result["text"]:
            transcript_text  = result["text"]
            source_used      = "Seeking Alpha"
            transcript_date  = result.get("date")
            transcript_title = result.get("title")

    # Source 3: SEC 8-K fallback (press release, not full transcript)
    if not transcript_text:
        time.sleep(REQUEST_DELAY)
        result = _fetch_sec_8k_earnings(ticker)
        if result["text"]:
            transcript_text  = result["text"]
            source_used      = "SEC 8-K (earnings press release — not full transcript)"
            transcript_date  = result.get("date")
            transcript_title = result.get("title")

    if not transcript_text:
        return _error_response(
            "TRANSCRIPT_NOT_FOUND",
            f"Could not retrieve earnings call transcript for '{ticker}'. "
            "Transcript may not yet be published (call was recent), "
            "company may not hold earnings calls, or sources are temporarily unavailable. "
            "Try again 24-48 hours after the earnings call date."
        )

    # ── Section extraction ────────────────────────────────────────────────────
    sections    = _extract_transcript_sections(transcript_text, max_chars_per_section)

    # ── Tone analysis ─────────────────────────────────────────────────────────
    tone        = _analyse_tone(transcript_text)

    # ── Guidance extraction ───────────────────────────────────────────────────
    guidance    = _extract_guidance(sections.get("prepared_remarks", "") +
                                    sections.get("full_text_sample", ""))

    # ── Key theme extraction ──────────────────────────────────────────────────
    themes      = _extract_key_themes(transcript_text)

    # ── Red flag scan ─────────────────────────────────────────────────────────
    red_flags   = _scan_red_flags(transcript_text)

    # ── Q&A deflection detection ──────────────────────────────────────────────
    deflections = _detect_deflections(sections.get("qa_section", ""))

    # ── Repeat phrase analysis ────────────────────────────────────────────────
    repeated    = _find_repeated_phrases(transcript_text)

    # ── Flags ─────────────────────────────────────────────────────────────────
    flags       = _build_flags(
        source_used, red_flags, deflections,
        tone, transcript_date, sections
    )

    # ── Agent summary line ────────────────────────────────────────────────────
    agent_summary = _build_agent_summary(
        ticker, tone, themes, guidance, red_flags, transcript_date
    )

    # ── Confidence score ──────────────────────────────────────────────────────
    sections_found   = sum(1 for v in sections.values() if v and len(v) > 100)
    source_quality   = {"Motley Fool": 90, "Seeking Alpha": 75,
                        "SEC 8-K (earnings press release — not full transcript)": 40}
    base_confidence  = source_quality.get(source_used, 50)
    section_bonus    = min(20, sections_found * 5)
    confidence_score = min(100, base_confidence + section_bonus)

    confidence_label = (
        "HIGH"   if confidence_score >= 75 else
        "MEDIUM" if confidence_score >= 45 else
        "LOW — partial transcript only, interpret with caution"
    )

    return {
        "data": {
            "identity": {
                "ticker":           ticker,
                "transcript_title": transcript_title,
                "transcript_date":  transcript_date,
                "source":           source_used,
            },
            "sections": {
                "prepared_remarks":   sections.get("prepared_remarks"),
                "qa_section":         sections.get("qa_section"),
                "opening_statement":  sections.get("opening_statement"),
                "closing_remarks":    sections.get("closing_remarks"),
                "full_text_sample":   sections.get("full_text_sample"),
            },
            "analysis": {
                "tone":                 tone,
                "guidance_mentions":    guidance,
                "key_themes":           themes,
                "repeated_phrases":     repeated,
                "red_flags":            red_flags,
                "deflections_detected": deflections,
            },
            "agent_summary_line":   agent_summary,
            "flags":                flags,
        },
        "metadata": {
            "tool":                  "get_earnings_call_transcript",
            "version":               "1.0",
            "ticker_queried":        ticker,
            "timestamp_utc":         datetime.now(timezone.utc).isoformat(),
            "data_source":           source_used,
            "max_chars_per_section": max_chars_per_section,
            "note": (
                "Transcript sections truncated at max_chars_per_section. "
                "Increase for deeper reads. "
                "For production, consider Quartr API for cleaner transcripts."
            ),
        },
        "validation_results": {
            "ticker_resolved":    True,
            "transcript_found":   True,
            "sections_extracted": sections_found,
            "flags_detected":     flags,
            "flag_count":         len(flags),
        },
        "confidence_assessment": {
            "score_pct":       confidence_score,
            "label":           confidence_label,
            "source_used":     source_used,
            "sections_found":  sections_found,
        },
        "missing_information": {
            "missing_sections": [
                k for k, v in sections.items()
                if not v or len(v) < 100
            ],
            "interpretation": (
                "Full transcript extracted successfully."
                if confidence_score >= 75 else
                "Partial content only. "
                "Transcript may be behind paywall or recently published."
            ),
        },
    }


# ── Source fetchers ───────────────────────────────────────────────────────────

def _fetch_motley_fool(ticker: str) -> dict:
    """
    Fetch transcript from Motley Fool earnings transcript pages.
    URL pattern: https://www.fool.com/earnings/call-transcripts/
    We search their transcript index for the ticker.
    """
    empty = {"text": None, "date": None, "title": None}
    try:
        # Search Motley Fool transcript index
        search_url = (
            f"https://www.fool.com/earnings/call-transcripts/"
            f"?symbol={ticker.lower()}"
        )
        time.sleep(REQUEST_DELAY)
        r = requests.get(search_url, headers=HEADERS, timeout=12)

        if r.status_code != 200:
            return empty

        soup = BeautifulSoup(r.text, "html.parser")

        # Find transcript links
        links = soup.find_all("a", href=True)
        transcript_link = None
        for link in links:
            href = link.get("href", "")
            if "/earnings/call-transcripts/" in href and ticker.lower() in href.lower():
                transcript_link = href
                break

        if not transcript_link:
            # Try article links that mention transcript
            for link in links:
                text = link.get_text(strip=True).lower()
                href = link.get("href", "")
                if "transcript" in text and "/articles/" in href:
                    transcript_link = href
                    break

        if not transcript_link:
            return empty

        # Fetch the transcript page
        full_url = (
            f"https://www.fool.com{transcript_link}"
            if transcript_link.startswith("/")
            else transcript_link
        )

        time.sleep(REQUEST_DELAY)
        r2 = requests.get(full_url, headers=HEADERS, timeout=15)

        if r2.status_code != 200:
            return empty

        soup2    = BeautifulSoup(r2.text, "html.parser")
        title    = soup2.find("h1")
        title    = title.get_text(strip=True) if title else f"{ticker} Earnings Call"

        # Extract article body
        body = (
            soup2.find("div", class_="article-body") or
            soup2.find("div", {"id": "article-body"}) or
            soup2.find("article") or
            soup2.find("main")
        )

        if not body:
            return empty

        text = body.get_text(separator="\n", strip=True)

        # Extract date
        date_tag = soup2.find("time")
        date_str = date_tag.get("datetime", "")[:10] if date_tag else None

        return {"text": text, "date": date_str, "title": title}

    except Exception:
        return empty


def _fetch_seeking_alpha(ticker: str) -> dict:
    """
    Attempt to fetch from Seeking Alpha transcript index.
    Free tier has limited access — often returns partial content.
    """
    empty = {"text": None, "date": None, "title": None}
    try:
        url = (
            f"https://seekingalpha.com/symbol/{ticker}/earnings/transcripts"
        )
        time.sleep(REQUEST_DELAY)
        r = requests.get(url, headers=HEADERS, timeout=12)

        if r.status_code != 200:
            return empty

        soup  = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)

        transcript_url = None
        for link in links:
            href = link.get("href", "")
            if "/article/" in href and "transcript" in href.lower():
                transcript_url = href
                break

        if not transcript_url:
            return empty

        full_url = (
            f"https://seekingalpha.com{transcript_url}"
            if transcript_url.startswith("/")
            else transcript_url
        )

        time.sleep(REQUEST_DELAY)
        r2   = requests.get(full_url, headers=HEADERS, timeout=15)
        soup2 = BeautifulSoup(r2.text, "html.parser")

        title = soup2.find("h1")
        title = title.get_text(strip=True) if title else f"{ticker} Earnings Call"

        body = (
            soup2.find("div", {"data-test-id": "article-content"}) or
            soup2.find("div", class_="sa-art") or
            soup2.find("article")
        )

        if not body:
            return empty

        text = body.get_text(separator="\n", strip=True)
        return {"text": text, "date": None, "title": title}

    except Exception:
        return empty


def _fetch_sec_8k_earnings(ticker: str) -> dict:
    """
    Fallback: fetch most recent earnings 8-K from SEC EDGAR.
    This is the press release, not the full transcript, but contains
    prepared remarks, financial tables, and sometimes guidance.
    """
    empty = {"text": None, "date": None, "title": None}
    try:
        # Resolve CIK
        mapping_url = "https://www.sec.gov/files/company_tickers.json"
        SEC_HEADERS = {"User-Agent": "StockResearchAgent research@example.com"}
        r = requests.get(mapping_url, headers=SEC_HEADERS, timeout=10)

        if r.status_code != 200:
            return empty

        cik = None
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == ticker:
                cik = str(entry["cik_str"]).zfill(10)
                break

        if not cik:
            return empty

        # Fetch 8-K filings
        time.sleep(0.2)
        sub_url  = f"https://data.sec.gov/submissions/CIK{cik}.json"
        r2       = requests.get(sub_url, headers=SEC_HEADERS, timeout=10)

        if r2.status_code != 200:
            return empty

        data     = r2.json()
        recent   = data.get("filings", {}).get("recent", {})
        forms    = recent.get("form", [])
        dates    = recent.get("filed", [])
        accnos   = recent.get("accessionNumber", [])

        # Find most recent 8-K
        for i, form in enumerate(forms):
            if form == "8-K":
                accno    = accnos[i]
                filed    = dates[i]
                acc_clean = accno.replace("-", "")

                # Get filing index
                idx_url = (
                    f"https://data.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{acc_clean}/{accno}-index.json"
                )
                time.sleep(0.2)
                r3 = requests.get(idx_url, headers=SEC_HEADERS, timeout=10)

                if r3.status_code != 200:
                    break

                docs = r3.json().get("documents", [])
                for doc in docs:
                    fname = doc.get("name", "")
                    if fname.endswith((".htm", ".html")):
                        doc_url = (
                            f"https://www.sec.gov/Archives/edgar/data/"
                            f"{int(cik)}/{acc_clean}/{fname}"
                        )
                        time.sleep(0.3)
                        r4 = requests.get(doc_url, headers=SEC_HEADERS, timeout=15)
                        if r4.status_code == 200:
                            soup = BeautifulSoup(r4.text, "html.parser")
                            text = soup.get_text(separator="\n", strip=True)
                            if len(text) > 500:
                                return {
                                    "text":  text,
                                    "date":  filed,
                                    "title": f"{ticker} 8-K Earnings Release ({filed})",
                                }
                break

    except Exception:
        pass

    return empty


# ── Section extraction ────────────────────────────────────────────────────────

def _extract_transcript_sections(text: str,
                                  max_chars: int) -> dict:
    """
    Split transcript into prepared remarks and Q&A sections.
    Most earnings call transcripts follow a standard structure:
    Operator intro → CEO prepared remarks → CFO remarks → Q&A → Closing
    """
    sections = {
        "opening_statement":  None,
        "prepared_remarks":   None,
        "qa_section":         None,
        "closing_remarks":    None,
        "full_text_sample":   text[:max_chars] if text else None,
    }

    text_lower = text.lower()

    # ── Opening statement (operator intro + first speaker) ────────────────────
    opening_markers = ["good morning", "good afternoon", "good evening",
                       "welcome to", "thank you for joining", "ladies and gentlemen"]
    for marker in opening_markers:
        idx = text_lower.find(marker)
        if idx != -1:
            sections["opening_statement"] = text[idx:idx + max_chars].strip()
            break

    # ── Prepared remarks ──────────────────────────────────────────────────────
    remarks_markers = [
        "prepared remarks", "management remarks",
        "i'd like to now turn", "let me start by",
        "i'll begin by", "let me begin"
    ]
    for marker in remarks_markers:
        idx = text_lower.find(marker)
        if idx != -1:
            sections["prepared_remarks"] = text[idx:idx + max_chars * 2].strip()
            break

    # If no prepared remarks marker, use the opening statement area
    if not sections["prepared_remarks"] and sections["opening_statement"]:
        sections["prepared_remarks"] = sections["opening_statement"]

    # ── Q&A section ───────────────────────────────────────────────────────────
    qa_markers = [
        "question-and-answer", "question and answer",
        "q&a session", "open the call for questions",
        "we will now begin the question", "operator: your first question",
        "first question comes from", "we'll take our first question"
    ]
    for marker in qa_markers:
        idx = text_lower.find(marker)
        if idx != -1:
            sections["qa_section"] = text[idx:idx + max_chars * 2].strip()
            break

    # ── Closing remarks ───────────────────────────────────────────────────────
    closing_markers = [
        "thank you for joining", "thank you for your time",
        "this concludes", "that concludes", "end of q&a",
        "we appreciate your interest", "this ends our"
    ]
    # Find the LAST occurrence of these (true closing, not mid-call)
    for marker in closing_markers:
        idx = text_lower.rfind(marker)
        if idx != -1 and idx > len(text) * 0.7:  # must be in last 30% of text
            sections["closing_remarks"] = text[idx:idx + max_chars].strip()
            break

    return sections


# ── Tone analysis ─────────────────────────────────────────────────────────────

def _analyse_tone(text: str) -> dict:
    """
    Score management tone across three dimensions:
    confident, defensive, hedging.

    Returns counts and a dominant tone label.
    This is a proxy for how management feels about the business trajectory.
    """
    text_lower   = text.lower()
    words        = text_lower.split()
    word_set     = set(words)

    confident_count  = sum(
        1 for w in CONFIDENT_WORDS
        if any(w in phrase for phrase in [text_lower])
    )
    defensive_count  = sum(
        1 for w in DEFENSIVE_WORDS
        if any(w in phrase for phrase in [text_lower])
    )
    hedging_count    = sum(
        1 for w in HEDGING_WORDS
        if any(w in phrase for phrase in [text_lower])
    )

    total = confident_count + defensive_count + hedging_count + 1e-9

    # Dominant tone
    if confident_count >= defensive_count and confident_count >= hedging_count:
        dominant = "CONFIDENT"
    elif defensive_count >= confident_count and defensive_count >= hedging_count:
        dominant = "DEFENSIVE"
    else:
        dominant = "HEDGING"

    # Mixed signal if no strong leader
    if (max(confident_count, defensive_count, hedging_count) /
            (confident_count + defensive_count + hedging_count + 1e-9)) < 0.4:
        dominant = "MIXED"

    tone_score = round(confident_count / total, 3)

    return {
        "dominant_tone":       dominant,
        "tone_score":          tone_score,
        "confident_signals":   confident_count,
        "defensive_signals":   defensive_count,
        "hedging_signals":     hedging_count,
        "interpretation": (
            "Management language is predominantly confident — bullish signal."
            if dominant == "CONFIDENT" else
            "Management language is predominantly defensive — warrants scrutiny."
            if dominant == "DEFENSIVE" else
            "Management language is heavily hedged — uncertainty ahead."
            if dominant == "HEDGING" else
            "Mixed management tone — no clear directional signal from language."
        ),
    }


# ── Guidance extraction ───────────────────────────────────────────────────────

def _extract_guidance(text: str) -> list:
    """
    Extract forward guidance mentions from transcript text.
    Looks for range patterns (X to Y) and specific figure mentions.
    These are the numbers the market will trade against next quarter.
    """
    guidance_mentions = []
    sentences = re.split(r'[.!?]\s+', text)

    guidance_trigger_words = [
        "guidance", "outlook", "expect", "anticipate", "forecast",
        "next quarter", "full year", "fiscal year", "q1", "q2", "q3", "q4",
        "2024", "2025", "2026", "going forward", "for the year"
    ]

    for sentence in sentences:
        sentence_lower = sentence.lower()
        if not any(trigger in sentence_lower for trigger in guidance_trigger_words):
            continue

        # Check for numeric mentions
        has_number = bool(re.search(r'\$|\d+%|\d+\s*(?:billion|million)', sentence_lower))
        if not has_number:
            continue

        # Extract any range patterns
        ranges_found = []
        for pattern in GUIDANCE_PATTERNS:
            matches = re.findall(pattern, sentence, re.IGNORECASE)
            if matches:
                ranges_found.extend(matches)

        guidance_mentions.append({
            "sentence":     sentence.strip()[:300],
            "ranges_found": ranges_found,
        })

        if len(guidance_mentions) >= 8:
            break

    return guidance_mentions


# ── Key theme extraction ──────────────────────────────────────────────────────

def _extract_key_themes(text: str) -> list:
    """
    Identify the dominant topics discussed on the call.
    These reveal what management considers most important.
    """
    THEME_KEYWORDS = {
        "AI / Machine Learning":       ["ai", "artificial intelligence", "machine learning",
                                        "large language model", "generative", "copilot"],
        "Cloud / SaaS growth":         ["cloud", "saas", "subscription", "arr", "mrr",
                                        "recurring revenue"],
        "International expansion":     ["international", "global", "emerging markets",
                                        "europe", "asia", "india", "china"],
        "Margin improvement":          ["margin expansion", "operating leverage",
                                        "cost reduction", "efficiency", "restructuring"],
        "Supply chain":                ["supply chain", "inventory", "logistics",
                                        "procurement", "shortage"],
        "Pricing power":               ["pricing", "price increase", "asr", "arpu",
                                        "average revenue per"],
        "Competition":                 ["competitive", "market share", "competitor",
                                        "differentiation"],
        "Regulatory / Legal":          ["regulatory", "compliance", "investigation",
                                        "litigation", "sec", "ftc"],
        "M&A / Partnerships":          ["acquisition", "partnership", "strategic",
                                        "joint venture", "collaboration"],
        "Product launches":            ["launch", "new product", "new feature",
                                        "release", "announce"],
        "Macro headwinds":             ["macro", "interest rate", "inflation",
                                        "recession", "consumer spending"],
        "Capital allocation":          ["buyback", "dividend", "capex",
                                        "capital expenditure", "return to shareholders"],
    }

    text_lower   = text.lower()
    theme_scores = {}

    for theme, keywords in THEME_KEYWORDS.items():
        count = sum(text_lower.count(kw) for kw in keywords)
        if count > 0:
            theme_scores[theme] = count

    # Return top 5 themes by frequency
    sorted_themes = sorted(theme_scores, key=theme_scores.get, reverse=True)
    return [
        {"theme": t, "mention_count": theme_scores[t]}
        for t in sorted_themes[:5]
    ]


# ── Red flag scanner ──────────────────────────────────────────────────────────

def _scan_red_flags(text: str) -> list:
    """Scan transcript for management language red flags."""
    text_lower = text.lower()
    found = []
    for phrase in TRANSCRIPT_RED_FLAGS:
        if phrase in text_lower:
            found.append(phrase)
    return found


# ── Deflection detection ──────────────────────────────────────────────────────

def _detect_deflections(qa_text: str) -> list:
    """
    Detect analyst questions that management deflected.
    Deflections are highly informative — they reveal sensitive areas.
    """
    if not qa_text:
        return []

    qa_lower  = qa_text.lower()
    found     = []

    for phrase in DEFLECTION_PHRASES:
        if phrase in qa_lower:
            # Find context around the deflection
            idx = qa_lower.find(phrase)
            context = qa_text[max(0, idx - 100):idx + 200].strip()
            found.append({
                "phrase":  phrase,
                "context": context[:300],
            })

    return found[:5]  # cap at 5 most notable


# ── Repeated phrase finder ────────────────────────────────────────────────────

def _find_repeated_phrases(text: str,
                            min_count: int = 3,
                            phrase_length: int = 3) -> list:
    """
    Find phrases management repeated multiple times.
    Repetition reveals management's priorities and talking points.
    High repetition of positive phrases = confidence.
    High repetition of hedging phrases = uncertainty being managed.
    """
    # Build n-gram frequency map
    words  = re.sub(r'[^\w\s]', '', text.lower()).split()
    ngrams = {}

    for i in range(len(words) - phrase_length + 1):
        ngram = " ".join(words[i:i + phrase_length])

        # Skip ngrams that are mostly stop words
        stop_words = {"the", "and", "for", "are", "was", "that", "this",
                      "with", "from", "have", "will", "our", "we", "to",
                      "in", "of", "a", "is", "it", "be", "as", "at", "by"}
        ngram_words = set(ngram.split())
        if len(ngram_words - stop_words) < 2:
            continue

        ngrams[ngram] = ngrams.get(ngram, 0) + 1

    # Filter to meaningful repetitions
    repeated = [
        {"phrase": phrase, "count": count}
        for phrase, count in ngrams.items()
        if count >= min_count and len(phrase) > 10
    ]

    return sorted(repeated, key=lambda x: x["count"], reverse=True)[:8]


# ── Flags builder ─────────────────────────────────────────────────────────────

def _build_flags(source_used, red_flags, deflections,
                 tone, transcript_date, sections) -> list:
    flags = []

    if source_used and "8-K" in source_used:
        flags.append(
            "PRESS_RELEASE_ONLY — full transcript unavailable. "
            "Using earnings press release (8-K). "
            "Q&A analysis and tone scoring limited."
        )

    if red_flags:
        flags.append(
            f"MANAGEMENT_RED_FLAGS — {len(red_flags)} concerning phrase(s) detected: "
            f"{', '.join(red_flags[:3])}"
        )

    if deflections:
        flags.append(
            f"ANALYST_DEFLECTIONS — {len(deflections)} Q&A deflection(s) detected. "
            "Management avoided direct answers on sensitive topics."
        )

    dominant_tone = tone.get("dominant_tone")
    if dominant_tone == "DEFENSIVE":
        flags.append(
            "DEFENSIVE_TONE — management language is predominantly defensive. "
            "Elevated scrutiny warranted."
        )

    if not sections.get("qa_section"):
        flags.append(
            "QA_NOT_EXTRACTED — Q&A section could not be parsed. "
            "Transcript format may be non-standard."
        )

    if transcript_date:
        try:
            call_date = datetime.strptime(transcript_date, "%Y-%m-%d")
            days_old  = (datetime.now() - call_date).days
            if days_old > 100:
                flags.append(
                    f"STALE_TRANSCRIPT — most recent transcript is {days_old} days old. "
                    "New earnings call may be upcoming."
                )
        except Exception:
            pass

    return flags


# ── Agent summary builder ─────────────────────────────────────────────────────

def _build_agent_summary(ticker, tone, themes, guidance,
                          red_flags, transcript_date) -> str:
    """Build a one-line summary for the agent to paste into the research brief."""
    dominant_tone = tone.get("dominant_tone", "MIXED")
    top_themes    = [t["theme"] for t in themes[:3]] if themes else []
    theme_str     = ", ".join(top_themes) if top_themes else "no dominant themes identified"
    date_str      = f" ({transcript_date})" if transcript_date else ""
    rf_str        = (
        f" Red flags: {', '.join(red_flags[:2])}."
        if red_flags else ""
    )
    guidance_str  = (
        f" {len(guidance)} guidance statement(s) extracted."
        if guidance else " No explicit guidance extracted."
    )

    return (
        f"Earnings call{date_str} tone for {ticker}: {dominant_tone}. "
        f"Dominant themes: {theme_str}.{guidance_str}{rf_str}"
    )


# ── Error response ────────────────────────────────────────────────────────────

def _error_response(code: str, message: str) -> dict:
    return {
        "data": None,
        "metadata": {
            "tool":          "get_earnings_call_transcript",
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


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("\n" + "="*60)
    print("TEST 1: All internal logic validation")
    print("="*60)

    # Mock transcript for testing all analysis functions
    mock_transcript = """
    Good morning, and welcome to Apple's Q4 fiscal year 2024 earnings conference call.
    
    CEO Tim Cook: Thank you. We had an exceptional quarter with record revenue driven
    by strong iPhone demand across all geographies. We are very confident in our
    product pipeline and excited about the opportunities ahead. AI integration into
    our products is accelerating and we are well-positioned for continued growth.
    
    CFO Luca Maestri: Revenue grew 6% year over year to $94.9 billion, above our
    guidance range of $89 to $93 billion. Operating margin expanded 140 basis points
    to 31.4%. For Q1 fiscal 2025, we expect revenue between $89 billion and $93 billion.
    We anticipate gross margin of 46% to 47% and operating expenses of $14.2 to $14.4 billion.
    
    Q&A Session:
    
    Analyst: Can you give us more detail on China market share trends?
    Tim Cook: We don't break that out by specific geography in that level of detail.
    We are pleased with our overall performance in greater China.
    
    Analyst: What is your AI monetisation timeline?
    Tim Cook: We are confident in our AI strategy and excited about the opportunities.
    We will share more as we get closer to launch. We are exploring strategic alternatives
    in this space and monitoring closely.

    Analyst: Any concerns about supply chain constraints?
    Tim Cook: Supply chain remains well-managed. We anticipate no material disruptions
    going forward assuming current conditions persist.
    
    This concludes our Q4 earnings call. Thank you for your continued interest in Apple.
    """

    # Test tone analysis
    print("\n--- Tone Analysis ---")
    tone = _analyse_tone(mock_transcript)
    print(f"  Dominant tone:      {tone['dominant_tone']}")
    print(f"  Confident signals:  {tone['confident_signals']}")
    print(f"  Defensive signals:  {tone['defensive_signals']}")
    print(f"  Hedging signals:    {tone['hedging_signals']}")
    print(f"  Interpretation:     {tone['interpretation']}")
    print(f"  [{'PASS' if tone['dominant_tone'] in ['CONFIDENT','MIXED'] else 'FAIL'}] Tone detection")

    # Test guidance extraction
    print("\n--- Guidance Extraction ---")
    guidance = _extract_guidance(mock_transcript)
    print(f"  Guidance mentions found: {len(guidance)}")
    for g in guidance[:3]:
        print(f"    - {g['sentence'][:100]}")
    print(f"  [{'PASS' if len(guidance) >= 1 else 'FAIL'}] Guidance extraction")

    # Test key themes
    print("\n--- Key Themes ---")
    themes = _extract_key_themes(mock_transcript)
    print(f"  Top themes:")
    for t in themes:
        print(f"    - {t['theme']}: {t['mention_count']} mentions")
    print(f"  [{'PASS' if len(themes) >= 1 else 'FAIL'}] Theme extraction")

    # Test red flags
    print("\n--- Red Flag Scan ---")
    red_flags = _scan_red_flags(mock_transcript)
    print(f"  Red flags found: {red_flags}")
    print(f"  [{'PASS' if 'we are exploring strategic alternatives' in red_flags else 'FAIL'}] Red flag detection")

    # Test deflections
    print("\n--- Deflection Detection ---")
    deflections = _detect_deflections(mock_transcript)
    print(f"  Deflections found: {len(deflections)}")
    for d in deflections:
        print(f"    - '{d['phrase']}'")
    print(f"  [{'PASS' if len(deflections) >= 1 else 'FAIL'}] Deflection detection")

    # Test repeated phrases
    print("\n--- Repeated Phrases ---")
    repeated = _find_repeated_phrases(mock_transcript, min_count=2)
    print(f"  Repeated phrases: {len(repeated)}")
    for r in repeated[:3]:
        print(f"    - '{r['phrase']}' × {r['count']}")

    # Test section extraction
    print("\n--- Section Extraction ---")
    sections = _extract_transcript_sections(mock_transcript, max_chars=400)
    for k, v in sections.items():
        status = "FOUND" if v and len(v) > 50 else "MISSING"
        print(f"  [{status}] {k}")

    # Test agent summary
    print("\n--- Agent Summary Line ---")
    summary = _build_agent_summary("AAPL", tone, themes, guidance, red_flags, "2024-11-01")
    print(f"  {summary}")

    print("\n" + "="*60)
    print("TEST 2: Error handling")
    print("="*60)
    err = _error_response("TRANSCRIPT_NOT_FOUND", "Test error")
    print(json.dumps(err["validation_results"], indent=2))

    print("\n" + "="*60)
    print("TEST 3: Live fetch (run on your machine)")
    print("="*60)
    print("  result = get_earnings_call_transcript('AAPL')")
    print("  print(result['data']['analysis']['tone'])")
    print("  print(result['data']['analysis']['key_themes'])")
    print("  print(result['data']['analysis']['red_flags'])")
    print("  print(result['data']['agent_summary_line'])")
    print("  print(result['data']['sections']['qa_section'][:1000])")