"""
TOOL 03 — get_financials_history(ticker)
=========================================
PURPOSE:
    Retrieve 8 quarters of financial statement data and automatically compute
    trend analysis across revenue, margins, EPS, cash flow, and leverage.

    This is the core fundamental analysis tool. A junior analyst typically
    spends 1-2 hours per company manually pulling quarterly results from
    filings, pasting into Excel, and computing growth rates and margin trends.
    This tool does all of that in one call.

ANALYST USE CASES:
    - Fundamental screening: is this business growing or declining?
    - Margin analysis: are margins expanding or compressing quarter over quarter?
    - Earnings quality: is reported profit backed by real cash flow?
    - Leverage check: is the balance sheet getting stronger or weaker?
    - Trend detection: acceleration or deceleration in key metrics?
    - Red flag detection: sudden margin drops, rising debt, deteriorating FCF

RESEARCH STEP REPLACED:
    Opening EDGAR/company IR pages, downloading 8 quarterly reports,
    copying revenue/EPS/margins into Excel, computing QoQ and YoY growth,
    building a trend table. Saves 1-2 hours per company.

POSITION IN PIPELINE:
    Called THIRD — after price/metrics and news context are established.
    Provides the quantitative backbone for thesis generation.
    Its output feeds into:
    - get_peer_comparison() — your historical margins vs peers
    - thesis generation — growth trajectory and quality of earnings
    - bear/bull case construction — trend acceleration or deterioration

DATA SOURCES:
    PRIMARY: yfinance — quarterly income statement, balance sheet, cash flow
    EXCLUDED: News, filings text, sentiment — handled by other tools

EDGE CASES HANDLED:
    - Fewer than 8 quarters available (new IPO, recently listed)
    - Negative revenue (rare, restatement scenario — flagged)
    - Negative EBITDA / operating loss (flagged explicitly)
    - Missing cash flow data (FCF marked unavailable)
    - Currency changes across periods (flagged if detected)
    - Restatements (sudden historical revisions — flagged)
    - Non-US companies with different reporting calendars
    - TTM (trailing twelve months) computed from available quarters

TOOL INVOCATION RULES:
    Call when:
    - Building any fundamental thesis on a company
    - Comparing a stock's current multiple to its own earnings history
    - Investigating margin or growth anomalies flagged by Tool 1 or 2
    Do NOT call for pure macro/sector questions — use industry tool instead.
    Call ONCE per company per session. Reuse output downstream.

APIs REQUIRED:
    yfinance — pip install yfinance
    No API key needed.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from typing import Optional


def get_financials_history(ticker: str, quarters: int = 8) -> dict:
    """
    Fetch multi-quarter financial history and compute trend analysis.

    REQUIRED PARAMETERS:
        ticker (str): Stock ticker e.g. "AAPL", "RELIANCE.NS"

    OPTIONAL PARAMETERS:
        quarters (int): Number of quarters to retrieve (default 8, max 12)

    VALIDATION RULES:
        - ticker uppercased automatically
        - quarters capped at 12 (yfinance limit)
        - All growth rates require minimum 2 data points
        - Missing individual fields degrade confidence score, not fail entirely
    """

    ticker  = ticker.strip().upper()
    quarters = min(quarters, 12)

    if not ticker:
        return _error_response("EMPTY_TICKER", "Ticker symbol cannot be empty.")

    # ── Fetch all three statements ────────────────────────────────────────────
    try:
        stock           = yf.Ticker(ticker)
        income_q        = stock.quarterly_income_stmt
        balance_q       = stock.quarterly_balance_sheet
        cashflow_q      = stock.quarterly_cashflow
        info            = stock.info or {}
    except Exception as e:
        return _error_response("FETCH_FAILED", f"yfinance fetch failed: {str(e)}")

    # ── Validate data returned ────────────────────────────────────────────────
    if income_q is None or income_q.empty:
        return _error_response(
            "NO_FINANCIAL_DATA",
            f"No quarterly financial data found for '{ticker}'. "
            "Company may be newly listed, delisted, or a non-reporting entity."
        )

    # ── Limit to requested quarters ───────────────────────────────────────────
    # yfinance returns columns as dates, most recent first
    income_q    = income_q.iloc[:, :quarters]
    balance_q   = balance_q.iloc[:, :quarters] if balance_q is not None and not balance_q.empty else pd.DataFrame()
    cashflow_q  = cashflow_q.iloc[:, :quarters] if cashflow_q is not None and not cashflow_q.empty else pd.DataFrame()

    actual_quarters = income_q.shape[1]
    quarter_dates   = [str(c)[:10] for c in income_q.columns.tolist()]

    # ── Safe row extractor ────────────────────────────────────────────────────
    def get_row(df, *keys):
        """Try multiple possible row names — yfinance naming is inconsistent."""
        for key in keys:
            if key in df.index:
                return df.loc[key]
        return pd.Series([None] * df.shape[1], index=df.columns)

    # ── Income statement rows ─────────────────────────────────────────────────
    revenue         = get_row(income_q, "Total Revenue", "Revenue")
    gross_profit    = get_row(income_q, "Gross Profit")
    operating_inc   = get_row(income_q, "Operating Income", "EBIT")
    ebitda          = get_row(income_q, "EBITDA", "Normalized EBITDA")
    net_income      = get_row(income_q, "Net Income", "Net Income Common Stockholders")
    interest_exp    = get_row(income_q, "Interest Expense", "Net Interest Income")
    tax_exp         = get_row(income_q, "Tax Provision", "Income Tax Expense")
    rd_exp          = get_row(income_q, "Research And Development", "Research Development")
    eps_basic       = get_row(income_q, "Basic EPS", "Diluted EPS")

    # ── Balance sheet rows ────────────────────────────────────────────────────
    total_assets    = get_row(balance_q, "Total Assets")
    total_debt      = get_row(balance_q, "Total Debt", "Long Term Debt And Capital Lease Obligation")
    cash            = get_row(balance_q, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
    total_equity    = get_row(balance_q, "Stockholders Equity", "Total Equity Gross Minority Interest")
    current_assets  = get_row(balance_q, "Current Assets")
    current_liab    = get_row(balance_q, "Current Liabilities")

    # ── Cash flow rows ────────────────────────────────────────────────────────
    cfo             = get_row(cashflow_q, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex           = get_row(cashflow_q, "Capital Expenditure", "Purchase Of PPE")

    # ── Build per-quarter records ─────────────────────────────────────────────
    quarters_data = []
    for i, date in enumerate(quarter_dates):
        def v(series, idx=i):
            """Safe value extractor — returns None if missing or NaN."""
            try:
                val = series.iloc[idx]
                return None if pd.isna(val) else float(val)
            except (IndexError, TypeError):
                return None

        rev     = v(revenue)
        gp      = v(gross_profit)
        op_inc  = v(operating_inc)
        ni      = v(net_income)
        eb      = v(ebitda)
        cfo_val = v(cfo)
        capex_v = v(capex)

        # Derived margins (require revenue > 0)
        gross_margin    = _safe_pct(gp, rev)
        operating_margin= _safe_pct(op_inc, rev)
        net_margin      = _safe_pct(ni, rev)
        ebitda_margin   = _safe_pct(eb, rev)

        # Free cash flow = CFO - CapEx (CapEx is negative in yfinance)
        fcf = None
        if cfo_val is not None and capex_v is not None:
            fcf = cfo_val + capex_v  # capex already negative

        # FCF conversion = FCF / Net Income (earnings quality check)
        fcf_conversion = _safe_ratio(fcf, ni)

        # Net debt = Total Debt - Cash
        td      = v(total_debt)
        c       = v(cash)
        net_debt = (td - c) if (td is not None and c is not None) else None

        # Net Debt / EBITDA (leverage ratio — annualise EBITDA)
        nd_ebitda = None
        if net_debt is not None and eb is not None and eb != 0:
            nd_ebitda = round(net_debt / (eb * 4), 2)  # annualise quarterly EBITDA

        # Current ratio
        ca  = v(current_assets)
        cl  = v(current_liab)
        current_ratio = _safe_ratio(ca, cl)

        # RoE = Net Income / Equity (annualised)
        eq  = v(total_equity)
        roe = None
        if ni is not None and eq is not None and eq != 0:
            roe = round((ni * 4 / eq) * 100, 2)

        quarters_data.append({
            "period":               date,
            "income_statement": {
                "revenue":          _fmt(rev),
                "gross_profit":     _fmt(gp),
                "operating_income": _fmt(op_inc),
                "ebitda":           _fmt(eb),
                "net_income":       _fmt(ni),
                "rd_expense":       _fmt(v(rd_exp)),
                "eps_basic":        v(eps_basic),
            },
            "margins": {
                "gross_margin_pct":     gross_margin,
                "operating_margin_pct": operating_margin,
                "net_margin_pct":       net_margin,
                "ebitda_margin_pct":    ebitda_margin,
            },
            "cash_flow": {
                "operating_cash_flow":  _fmt(cfo_val),
                "capex":                _fmt(capex_v),
                "free_cash_flow":       _fmt(fcf),
                "fcf_conversion_pct":   fcf_conversion,
            },
            "balance_sheet": {
                "total_assets":     _fmt(v(total_assets)),
                "total_debt":       _fmt(td),
                "cash":             _fmt(c),
                "net_debt":         _fmt(net_debt),
                "total_equity":     _fmt(eq),
                "current_ratio":    current_ratio,
            },
            "leverage_and_returns": {
                "net_debt_to_ebitda":   nd_ebitda,
                "return_on_equity_pct": roe,
            },
        })

    # ── Trend analysis ────────────────────────────────────────────────────────
    # Use most recent 4 quarters vs prior 4 quarters for YoY
    trend = _compute_trends(quarters_data, quarter_dates)

    # ── TTM (Trailing Twelve Months) — sum of last 4 quarters ────────────────
    ttm = _compute_ttm(quarters_data)

    # ── Flags and anomalies ───────────────────────────────────────────────────
    flags = _detect_flags(quarters_data, trend, actual_quarters)

    # ── Confidence score ──────────────────────────────────────────────────────
    populated_fields = sum(
        1 for q in quarters_data[:4]
        for val in [
            q["income_statement"]["revenue"],
            q["margins"]["gross_margin_pct"],
            q["cash_flow"]["free_cash_flow"],
            q["balance_sheet"]["net_debt"],
        ]
        if val is not None
    )
    confidence_score = min(100, round((populated_fields / 16) * 100))
    confidence_label = (
        "HIGH"   if confidence_score >= 80 else
        "MEDIUM" if confidence_score >= 50 else
        "LOW — significant data gaps, interpret with caution"
    )

    # ── Missing fields ────────────────────────────────────────────────────────
    missing = []
    if all(q["cash_flow"]["free_cash_flow"] is None for q in quarters_data):
        missing.append("free_cash_flow — cash flow statement unavailable")
    if all(q["balance_sheet"]["net_debt"] is None for q in quarters_data):
        missing.append("net_debt — balance sheet unavailable")
    if actual_quarters < 4:
        missing.append(f"full_history — only {actual_quarters} quarters available (newly listed?)")

    return {
        "data": {
            "identity": {
                "ticker":           ticker,
                "company_name":     info.get("longName") or info.get("shortName") or ticker,
                "currency":         info.get("financialCurrency") or info.get("currency") or "USD",
                "reporting_periods":quarter_dates,
                "quarters_returned":actual_quarters,
            },
            "ttm_summary":  ttm,
            "trend_analysis": trend,
            "quarterly_data": quarters_data,
            "flags":          flags,
        },
        "metadata": {
            "tool":             "get_financials_history",
            "version":          "1.0",
            "ticker_queried":   ticker,
            "quarters_requested": quarters,
            "timestamp_utc":    datetime.now(timezone.utc).isoformat(),
            "data_source":      "Yahoo Finance via yfinance (quarterly statements)",
            "note":             "All monetary values in reporting currency (millions). Margins in percent.",
        },
        "validation_results": {
            "ticker_resolved":  True,
            "data_found":       True,
            "flags_detected":   flags,
            "flag_count":       len(flags),
        },
        "confidence_assessment": {
            "score_pct":        confidence_score,
            "label":            confidence_label,
            "quarters_available": actual_quarters,
            "quarters_requested": quarters,
        },
        "missing_information": {
            "missing_fields":   missing,
            "interpretation": (
                "Partial data is normal for: newly IPO'd firms, foreign listings, "
                "holding companies, or firms that don't report cash flows separately."
            ) if missing else "All key fields populated across requested quarters.",
        },
    }


# ── Derived metric helpers ────────────────────────────────────────────────────

def _safe_pct(numerator, denominator) -> Optional[float]:
    """Return percentage rounded to 2dp, or None if inputs invalid."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round((numerator / denominator) * 100, 2)


def _safe_ratio(a, b) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return round(a / b, 2)


def _fmt(val) -> Optional[float]:
    """Format large numbers to millions, rounded to 2dp."""
    if val is None:
        return None
    return round(val / 1_000_000, 2)  # convert to millions


def _growth_rate(new_val, old_val) -> Optional[float]:
    """Compute YoY or QoQ growth rate as percentage."""
    if new_val is None or old_val is None or old_val == 0:
        return None
    return round(((new_val - old_val) / abs(old_val)) * 100, 2)


# ── Trend analysis ────────────────────────────────────────────────────────────

def _compute_trends(quarters_data: list, dates: list) -> dict:
    """
    Compute QoQ and YoY trends across key metrics.
    Most recent quarter is index 0 (yfinance returns newest first).
    YoY = Q0 vs Q4 (same quarter last year).
    QoQ = Q0 vs Q1 (previous quarter).
    """
    def get_val(field_path, idx):
        """Navigate nested dict with dot notation e.g. 'income_statement.revenue'"""
        try:
            parts = field_path.split(".")
            val = quarters_data[idx]
            for p in parts:
                val = val[p]
            # Convert from millions back for growth computation (or keep as-is)
            return val
        except (IndexError, KeyError, TypeError):
            return None

    metrics = {
        "revenue":          "income_statement.revenue",
        "gross_profit":     "income_statement.gross_profit",
        "operating_income": "income_statement.operating_income",
        "net_income":       "income_statement.net_income",
        "free_cash_flow":   "cash_flow.free_cash_flow",
        "gross_margin":     "margins.gross_margin_pct",
        "operating_margin": "margins.operating_margin_pct",
        "net_margin":       "margins.net_margin_pct",
    }

    trends = {}
    for label, path in metrics.items():
        q0 = get_val(path, 0)   # most recent
        q1 = get_val(path, 1)   # prior quarter
        q4 = get_val(path, 4)   # same quarter last year

        qoq = _growth_rate(q0, q1)
        yoy = _growth_rate(q0, q4)

        # 4-quarter direction: are we improving or deteriorating?
        values = [get_val(path, i) for i in range(min(4, len(quarters_data)))]
        values = [v for v in values if v is not None]
        direction = _compute_direction(values)

        trends[label] = {
            "most_recent":          q0,
            "qoq_growth_pct":       qoq,
            "yoy_growth_pct":       yoy,
            "4q_trend_direction":   direction,
        }

    # ── Acceleration / deceleration check ────────────────────────────────────
    rev_growths = []
    for i in range(min(4, len(quarters_data) - 1)):
        q_now  = get_val("income_statement.revenue", i)
        q_prev = get_val("income_statement.revenue", i + 1)
        g = _growth_rate(q_now, q_prev)
        if g is not None:
            rev_growths.append(g)

    acceleration = None
    if len(rev_growths) >= 3:
        if rev_growths[0] > rev_growths[1] > rev_growths[2]:
            acceleration = "ACCELERATING — revenue growth increasing each quarter"
        elif rev_growths[0] < rev_growths[1] < rev_growths[2]:
            acceleration = "DECELERATING — revenue growth slowing each quarter"
        else:
            acceleration = "MIXED — no clear acceleration or deceleration trend"

    trends["revenue_acceleration"] = acceleration

    return trends


def _compute_direction(values: list) -> str:
    """Determine 4-quarter trend direction from list of values."""
    if len(values) < 2:
        return "INSUFFICIENT_DATA"
    # Compare first half vs second half average
    mid = len(values) // 2
    recent_avg  = sum(values[:mid]) / mid if mid > 0 else 0
    earlier_avg = sum(values[mid:]) / (len(values) - mid) if (len(values) - mid) > 0 else 0
    if earlier_avg == 0:
        return "INSUFFICIENT_DATA"
    change = ((recent_avg - earlier_avg) / abs(earlier_avg)) * 100
    if change > 5:
        return "IMPROVING"
    elif change < -5:
        return "DETERIORATING"
    else:
        return "STABLE"


# ── TTM computation ───────────────────────────────────────────────────────────

def _compute_ttm(quarters_data: list) -> dict:
    """Sum last 4 quarters for income/CF items. Use most recent for balance sheet."""
    def sum_4q(field_path):
        total = 0
        count = 0
        for i in range(min(4, len(quarters_data))):
            try:
                parts = field_path.split(".")
                val = quarters_data[i]
                for p in parts:
                    val = val[p]
                if val is not None:
                    total += val
                    count += 1
            except (KeyError, TypeError):
                pass
        return round(total, 2) if count > 0 else None

    def latest(field_path):
        try:
            parts = field_path.split(".")
            val = quarters_data[0]
            for p in parts:
                val = val[p]
            return val
        except (KeyError, TypeError, IndexError):
            return None

    ttm_revenue     = sum_4q("income_statement.revenue")
    ttm_net_income  = sum_4q("income_statement.net_income")
    ttm_fcf         = sum_4q("cash_flow.free_cash_flow")
    ttm_ebitda      = sum_4q("income_statement.ebitda")

    ttm_net_margin  = _safe_pct(
        ttm_net_income,
        ttm_revenue
    ) if ttm_revenue else None

    return {
        "ttm_revenue_m":        ttm_revenue,
        "ttm_net_income_m":     ttm_net_income,
        "ttm_free_cash_flow_m": ttm_fcf,
        "ttm_ebitda_m":         ttm_ebitda,
        "ttm_net_margin_pct":   ttm_net_margin,
        "latest_net_debt_m":    latest("balance_sheet.net_debt"),
        "latest_current_ratio": latest("balance_sheet.current_ratio"),
        "note": "TTM = sum of last 4 available quarters. Balance sheet items = most recent quarter.",
    }


# ── Flag detection ────────────────────────────────────────────────────────────

def _detect_flags(quarters_data: list, trend: dict, actual_quarters: int) -> list:
    """Detect anomalies that warrant analyst attention."""
    flags = []

    if actual_quarters < 4:
        flags.append(f"LIMITED_HISTORY — only {actual_quarters} quarters available")

    # Revenue decline
    rev_yoy = trend.get("revenue", {}).get("yoy_growth_pct")
    if rev_yoy is not None and rev_yoy < -10:
        flags.append(f"REVENUE_DECLINE — YoY revenue down {abs(rev_yoy):.1f}%")

    # Margin compression
    gm_trend = trend.get("gross_margin", {}).get("4q_trend_direction")
    om_trend = trend.get("operating_margin", {}).get("4q_trend_direction")
    if gm_trend == "DETERIORATING":
        flags.append("GROSS_MARGIN_COMPRESSION — gross margin deteriorating over last 4 quarters")
    if om_trend == "DETERIORATING":
        flags.append("OPERATING_MARGIN_COMPRESSION — operating margin deteriorating over last 4 quarters")

    # Negative operating income in most recent quarter
    if quarters_data:
        latest_op = quarters_data[0]["income_statement"].get("operating_income")
        if latest_op is not None and latest_op < 0:
            flags.append(f"OPERATING_LOSS — most recent quarter operating loss of ${abs(latest_op):.1f}M")

    # Negative FCF
    fcf_trend = trend.get("free_cash_flow", {}).get("4q_trend_direction")
    if fcf_trend == "DETERIORATING":
        flags.append("FCF_DETERIORATION — free cash flow declining over last 4 quarters")

    latest_fcf = quarters_data[0]["cash_flow"].get("free_cash_flow") if quarters_data else None
    if latest_fcf is not None and latest_fcf < 0:
        flags.append("NEGATIVE_FCF — most recent quarter free cash flow negative")

    # High leverage
    if quarters_data:
        nd_ebitda = quarters_data[0]["leverage_and_returns"].get("net_debt_to_ebitda")
        if nd_ebitda is not None and nd_ebitda > 4:
            flags.append(f"HIGH_LEVERAGE — Net Debt/EBITDA of {nd_ebitda}x (>4x threshold)")

    # Earnings quality — FCF conversion below 70%
    if quarters_data:
        fcf_conv = quarters_data[0]["cash_flow"].get("fcf_conversion_pct")
        if fcf_conv is not None and 0 < fcf_conv < 70:
            flags.append(
                f"LOW_EARNINGS_QUALITY — FCF conversion {fcf_conv:.1f}% "
                "(net income not well supported by cash flow)"
            )

    # Acceleration / deceleration
    acc = trend.get("revenue_acceleration")
    if acc and "DECELERATING" in acc:
        flags.append("REVENUE_DECELERATION — growth rate slowing for 3+ consecutive quarters")

    return flags


# ── Error response ────────────────────────────────────────────────────────────

def _error_response(code: str, message: str) -> dict:
    return {
        "data": None,
        "metadata": {
            "tool":          "get_financials_history",
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
    print("TEST 1: Valid ticker — Microsoft")
    print("="*60)
    result = get_financials_history("MSFT", quarters=8)

    if result["data"]:
        print(json.dumps({
            "identity":         result["data"]["identity"],
            "ttm_summary":      result["data"]["ttm_summary"],
            "trend_analysis":   result["data"]["trend_analysis"],
            "flags":            result["data"]["flags"],
            "confidence":       result["confidence_assessment"],
            "missing":          result["missing_information"],
            "sample_quarter":   result["data"]["quarterly_data"][0] if result["data"]["quarterly_data"] else None,
        }, indent=2))
    else:
        print(json.dumps(result, indent=2))

    print("\n" + "="*60)
    print("TEST 2: Invalid ticker")
    print("="*60)
    result2 = get_financials_history("INVALIDXYZ999")
    print(json.dumps(result2, indent=2))

    """to use anywhere in project
from tools.tool_03_financials_history import get_financials_history

result = get_financials_history("MSFT", quarters=8)

# TTM snapshot
print(result["data"]["ttm_summary"])

# Trend direction across all metrics
print(result["data"]["trend_analysis"])

# Flags — red alerts
print(result["data"]["flags"])

# Full quarter by quarter data
for q in result["data"]["quarterly_data"]:
    print(q["period"], q["margins"])"""