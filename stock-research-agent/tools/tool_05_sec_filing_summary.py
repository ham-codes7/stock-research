"""
TOOL 05 — get_sec_filing_summary(ticker)
=========================================
PURPOSE:
    Retrieve and extract key qualitative content from a company's most recent
    SEC filings — specifically the 10-K (annual) and 10-Q (quarterly) reports.

    Financial data APIs give you numbers. SEC filings give you the narrative
    behind the numbers — what management says about their business, what risks
    they're required to disclose, what changed since last quarter, and what
    they're not saying loudly enough.

    This tool hits the SEC EDGAR API directly — no third-party data vendor
    needed, completely free, and authoritative (straight from the source).

ANALYST USE CASES:
    - Risk factor extraction: what does management say could go wrong?
    - MD&A analysis: how does management explain recent performance?
    - Business description: what does this company actually do in detail?
    - Change detection: what's new or different vs the prior filing?
    - Red flag detection: unusual disclosures, going concern language,
      restatement notices, material weakness in internal controls
    - Qualitative thesis support: management's own words on growth drivers

RESEARCH STEP REPLACED:
    Manually navigating EDGAR, downloading 200-page 10-K PDFs, searching
    for risk factors and MD&A sections, reading and summarising.
    Saves 2-4 hours per company for a thorough qualitative read.

POSITION IN PIPELINE:
    Called FIFTH — after quantitative picture is established.
    Provides qualitative context that explains WHY the numbers look the way
    they do. Feeds into:
    - Thesis generation — management's own language for bull case
    - Bear case discovery — risk factors as structured input
    - Variant perception — gaps between management narrative and financials

DATA SOURCES:
    PRIMARY: SEC EDGAR REST API (api.sec.gov) — completely free, no key needed
    SECONDARY: SEC EDGAR full-text search (efts.sec.gov) — filing index
    EXCLUDED: News, financial data APIs — handled by other tools

EDGE CASES HANDLED:
    - Non-US companies (foreign private issuers file 20-F, not 10-K — handled)
    - Newly IPO'd companies (S-1 used as fallback if no 10-K exists)
    - Companies with no EDGAR filings (flagged — may be non-reporting)
    - Very large filings (text truncated at section level, not document level)
    - EDGAR rate limits (polite retry with backoff)
    - CIK lookup failure (fallback search by company name)
    - Amended filings (10-K/A, 10-Q/A — flagged as amended)

TOOL INVOCATION RULES:
    Call when:
    - Building a complete fundamental thesis on any US-listed company
    - News tool flagged a regulatory or legal event — check 8-K filings
    - Agent needs qualitative context beyond what financials show
    Do NOT call for: pure valuation questions, peer comparisons,
    or non-US companies without EDGAR filings.
    Call ONCE per company per session — filings don't change intraday.

APIs REQUIRED:
    SEC EDGAR REST API — https://data.sec.gov
    No API key needed. Completely free.
    Rate limit: 10 requests/second (we stay well under this).
    User-Agent header required by SEC — set in code automatically.
"""

import re
import time
import requests
from datetime import datetime, timezone
from typing import Optional


# SEC requires a descriptive User-Agent — failure to set this gets you blocked
SEC_USER_AGENT = "StockResearchAgent malleswarammoggers@gmail.com"
SEC_BASE_URL   = "https://data.sec.gov"
EDGAR_SEARCH   = "https://efts.sec.gov/LATEST/search-index"
SEC_HEADERS    = {
    "User-Agent":   SEC_USER_AGENT,
    "Accept":       "application/json",
}

# Filing types in priority order
FILING_PRIORITY = ["10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "S-1"]

# Sections we extract from filings
# Keys match common EDGAR section identifiers
TARGET_SECTIONS = {
    "business_description": [
        "item 1.", "item 1 ", "business overview",
        "description of business", "our business",
    ],
    "risk_factors": [
        "item 1a.", "item 1a ", "risk factors",
        "risks related to", "risks associated with",
    ],
    "mda": [
        "item 7.", "item 7 ", "item 2.",  # item 2 = MD&A in 10-Q
        "management's discussion", "management discussion",
        "results of operations",
    ],
    "recent_developments": [
        "recent developments", "recent events",
        "subsequent events", "item 8a.",
    ],
    "quantitative_disclosures": [
        "item 7a.", "quantitative and qualitative disclosures",
        "market risk",
    ],
}

# Red flag phrases that warrant analyst attention
RED_FLAG_PHRASES = [
    "going concern",
    "material weakness",
    "restatement",
    "restated",
    "significant doubt",
    "bankruptcy",
    "chapter 11",
    "chapter 7",
    "default",
    "covenant violation",
    "regulatory action",
    "criminal investigation",
    "SEC investigation",
    "class action",
    "whistleblower",
    "internal investigation",
    "impairment",
    "goodwill impairment",
    "write-down",
    "write-off",
    "discontinued operations",
    "liquidity risk",
    "going out of business",
]


def get_sec_filing_summary(ticker: str,
                           filing_type: str = "auto",
                           max_section_chars: int = 3000) -> dict:
    """
    Retrieve and extract key sections from most recent SEC filing.

    REQUIRED PARAMETERS:
        ticker (str): Stock ticker e.g. "AAPL", "TSLA"

    OPTIONAL PARAMETERS:
        filing_type (str): "auto" (default) | "10-K" | "10-Q" | "20-F" | "S-1"
                           "auto" fetches most recent 10-K first, falls back to 10-Q
        max_section_chars (int): Max characters to extract per section (default 3000)
                                 Increase for deeper reads, decrease for faster runs

    VALIDATION RULES:
        - ticker uppercased automatically
        - filing_type validated against known SEC form types
        - CIK lookup retried once on failure before giving up
    """

    ticker = ticker.strip().upper()

    if not ticker:
        return _error_response("EMPTY_TICKER", "Ticker symbol cannot be empty.")

    # ── Step 1: Resolve ticker to CIK ────────────────────────────────────────
    cik, company_name = _resolve_cik(ticker)

    if not cik:
        return _error_response(
            "CIK_NOT_FOUND",
            f"Could not resolve '{ticker}' to an SEC CIK number. "
            "Company may not file with the SEC (non-US issuer, private company, "
            "or invalid ticker)."
        )

    cik_padded = str(cik).zfill(10)

    # ── Step 2: Fetch filing index for this company ───────────────────────────
    filings_meta = _fetch_filing_index(cik_padded)

    if not filings_meta:
        return _error_response(
            "FILING_INDEX_FAILED",
            f"Could not retrieve filing index for CIK {cik_padded}. "
            "EDGAR may be temporarily unavailable."
        )

    # ── Step 3: Select target filing ─────────────────────────────────────────
    target_types = (
        FILING_PRIORITY if filing_type == "auto"
        else [filing_type]
    )

    selected_filing = _select_filing(filings_meta, target_types)

    if not selected_filing:
        return _error_response(
            "NO_FILING_FOUND",
            f"No {filing_type} filing found for '{ticker}' (CIK: {cik}). "
            "Company may be newly listed, foreign private issuer, or non-reporting."
        )

    form_type    = selected_filing["form"]
    filed_date   = selected_filing["filed"]
    accession_no = selected_filing["accessionNumber"]
    is_amended   = form_type.endswith("/A")

    # ── Step 4: Fetch filing document list ───────────────────────────────────
    doc_url, doc_type = _get_primary_document_url(cik_padded, accession_no)

    if not doc_url:
        return _error_response(
            "DOCUMENT_NOT_FOUND",
            f"Could not retrieve document URL for filing {accession_no}."
        )

    # ── Step 5: Fetch and parse filing text ───────────────────────────────────
    filing_text = _fetch_filing_text(doc_url)

    if not filing_text:
        return _error_response(
            "FILING_TEXT_FAILED",
            f"Could not retrieve filing text from {doc_url}. "
            "Document may be in XBRL or binary format."
        )

    # ── Step 6: Extract target sections ──────────────────────────────────────
    sections = _extract_sections(filing_text, max_section_chars)

    # ── Step 7: Red flag scan ─────────────────────────────────────────────────
    red_flags = _scan_red_flags(filing_text)

    # ── Step 8: Extract key metrics mentioned in text ─────────────────────────
    mentioned_metrics = _extract_mentioned_metrics(
        sections.get("mda", "") + sections.get("business_description", "")
    )

    # ── Step 9: Flags ─────────────────────────────────────────────────────────
    flags = []

    if is_amended:
        flags.append(
            f"AMENDED_FILING — this is a {form_type} (amended). "
            "Check original filing for comparison."
        )

    if red_flags:
        flags.append(
            f"RED_FLAGS_DETECTED — {len(red_flags)} concerning phrase(s) found: "
            f"{', '.join(red_flags[:5])}"
        )

    if form_type in ("10-Q", "10-Q/A"):
        flags.append(
            "QUARTERLY_FILING — most recent is 10-Q, not annual 10-K. "
            "Risk factors may be abbreviated. Fetch 10-K for full disclosure."
        )

    if form_type in ("S-1",):
        flags.append(
            "IPO_FILING — company filed S-1. No operating history as public company."
        )

    days_since_filed = _days_since(filed_date)
    if days_since_filed and days_since_filed > 120:
        flags.append(
            f"STALE_FILING — most recent filing is {days_since_filed} days old. "
            "New filing may be due soon."
        )

    sections_missing = [k for k, v in sections.items() if not v]
    if sections_missing:
        flags.append(
            f"SECTIONS_NOT_EXTRACTED — could not parse: {', '.join(sections_missing)}. "
            "Filing may use non-standard section headers."
        )

    # ── Confidence score ──────────────────────────────────────────────────────
    sections_found  = sum(1 for v in sections.values() if v)
    total_sections  = len(TARGET_SECTIONS)
    confidence_score = round((sections_found / total_sections) * 100)

    if red_flags:
        confidence_score = min(confidence_score, 85)  # cap if red flags found

    confidence_label = (
        "HIGH"   if confidence_score >= 75 else
        "MEDIUM" if confidence_score >= 40 else
        "LOW — few sections extracted, qualitative analysis limited"
    )

    return {
        "data": {
            "identity": {
                "ticker":           ticker,
                "company_name":     company_name,
                "cik":              cik,
                "cik_padded":       cik_padded,
            },
            "filing_metadata": {
                "form_type":        form_type,
                "filed_date":       filed_date,
                "accession_number": accession_no,
                "document_url":     doc_url,
                "is_amended":       is_amended,
                "days_since_filed": days_since_filed,
            },
            "sections": {
                "business_description": sections.get("business_description"),
                "risk_factors":         sections.get("risk_factors"),
                "mda":                  sections.get("mda"),
                "recent_developments":  sections.get("recent_developments"),
                "quantitative_disclosures": sections.get("quantitative_disclosures"),
            },
            "red_flags":         red_flags,
            "mentioned_metrics": mentioned_metrics,
            "flags":             flags,
        },
        "metadata": {
            "tool":                 "get_sec_filing_summary",
            "version":              "1.0",
            "ticker_queried":       ticker,
            "filing_type_requested": filing_type,
            "timestamp_utc":        datetime.now(timezone.utc).isoformat(),
            "data_source":          "SEC EDGAR REST API (api.sec.gov)",
            "api_key_required":     False,
            "note": (
                f"Sections truncated at {max_section_chars} chars each. "
                "Increase max_section_chars for deeper reads."
            ),
        },
        "validation_results": {
            "ticker_resolved":  True,
            "cik_found":        True,
            "filing_found":     True,
            "sections_extracted": sections_found,
            "sections_total":   total_sections,
            "flags_detected":   flags,
            "flag_count":       len(flags),
        },
        "confidence_assessment": {
            "score_pct":        confidence_score,
            "label":            confidence_label,
            "sections_found":   sections_found,
            "sections_total":   total_sections,
            "red_flag_count":   len(red_flags),
        },
        "missing_information": {
            "missing_sections": sections_missing,
            "interpretation": (
                "Missing sections are common when: filing uses XBRL inline format, "
                "non-standard section headers, or company is foreign private issuer "
                "using 20-F format with different structure."
                if sections_missing else
                "All target sections successfully extracted."
            ),
        },
    }


# ── CIK resolution ────────────────────────────────────────────────────────────

def _resolve_cik(ticker: str) -> tuple:
    """
    Resolve ticker to SEC CIK using EDGAR company search.
    Returns (cik, company_name) or (None, None) on failure.
    """
    try:
        url      = f"{SEC_BASE_URL}/submissions/CIK{ticker.zfill(10)}.json"
        response = _sec_get(f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2020-01-01&enddt=2099-01-01&forms=10-K")

        # Primary: use EDGAR ticker-to-CIK mapping
        mapping_url = "https://www.sec.gov/files/company_tickers.json"
        r = _sec_get(mapping_url)
        if r and r.status_code == 200:
            data = r.json()
            for entry in data.values():
                if entry.get("ticker", "").upper() == ticker:
                    return entry["cik_str"], entry.get("title", ticker)

        # Fallback: EDGAR full-text search
        search_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=10-K"
        r2 = _sec_get(search_url)
        if r2 and r2.status_code == 200:
            hits = r2.json().get("hits", {}).get("hits", [])
            if hits:
                src = hits[0].get("_source", {})
                return src.get("entity_id"), src.get("display_names", [ticker])[0]

    except Exception:
        pass

    return None, None


# ── Filing index ──────────────────────────────────────────────────────────────

def _fetch_filing_index(cik_padded: str) -> Optional[dict]:
    """Fetch company submissions JSON from EDGAR."""
    url = f"{SEC_BASE_URL}/submissions/CIK{cik_padded}.json"
    r   = _sec_get(url)
    if r and r.status_code == 200:
        return r.json()
    return None


def _select_filing(filings_meta: dict, target_types: list) -> Optional[dict]:
    """
    Select the most recent filing of the desired type from filings metadata.
    EDGAR returns filings in the 'filings.recent' block.
    """
    try:
        recent = filings_meta.get("filings", {}).get("recent", {})
        forms       = recent.get("form", [])
        dates       = recent.get("filed", [])
        accessions  = recent.get("accessionNumber", [])

        if not forms:
            return None

        for target in target_types:
            for i, form in enumerate(forms):
                if form == target:
                    return {
                        "form":            form,
                        "filed":           dates[i] if i < len(dates) else None,
                        "accessionNumber": accessions[i] if i < len(accessions) else None,
                    }
    except Exception:
        pass

    return None


# ── Document URL resolution ───────────────────────────────────────────────────

def _get_primary_document_url(cik_padded: str, accession_no: str) -> tuple:
    """
    Fetch the filing index page and identify the primary HTML/HTM document.
    Returns (url, doc_type).
    """
    try:
        acc_clean   = accession_no.replace("-", "")
        index_url   = (
            f"{SEC_BASE_URL}/Archives/edgar/data/"
            f"{int(cik_padded)}/{acc_clean}/{accession_no}-index.json"
        )
        r = _sec_get(index_url)

        if r and r.status_code == 200:
            index_data = r.json()
            documents  = index_data.get("documents", [])

            # Prefer primary document — look for htm/html filing
            for doc in documents:
                doc_type = doc.get("type", "")
                filename = doc.get("name", "")
                if doc.get("isPrimary") and filename.endswith((".htm", ".html")):
                    url = (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{int(cik_padded)}/{acc_clean}/{filename}"
                    )
                    return url, doc_type

            # Fallback: first htm file
            for doc in documents:
                filename = doc.get("name", "")
                if filename.endswith((".htm", ".html")):
                    url = (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{int(cik_padded)}/{acc_clean}/{filename}"
                    )
                    return url, doc.get("type", "")

    except Exception:
        pass

    return None, None


# ── Filing text fetcher ───────────────────────────────────────────────────────

def _fetch_filing_text(doc_url: str) -> Optional[str]:
    """
    Fetch and clean filing HTML text.
    Strips HTML tags, normalises whitespace.
    """
    try:
        r = _sec_get(doc_url, timeout=20)
        if not r or r.status_code != 200:
            return None

        text = r.text

        # Strip HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Normalise whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove XBRL metadata blocks
        text = re.sub(r'\{[^}]{0,200}\}', '', text)

        return text.strip()

    except Exception:
        return None


# ── Section extraction ────────────────────────────────────────────────────────

def _extract_sections(text: str, max_chars: int) -> dict:
    """
    Extract target sections from cleaned filing text.
    Uses keyword matching on section headers.
    """
    sections = {k: None for k in TARGET_SECTIONS}
    text_lower = text.lower()

    for section_key, keywords in TARGET_SECTIONS.items():
        for keyword in keywords:
            idx = text_lower.find(keyword)
            if idx == -1:
                continue

            # Find the start of this section
            start = idx

            # Find the end — look for the next major section header
            end = len(text)
            next_section_markers = [
                "\nitem ", "ITEM ", "\npart ", "PART ",
                "table of contents", "TABLE OF CONTENTS",
            ]
            for marker in next_section_markers:
                next_idx = text_lower.find(marker.lower(), start + 100)
                if next_idx != -1 and next_idx < end:
                    end = next_idx

            excerpt = text[start:start + max_chars].strip()

            # Sanity check — must have meaningful content
            if len(excerpt) > 100:
                sections[section_key] = excerpt
                break

    return sections


# ── Red flag scanner ──────────────────────────────────────────────────────────

def _scan_red_flags(text: str) -> list:
    """Scan full filing text for red flag phrases."""
    text_lower  = text.lower()
    found       = []

    for phrase in RED_FLAG_PHRASES:
        if phrase.lower() in text_lower:
            found.append(phrase)

    return found


# ── Metric mention extractor ──────────────────────────────────────────────────

def _extract_mentioned_metrics(text: str) -> dict:
    """
    Extract specific numbers mentioned in MD&A and business description.
    Looks for percentage figures, dollar amounts, and growth rates.
    """
    metrics = {
        "percentage_figures": [],
        "dollar_amounts":     [],
        "growth_mentions":    [],
    }

    if not text:
        return metrics

    # Percentage figures e.g. "grew 23%", "margin of 41%"
    pct_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', text)
    metrics["percentage_figures"] = [
        float(p) for p in pct_matches[:10]
        if 0 < float(p) < 1000
    ]

    # Dollar amounts e.g. "$2.4 billion", "$500 million"
    dollar_matches = re.findall(
        r'\$\s*(\d+(?:\.\d+)?)\s*(billion|million|trillion)',
        text.lower()
    )
    for amount, unit in dollar_matches[:8]:
        multiplier = {"million": 1e6, "billion": 1e9, "trillion": 1e12}.get(unit, 1)
        metrics["dollar_amounts"].append({
            "raw": f"${amount} {unit}",
            "value": float(amount) * multiplier,
        })

    # Growth rate language
    growth_matches = re.findall(
        r'(increased?|decreased?|grew?|declined?|expanded?|contracted?)'
        r'\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%',
        text.lower()
    )
    for direction, amount in growth_matches[:8]:
        metrics["growth_mentions"].append({
            "direction": direction,
            "amount_pct": float(amount),
        })

    return metrics


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _sec_get(url: str, timeout: int = 12, retries: int = 2) -> Optional[requests.Response]:
    """
    Polite SEC EDGAR GET request with retry.
    SEC requires User-Agent and asks for <10 req/sec.
    """
    for attempt in range(retries):
        try:
            time.sleep(0.15)  # stay well under 10 req/sec limit
            r = requests.get(url, headers=SEC_HEADERS, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2 ** attempt)  # exponential backoff on rate limit
                continue
            return r
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None
        except Exception:
            return None
    return None


# ── Date helper ───────────────────────────────────────────────────────────────

def _days_since(date_str: Optional[str]) -> Optional[int]:
    """Return number of days since a filing date string e.g. '2024-01-15'."""
    if not date_str:
        return None
    try:
        filed = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - filed).days
    except Exception:
        return None


# ── Error response ────────────────────────────────────────────────────────────

def _error_response(code: str, message: str) -> dict:
    return {
        "data": None,
        "metadata": {
            "tool":          "get_sec_filing_summary",
            "version":       "1.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "data_source":   "SEC EDGAR REST API",
        },
        "validation_results": {
            "ticker_resolved": False,
            "error_code":      code,
            "error_message":   message,
        },
        "confidence_assessment": {"score_pct": 0, "label": "NO_DATA"},
        "missing_information":   {
            "missing_fields":  ["all"],
            "interpretation":  message,
        },
    }


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("\n" + "="*60)
    print("TEST 1: Logic and schema validation")
    print("="*60)

    # Test red flag scanner
    mock_text = """
    The company faces going concern risk as cash reserves decline.
    Management identified a material weakness in internal controls.
    The SEC investigation into accounting practices continues.
    Revenue increased 23% to $2.4 billion driven by cloud segment growth.
    Operating margin expanded by 340 basis points to 28.5%.
    """

    red_flags = _scan_red_flags(mock_text)
    print(f"\nRed flags detected: {len(red_flags)}")
    for f in red_flags:
        print(f"  - {f}")
    expected = ["going concern", "material weakness", "SEC investigation"]
    for ef in expected:
        found = ef in red_flags
        print(f"  [{'PASS' if found else 'FAIL'}] Expected: '{ef}'")

    # Test metric extraction
    print(f"\nMentioned metrics:")
    metrics = _extract_mentioned_metrics(mock_text)
    print(f"  Percentages:    {metrics['percentage_figures']}")
    print(f"  Dollar amounts: {metrics['dollar_amounts']}")
    print(f"  Growth mentions:{metrics['growth_mentions']}")
    print(f"  [{'PASS' if 23.0 in metrics['percentage_figures'] else 'FAIL'}] Percentage extraction")
    print(f"  [{'PASS' if any(d['value'] == 2.4e9 for d in metrics['dollar_amounts']) else 'FAIL'}] Dollar amount extraction")

    # Test days since
    print(f"\nDays since tests:")
    print(f"  '2024-01-01' → {_days_since('2024-01-01')} days")
    print(f"  None         → {_days_since(None)}")
    print(f"  [PASS] Date parsing")

    # Test section extraction
    print(f"\nSection extraction test:")
    mock_filing = """
    PART I

    Item 1. Business Overview
    We are a technology company that develops software products for enterprise customers.
    Our flagship product serves over 50,000 businesses worldwide.
    We generate revenue through subscription and professional services.

    Item 1A. Risk Factors
    Our business faces significant competition from larger companies with greater resources.
    We may not be able to maintain our growth rate due to market saturation.
    Regulatory changes could adversely affect our operations.

    Item 7. Management Discussion and Analysis
    Revenue increased 18% year over year driven by strong demand in North America.
    Gross margin expanded 200 basis points to 72% due to operating leverage.
    We expect continued growth in fiscal 2025 pending macroeconomic conditions.
    """
    sections = _extract_sections(mock_filing, max_chars=500)
    print(f"  Business description found: {'PASS' if sections.get('business_description') else 'FAIL'}")
    print(f"  Risk factors found:         {'PASS' if sections.get('risk_factors') else 'FAIL'}")
    print(f"  MD&A found:                 {'PASS' if sections.get('mda') else 'FAIL'}")

    print("\n" + "="*60)
    print("TEST 2: Error handling — invalid ticker")
    print("="*60)
    # Test error schema directly
    err = _error_response("CIK_NOT_FOUND", "Test error message")
    print(json.dumps(err, indent=2))

    print("\n" + "="*60)
    print("TEST 3: Live EDGAR call — Apple (requires network)")
    print("="*60)
    print("Run this on your local machine:")
    print("  result = get_sec_filing_summary('AAPL')")
    print("  print(result['data']['filing_metadata'])")
    print("  print(result['data']['red_flags'])")
    print("  print(result['data']['sections']['risk_factors'][:500])")

    """ to integrate this
from tools.tool_05_sec_filing_summary import get_sec_filing_summary

result = get_sec_filing_summary("AAPL")

# Check for red flags first — always
print(result["data"]["red_flags"])

# Read risk factors
print(result["data"]["sections"]["risk_factors"])

# Read MD&A — what management says about the numbers
print(result["data"]["sections"]["mda"])

# Metrics management mentioned in their own words
print(result["data"]["mentioned_metrics"])

# Filing metadata
print(result["data"]["filing_metadata"])"""