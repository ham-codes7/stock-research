"""
run_research.py
================
WHAT THIS FILE IS:
    The integration layer for all 7 tools.
    Run this file to research any company end to end.

    This is NOT the agent loop yet — that comes in Phase 3.
    This is the sequential pipeline that proves all tools
    work together before we wire them into the agent brain.

HOW TO RUN:
    python run_research.py AAPL
    python run_research.py TSLA
    python run_research.py MSFT "Microsoft Corp"

WHAT IT DOES:
    Step 1  → get_price_and_metrics      (Tool 1)
    Step 2  → get_recent_news            (Tool 2)
    Step 3  → sentiment_score            (Tool 6, uses Tool 2 output)
    Step 4  → get_financials_history     (Tool 3)
    Step 5  → get_peer_comparison        (Tool 4)
    Step 6  → get_sec_filing_summary     (Tool 5)
    Step 7  → get_earnings_call_transcript (Tool 7)
    Step 8  → print_research_brief       (combines all outputs)

FOLDER STRUCTURE NEEDED:
    stock-research-agent/
    ├── run_research.py          ← this file
    ├── .env                     ← your API keys
    └── tools/
        ├── tool_01_price_and_metrics.py
        ├── tool_02_recent_news.py
        ├── tool_03_financials_history.py
        ├── tool_04_peer_comparison.py
        ├── tool_05_sec_filing_summary.py
        ├── tool_06_sentiment_score.py
        └── tool_07_earnings_call_transcript.py

.ENV FILE:
    Create a file called .env in your stock-research-agent folder.
    Add this one line:
    NEWS_API_KEY=your_key_from_newsapi_org

    That is the only API key this entire pipeline needs.
    Everything else is free with no key.
"""

import sys
import json
import time
from datetime import datetime

# ── Import all 7 tools ────────────────────────────────────────────────────────
from tools.tool_01_price_and_metrics        import get_price_and_metrics
from tools.tool_02_recent_news              import get_recent_news
from tools.tool_03_financials_history       import get_financials_history
from tools.tool_04_peer_comparison          import get_peer_comparison
from tools.tool_05_sec_filing_summary       import get_sec_filing_summary
from tools.tool_06_sentiment_score          import sentiment_score
from tools.tool_07_earnings_call_transcript import get_earnings_call_transcript


# ── Separator helper ──────────────────────────────────────────────────────────
def section(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def sub(label: str, value):
    if value is None:
        print(f"  {label}: N/A")
    elif isinstance(value, list):
        if not value:
            print(f"  {label}: None detected")
        else:
            print(f"  {label}:")
            for item in value:
                if isinstance(item, dict):
                    print(f"    - {json.dumps(item)}")
                else:
                    print(f"    - {item}")
    else:
        print(f"  {label}: {value}")


# ── Main research pipeline ────────────────────────────────────────────────────

def run_research(ticker: str, company_name: str = None):
    """
    Run the full 7-tool research pipeline for a given ticker.
    Each tool's output feeds into the next where relevant.
    At the end, prints a structured research brief.
    """

    print(f"\n{'#' * 60}")
    print(f"  STOCK RESEARCH AGENT")
    print(f"  Researching: {ticker}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#' * 60}")

    results = {}  # stores all tool outputs

    # ── TOOL 1: Price and metrics ─────────────────────────────────────────────
    section("TOOL 1 — Price & Valuation Metrics")
    print("  Fetching live price and valuation multiples...")

    t1 = get_price_and_metrics(ticker)
    results["price"] = t1

    if t1["data"]:
        identity = t1["data"]["identity"]
        price    = t1["data"]["price"]
        val      = t1["data"]["valuation_multiples"]
        size     = t1["data"]["size"]
        flags    = t1["data"]["flags"]

        # Auto-resolve company name from Tool 1 if not provided
        if not company_name:
            company_name = identity.get("company_name", ticker)

        sub("Company",       identity.get("company_name"))
        sub("Sector",        identity.get("sector"))
        sub("Industry",      identity.get("industry"))
        sub("Current Price", f"${price.get('current')} ({price.get('day_change_pct')}% today)")
        sub("Market Cap",    size.get("market_cap_formatted"))
        sub("52W Position",  f"{price.get('week_52_position_pct')}% of range")
        sub("Trailing PE",   val.get("pe_trailing"))
        sub("Forward PE",    val.get("pe_forward"))
        sub("EV/EBITDA",     val.get("ev_to_ebitda"))
        sub("Confidence",    t1["confidence_assessment"]["label"])
        sub("Flags",         flags)
    else:
        print(f"  ERROR: {t1['validation_results'].get('error_message')}")
        print("  Cannot proceed without price data. Check ticker symbol.")
        return

    # ── TOOL 2: Recent news ───────────────────────────────────────────────────
    section("TOOL 2 — Recent News & Event Detection")
    print(f"  Fetching recent news for {company_name}...")

    t2 = get_recent_news(ticker, company_name)
    results["news"] = t2

    if t2["data"]:
        summary  = t2["data"]["summary"]
        articles = t2["data"]["articles"]
        flags    = t2["data"]["flags"]

        sub("Articles retrieved",   summary.get("total_articles_retrieved"))
        sub("Material events",      summary.get("material_event_count"))
        sub("Event breakdown",      summary.get("event_type_breakdown"))
        sub("Dominant themes",      summary.get("dominant_themes"))
        sub("Confidence",           t2["confidence_assessment"]["label"])
        sub("Flags",                flags)

        print("\n  Top 5 Headlines:")
        for i, article in enumerate(articles[:5], 1):
            label = article.get("label", "")
            print(f"    {i}. [{article.get('source_tier','?').upper()}] "
                  f"{'[MATERIAL] ' if article.get('is_material') else ''}"
                  f"{article.get('title','')[:80]}")
    else:
        print("  No news data returned.")

    # ── TOOL 6: Sentiment (uses Tool 2 output) ────────────────────────────────
    section("TOOL 6 — Sentiment Analysis")
    print("  Scoring news headline sentiment...")

    headlines = []
    if t2["data"]:
        headlines = t2["data"].get("headlines_for_sentiment", [])

    t6 = sentiment_score(headlines, ticker=ticker)
    results["sentiment"] = t6

    if t6["data"]:
        agg   = t6["data"]["aggregate"]
        flags = t6["data"]["flags"]

        sub("Sentiment score",   f"{agg.get('score'):.2f} / 1.0")
        sub("Overall label",     agg.get("overall_label"))
        sub("Positive headlines",agg.get("positive_count"))
        sub("Neutral headlines", agg.get("neutral_count"))
        sub("Negative headlines",agg.get("negative_count"))
        sub("Negative themes",   t6["data"].get("negative_themes"))
        sub("Model used",        t6["metadata"].get("model_used"))
        sub("ML server online",  t6["metadata"].get("ml_server_online"))
        sub("Confidence",        t6["confidence_assessment"]["label"])
        sub("Flags",             flags)
        print(f"\n  Agent Summary: {t6['data'].get('agent_summary_line')}")
    else:
        print("  No sentiment data returned.")

    # ── TOOL 3: Financials history ────────────────────────────────────────────
    section("TOOL 3 — Financial History (8 Quarters)")
    print("  Fetching 8 quarters of financial statements...")

    t3 = get_financials_history(ticker, quarters=8)
    results["financials"] = t3

    if t3["data"]:
        identity = t3["data"]["identity"]
        ttm      = t3["data"]["ttm_summary"]
        trend    = t3["data"]["trend_analysis"]
        flags    = t3["data"]["flags"]
        quarters_data = t3["data"]["quarterly_data"]

        sub("Currency",          identity.get("currency"))
        sub("Quarters returned", identity.get("quarters_returned"))

        print("\n  TTM Summary:")
        sub("  TTM Revenue",      f"${ttm.get('ttm_revenue_m')}M")
        sub("  TTM Net Income",   f"${ttm.get('ttm_net_income_m')}M")
        sub("  TTM Free Cash Flow", f"${ttm.get('ttm_free_cash_flow_m')}M")
        sub("  TTM EBITDA",       f"${ttm.get('ttm_ebitda_m')}M")
        sub("  Net Debt",         f"${ttm.get('latest_net_debt_m')}M")

        print("\n  Trend Analysis:")
        for metric in ["revenue", "gross_margin", "operating_margin", "free_cash_flow"]:
            t = trend.get(metric, {})
            print(f"    {metric:25} | "
                  f"YoY: {str(t.get('yoy_growth_pct'))+'%':>8} | "
                  f"Direction: {t.get('4q_trend_direction','N/A')}")

        rev_acc = trend.get("revenue_acceleration")
        if rev_acc:
            print(f"\n  Revenue acceleration: {rev_acc}")

        sub("Confidence", t3["confidence_assessment"]["label"])
        sub("Flags",      flags)

        if quarters_data:
            print("\n  Most Recent Quarter:")
            q = quarters_data[0]
            print(f"    Period:            {q.get('period')}")
            inc = q.get("income_statement", {})
            mar = q.get("margins", {})
            print(f"    Revenue:           ${inc.get('revenue')}M")
            print(f"    Gross Margin:      {mar.get('gross_margin_pct')}%")
            print(f"    Operating Margin:  {mar.get('operating_margin_pct')}%")
            print(f"    Net Margin:        {mar.get('net_margin_pct')}%")
    else:
        print(f"  ERROR: {t3['validation_results'].get('error_message')}")

    # ── TOOL 4: Peer comparison ───────────────────────────────────────────────
    section("TOOL 4 — Peer Comparison & Relative Valuation")
    print(f"  Building comp table for {company_name}...")

    t4 = get_peer_comparison(ticker)
    results["peers"] = t4

    if t4["data"]:
        peer_group   = t4["data"]["peer_group"]
        positioning  = t4["data"]["positioning"]
        rankings     = t4["data"]["rankings"]
        flags        = t4["data"]["flags"]

        sub("Peers identified", peer_group.get("peers_identified"))
        sub("Peers failed",     peer_group.get("peers_failed"))

        print("\n  Relative Rankings vs Peers:")
        key_metrics = [
            ("pe_forward",      "Forward PE"),
            ("ev_ebitda",       "EV/EBITDA"),
            ("gross_margin",    "Gross Margin"),
            ("operating_margin","Operating Margin"),
            ("revenue_growth",  "Revenue Growth"),
            ("roe",             "Return on Equity"),
        ]
        for key, label in key_metrics:
            r = rankings.get(key, {})
            val_str  = str(r.get("subject_value", "N/A"))
            med_str  = str(r.get("peer_median", "N/A"))
            rank_str = (f"#{r.get('rank')}/{r.get('ranked_out_of')}"
                        if r.get("rank") else "N/A")
            vs_label = r.get("vs_median_label", "N/A")
            print(f"    {label:22} | "
                  f"Value: {val_str:>8} | "
                  f"Median: {med_str:>8} | "
                  f"Rank: {rank_str:>6} | "
                  f"{vs_label}")

        print("\n  Positioning Summary:")
        sub("  Valuation quality",  positioning.get("valuation_quality_label"))
        sub("  Strengths",          positioning.get("strengths_vs_peers"))
        sub("  Weaknesses",         positioning.get("weaknesses_vs_peers"))
        print(f"\n  Analyst Summary: {positioning.get('analyst_summary')}")

        sub("Confidence", t4["confidence_assessment"]["label"])
        sub("Flags",      flags)
    else:
        print(f"  ERROR: {t4['validation_results'].get('error_message')}")

    # ── TOOL 5: SEC filing ────────────────────────────────────────────────────
    section("TOOL 5 — SEC Filing Analysis")
    print(f"  Fetching SEC filings for {ticker}...")

    t5 = get_sec_filing_summary(ticker)
    results["sec"] = t5

    if t5["data"]:
        filing   = t5["data"]["filing_metadata"]
        sections_data = t5["data"]["sections"]
        red_flags= t5["data"]["red_flags"]
        metrics  = t5["data"]["mentioned_metrics"]
        flags    = t5["data"]["flags"]

        sub("Filing type",    filing.get("form_type"))
        sub("Filed date",     filing.get("filed_date"))
        sub("Days since",     f"{filing.get('days_since_filed')} days ago")
        sub("Is amended",     filing.get("is_amended"))

        print("\n  Sections extracted:")
        for sec_name, content in sections_data.items():
            status = "FOUND" if content and len(content) > 100 else "NOT FOUND"
            print(f"    [{status}] {sec_name}")

        print("\n  Metrics mentioned in MD&A:")
        sub("  Percentages",    metrics.get("percentage_figures", [])[:5])
        sub("  Growth mentions",
            [f"{g['direction']} {g['amount_pct']}%"
             for g in metrics.get("growth_mentions", [])[:4]])

        sub("Red flags",  red_flags)
        sub("Confidence", t5["confidence_assessment"]["label"])
        sub("Flags",      flags)

        # Print risk factors excerpt
        risk = sections_data.get("risk_factors")
        if risk:
            print(f"\n  Risk Factors (first 400 chars):")
            print(f"    {risk[:400]}...")
    else:
        print(f"  ERROR: {t5['validation_results'].get('error_message')}")

    # ── TOOL 7: Earnings call transcript ─────────────────────────────────────
    section("TOOL 7 — Earnings Call Transcript Analysis")
    print(f"  Fetching most recent earnings call transcript...")

    t7 = get_earnings_call_transcript(ticker)
    results["transcript"] = t7

    if t7["data"]:
        identity  = t7["data"]["identity"]
        analysis  = t7["data"]["analysis"]
        sections_t= t7["data"]["sections"]
        flags     = t7["data"]["flags"]

        sub("Transcript date", identity.get("transcript_date"))
        sub("Source",          identity.get("source"))
        sub("Title",           identity.get("transcript_title"))

        tone = analysis.get("tone", {})
        print("\n  Management Tone:")
        sub("  Dominant tone",      tone.get("dominant_tone"))
        sub("  Interpretation",     tone.get("interpretation"))

        print("\n  Key Themes:")
        for t in analysis.get("key_themes", [])[:5]:
            print(f"    - {t['theme']}: {t['mention_count']} mentions")

        print("\n  Guidance Mentions:")
        for g in analysis.get("guidance_mentions", [])[:3]:
            print(f"    - {g['sentence'][:120]}")

        print("\n  Repeated Phrases (management talking points):")
        for r in analysis.get("repeated_phrases", [])[:4]:
            print(f"    - '{r['phrase']}' × {r['count']}")

        sub("Red flags",    analysis.get("red_flags"))
        sub("Deflections",  [d["phrase"] for d in analysis.get("deflections_detected", [])])
        sub("Confidence",   t7["confidence_assessment"]["label"])
        sub("Flags",        flags)

        print(f"\n  Agent Summary: {t7['data'].get('agent_summary_line')}")
    else:
        print(f"  No transcript data: {t7['validation_results'].get('error_message')}")

    # ── FINAL RESEARCH BRIEF ──────────────────────────────────────────────────
    _print_research_brief(ticker, company_name, results)

    return results


# ── Research brief printer ────────────────────────────────────────────────────

def _print_research_brief(ticker: str, company_name: str, results: dict):
    """
    Combine all tool outputs into a structured research brief.
    This is the format the agent will eventually generate.
    Right now we're assembling it manually from tool outputs.
    In Phase 3, Claude will generate this narrative automatically.
    """

    print(f"\n{'#' * 60}")
    print(f"  RESEARCH BRIEF — {ticker} ({company_name})")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#' * 60}")

    # ── 1. Company snapshot ───────────────────────────────────────────────────
    section("1. COMPANY SNAPSHOT")
    price_data = results.get("price", {}).get("data", {})
    if price_data:
        identity = price_data.get("identity", {})
        price    = price_data.get("price", {})
        val      = price_data.get("valuation_multiples", {})
        size     = price_data.get("size", {})
        mkt_beh  = price_data.get("market_behaviour", {})

        print(f"  {company_name} ({ticker})")
        print(f"  {identity.get('sector')} | {identity.get('industry')}")
        print(f"  Exchange: {identity.get('exchange')} | Currency: {identity.get('currency')}")
        print()
        print(f"  Price:       ${price.get('current')}  "
              f"({price.get('day_change_pct')}% today)")
        print(f"  Market Cap:  {size.get('market_cap_formatted')}")
        print(f"  52W Range:   ${price.get('week_52_low')} – ${price.get('week_52_high')}"
              f"  ({price.get('week_52_position_pct')}% of range)")
        print(f"  Beta:        {mkt_beh.get('beta')}")

    # ── 2. Valuation summary ──────────────────────────────────────────────────
    section("2. VALUATION")
    if price_data:
        val = price_data.get("valuation_multiples", {})
        rank_data = results.get("peers", {}).get("data", {})
        rankings  = rank_data.get("rankings", {}) if rank_data else {}

        metrics = [
            ("Trailing P/E",    val.get("pe_trailing"),    "pe_trailing"),
            ("Forward P/E",     val.get("pe_forward"),     "pe_forward"),
            ("EV/EBITDA",       val.get("ev_to_ebitda"),   "ev_ebitda"),
            ("Price/Sales",     val.get("price_to_sales"), "price_to_sales"),
            ("Price/Book",      val.get("price_to_book"),  "price_to_book"),
        ]
        for label, val_raw, rank_key in metrics:
            rank = rankings.get(rank_key, {})
            vs   = rank.get("vs_median_label", "")
            med  = rank.get("peer_median")
            print(f"  {label:15} {str(val_raw):>8}   "
                  f"Peer median: {str(med):>8}   {vs}")

        pos = rank_data.get("positioning", {}) if rank_data else {}
        vq  = pos.get("valuation_quality_label")
        if vq:
            print(f"\n  Valuation quality: {vq}")

    # ── 3. Financial performance ──────────────────────────────────────────────
    section("3. FINANCIAL PERFORMANCE")
    fin_data = results.get("financials", {}).get("data", {})
    if fin_data:
        ttm   = fin_data.get("ttm_summary", {})
        trend = fin_data.get("trend_analysis", {})

        print("  TTM (Trailing Twelve Months):")
        print(f"    Revenue:        ${ttm.get('ttm_revenue_m')}M")
        print(f"    Net Income:     ${ttm.get('ttm_net_income_m')}M")
        print(f"    Free Cash Flow: ${ttm.get('ttm_free_cash_flow_m')}M")
        print(f"    EBITDA:         ${ttm.get('ttm_ebitda_m')}M")
        print(f"    Net Debt:       ${ttm.get('latest_net_debt_m')}M")
        print(f"    Net Margin:     {ttm.get('ttm_net_margin_pct')}%")

        print("\n  Trend Signals:")
        for metric in ["revenue", "gross_margin", "operating_margin"]:
            t = trend.get(metric, {})
            print(f"    {metric:22} YoY: {str(t.get('yoy_growth_pct','N/A'))+'%':>8}"
                  f"  4Q direction: {t.get('4q_trend_direction','N/A')}")

        acc = trend.get("revenue_acceleration")
        if acc:
            print(f"\n  {acc}")

    # ── 4. Competitive position ───────────────────────────────────────────────
    section("4. COMPETITIVE POSITION")
    peer_data = results.get("peers", {}).get("data", {})
    if peer_data:
        pos = peer_data.get("positioning", {})
        print(f"  {pos.get('analyst_summary')}")
        print()
        strengths = pos.get("strengths_vs_peers", [])
        weaknesses= pos.get("weaknesses_vs_peers", [])
        if strengths:
            print("  Strengths vs peers:")
            for s in strengths:
                print(f"    ✓ {s}")
        if weaknesses:
            print("  Weaknesses vs peers:")
            for w in weaknesses:
                print(f"    ✗ {w}")

    # ── 5. News sentiment ─────────────────────────────────────────────────────
    section("5. NEWS SENTIMENT")
    sent_data = results.get("sentiment", {}).get("data", {})
    if sent_data:
        print(f"  {results['sentiment']['data'].get('agent_summary_line')}")
        themes = sent_data.get("negative_themes", [])
        if themes:
            print(f"  Negative themes: {', '.join(themes)}")

    # ── 6. Management signals ─────────────────────────────────────────────────
    section("6. MANAGEMENT SIGNALS (Earnings Call)")
    trans_data = results.get("transcript", {}).get("data", {})
    if trans_data:
        print(f"  {trans_data.get('agent_summary_line')}")
        analysis = trans_data.get("analysis", {})
        deflections = analysis.get("deflections_detected", [])
        if deflections:
            print(f"\n  Analyst questions deflected:")
            for d in deflections[:3]:
                print(f"    - '{d['phrase']}'")

    # ── 7. Risk summary ───────────────────────────────────────────────────────
    section("7. KEY RISKS")
    all_flags = []

    # Collect flags from all tools
    for tool_key in ["price", "news", "financials", "peers", "sec", "transcript"]:
        tool_result = results.get(tool_key, {})
        data = tool_result.get("data", {})
        if data:
            flags = data.get("flags", [])
            all_flags.extend(flags)

    # SEC red flags
    sec_data = results.get("sec", {}).get("data", {})
    if sec_data:
        for rf in sec_data.get("red_flags", []):
            all_flags.append(f"SEC RED FLAG: {rf}")

    # Transcript red flags
    if trans_data:
        for rf in trans_data.get("analysis", {}).get("red_flags", []):
            all_flags.append(f"MANAGEMENT RED FLAG: {rf}")

    if all_flags:
        for flag in all_flags[:10]:  # show top 10 flags
            print(f"  ⚠  {flag}")
    else:
        print("  No significant flags detected across all tools.")

    # ── 8. Data quality summary ───────────────────────────────────────────────
    section("8. DATA QUALITY")
    tool_names = {
        "price":      "Tool 1 — Price & Metrics",
        "news":       "Tool 2 — Recent News",
        "sentiment":  "Tool 6 — Sentiment",
        "financials": "Tool 3 — Financials",
        "peers":      "Tool 4 — Peer Comparison",
        "sec":        "Tool 5 — SEC Filing",
        "transcript": "Tool 7 — Earnings Call",
    }
    for key, name in tool_names.items():
        result = results.get(key, {})
        conf   = result.get("confidence_assessment", {})
        score  = conf.get("score_pct", 0)
        label  = conf.get("label", "N/A")
        bar    = "█" * (score // 10) + "░" * (10 - score // 10)
        print(f"  {name:35} [{bar}] {score}%  {label}")

    print(f"\n{'#' * 60}")
    print(f"  END OF RESEARCH BRIEF — {ticker}")
    print(f"{'#' * 60}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_research.py <TICKER> [company_name]")
        print("Examples:")
        print("  python run_research.py AAPL")
        print("  python run_research.py TSLA 'Tesla Inc'")
        print("  python run_research.py MSFT 'Microsoft Corporation'")
        sys.exit(1)

    ticker_input   = sys.argv[1].upper()
    company_input  = sys.argv[2] if len(sys.argv) > 2 else None

    run_research(ticker_input, company_input)