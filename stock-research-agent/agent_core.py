"""
agent_core.py
=============
The agent brain. This is where Claude drives the research process.

HOW IT WORKS:
    Claude receives a system prompt that describes all 7 tools.
    It then reasons about which tools to call, in what order.
    After each tool call, results are fed back into the conversation.
    When all tools are done, a final synthesis call produces the brief.

USAGE:
    # From terminal
    python agent_core.py AAPL
    python agent_core.py TSLA "Tesla Inc"

    # From backend (async)
    from agent_core import run_agent
    brief = await run_agent("AAPL", "Apple Inc.", request_id, ws_callback)

    # Synchronous (for testing)
    from agent_core import run_agent_sync
    brief = run_agent_sync("AAPL")
"""

import os
import sys
import json
import asyncio
import time
from datetime import datetime
from typing import Optional, Callable
from dotenv import load_dotenv
import google.genai as genai
from google.genai import types

# ── Import all 7 tools ────────────────────────────────────────────────────────
from tools.tool_01_price_and_metrics        import get_price_and_metrics
from tools.tool_02_recent_news              import get_recent_news
from tools.tool_03_financials_history       import get_financials_history
from tools.tool_04_peer_comparison          import get_peer_comparison
from tools.tool_05_sec_filing_summary       import get_sec_filing_summary
from tools.tool_06_sentiment_score          import sentiment_score
from tools.tool_07_earnings_call_transcript import get_earnings_call_transcript

load_dotenv()

# ── Client ────────────────────────────────────────────────────────────────────
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash-lite"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS
# Describes each tool to Claude so it knows when and how to call each one.
# The description is the most important part — Claude reads this to decide
# whether to call the tool and what arguments to pass.
# ══════════════════════════════════════════════════════════════════════════════

GEMINI_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_price_and_metrics",
        description=(
            "Fetch real-time stock price and core valuation metrics for a company. "
            "Returns current price, day change, 52-week position, market cap, "
            "PE ratios (trailing and forward), EV/EBITDA, price-to-book, beta, "
            "volume vs average, and anomaly flags. "
            "Call this FIRST for any company research. It anchors all valuation analysis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol e.g. AAPL, TSLA, MSFT"},
            },
            "required": ["ticker"],
        },
    ),
    types.FunctionDeclaration(
        name="get_recent_news",
        description=(
            "Fetch and classify recent news articles for a company. "
            "Returns headlines classified by event type (earnings, M&A, regulatory, "
            "leadership change, analyst action etc.), source credibility tier, "
            "and materiality flags. Also returns a headlines list ready for sentiment scoring. "
            "Call this SECOND — news context explains price movements and sets up sentiment analysis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "company_name": {"type": "string", "description": "Full company name e.g. Apple Inc. Improves news search accuracy."},
            },
            "required": ["ticker"],
        },
    ),
    types.FunctionDeclaration(
        name="sentiment_score",
        description=(
            "Score the sentiment of financial news headlines using an ML model. "
            "Returns aggregate sentiment score (0.0=bearish to 1.0=bullish), "
            "per-headline labels (positive/neutral/negative), high-conviction signals, "
            "and dominant negative themes. "
            "Call this AFTER get_recent_news — pass the headlines_for_sentiment field directly."
        ),
        parameters={
            "type": "object",
            "properties": {
                "headlines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of news headlines to score.",
                },
                "ticker": {"type": "string", "description": "Ticker context e.g. AAPL"},
            },
            "required": ["headlines"],
        },
    ),
    types.FunctionDeclaration(
        name="get_financials_history",
        description=(
            "Fetch 8 quarters of financial statement history with automatic trend analysis. "
            "Returns per-quarter revenue, gross profit, operating income, EBITDA, net income, "
            "all margins, free cash flow, net debt, and leverage ratios. "
            "Also computes TTM totals, QoQ and YoY growth rates, 4-quarter trend directions, "
            "revenue acceleration/deceleration, and anomaly flags. "
            "Call this for fundamental analysis — it is the quantitative backbone of any thesis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    ),
    types.FunctionDeclaration(
        name="get_peer_comparison",
        description=(
            "Build a peer comparison table benchmarking the company against its sector peers. "
            "Auto-identifies peers from sector/industry. Returns valuation multiples, "
            "growth rates, profitability margins, and leverage for each peer. "
            "Computes peer medians, ranks the subject company 1-to-N on each metric, "
            "calculates premium/discount to peer median, and generates a positioning summary "
            "with valuation quality label (ATTRACTIVE / FAIRLY_PRICED / EXPENSIVE / VALUE_TRAP_RISK). "
            "Call this for relative valuation context."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "custom_peers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of peer tickers to override auto-identification e.g. ['MSFT', 'GOOGL']",
                },
            },
            "required": ["ticker"],
        },
    ),
    types.FunctionDeclaration(
        name="get_sec_filing_summary",
        description=(
            "Retrieve and extract key sections from the most recent SEC filing (10-K or 10-Q). "
            "Returns business description, risk factors, management discussion and analysis (MD&A), "
            "recent developments, and quantitative disclosures. "
            "Also scans for 28 red flag phrases (going concern, material weakness, SEC investigation etc.) "
            "and extracts numeric metrics management mentioned. "
            "Call this for qualitative context — the narrative behind the numbers."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol. Must be a US-listed company filing with the SEC."},
            },
            "required": ["ticker"],
        },
    ),
    types.FunctionDeclaration(
        name="get_earnings_call_transcript",
        description=(
            "Retrieve and analyse the most recent earnings call transcript. "
            "Returns management tone (CONFIDENT/DEFENSIVE/HEDGING/MIXED), "
            "key themes by frequency, forward guidance mentions with numeric ranges, "
            "repeated phrases (management talking points), red flag language detection, "
            "and analyst Q&A deflection detection. "
            "Call this LAST — it provides the management narrative layer and is slowest to fetch."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    ),
])


# ══════════════════════════════════════════════════════════════════════════════
# TOOL DISPATCH
# Maps Claude's tool_name string to the actual Python function.
# When Claude requests tool_name="get_price_and_metrics", we call
# the real Python function and return the result.
# ══════════════════════════════════════════════════════════════════════════════

def dispatch_tool(tool_name: str, tool_input: dict, context: dict) -> dict:
    """
    Call the real Python tool function based on Claude's tool_use request.

    context holds state across tool calls — specifically the headlines
    from get_recent_news that get passed to sentiment_score.
    """

    if tool_name == "get_price_and_metrics":
        return get_price_and_metrics(tool_input["ticker"])

    elif tool_name == "get_recent_news":
        result = get_recent_news(
            ticker=tool_input["ticker"],
            company_name=tool_input.get("company_name"),
        )
        # Store headlines so Claude can pass them to sentiment_score
        if result.get("data"):
            context["headlines"] = result["data"].get("headlines_for_sentiment", [])
            context["company_name"] = (
                result["data"].get("company", {}).get("company_name") or
                tool_input.get("company_name") or
                tool_input["ticker"]
            )
        return result

    elif tool_name == "sentiment_score":
        headlines = tool_input.get("headlines") or context.get("headlines", [])
        return sentiment_score(
            headlines=headlines,
            ticker=tool_input.get("ticker"),
        )

    elif tool_name == "get_financials_history":
        return get_financials_history(tool_input["ticker"])

    elif tool_name == "get_peer_comparison":
        return get_peer_comparison(
            ticker=tool_input["ticker"],
            custom_peers=tool_input.get("custom_peers"),
        )

    elif tool_name == "get_sec_filing_summary":
        return get_sec_filing_summary(tool_input["ticker"])

    elif tool_name == "get_earnings_call_transcript":
        return get_earnings_call_transcript(tool_input["ticker"])

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# This is Claude's operating context. It tells Claude what role it plays,
# what tools it has, and what the expected output is.
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an institutional equity research analyst AI agent.

Your task is to conduct comprehensive stock research for a given company by calling the available tools in a logical sequence. You have 7 specialist tools. Use all of them.

TOOL CALLING ORDER:
1. get_price_and_metrics      — always first, establishes valuation baseline
2. get_recent_news            — news context and event detection
3. sentiment_score            — pass headlines from step 2
4. get_financials_history     — 8 quarters of fundamentals
5. get_peer_comparison        — relative valuation vs sector peers
6. get_sec_filing_summary     — qualitative filing analysis
7. get_earnings_call_transcript — management tone and guidance

After all tools have run, produce a structured research brief.

RULES:
- Call every tool exactly once. Do not skip any.
- Do not hallucinate data. Only use what the tools return.
- If a tool returns an error or partial data, note it and continue.
- After all tools are done, write the final brief as valid JSON only.
- The brief JSON must have these top-level keys:
  company_snapshot, valuation, financials, competitive_position,
  sentiment, management_signals, risks, analyst_summary, data_quality
"""


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHESIS PROMPT
# After all tools have run, this prompt instructs Claude to combine
# everything into the final structured research brief.
# ══════════════════════════════════════════════════════════════════════════════

def build_synthesis_prompt(ticker: str, company_name: str, tool_results: dict) -> str:
    """
    Build the final synthesis prompt that generates the research brief.
    We pass all accumulated tool outputs in a single structured block.
    """
    # Trim tool outputs to avoid hitting context limits
    # Each tool output is trimmed to its most important fields
    summary = {}

    for tool_name, result in tool_results.items():
        data = result.get("data") if result else None
        if not data:
            summary[tool_name] = {"status": "failed", "error": result.get("validation_results", {}).get("error_message", "No data")}
            continue

        confidence = result.get("confidence_assessment", {})

        if tool_name == "get_price_and_metrics":
            summary[tool_name] = {
                "identity":   data.get("identity"),
                "price":      data.get("price"),
                "size":       data.get("size"),
                "valuation":  data.get("valuation_multiples"),
                "behaviour":  data.get("market_behaviour"),
                "flags":      data.get("flags"),
                "confidence": confidence.get("score_pct"),
            }

        elif tool_name == "get_recent_news":
            summary[tool_name] = {
                "summary": data.get("summary"),
                "top_headlines": [
                    {"title": a.get("title"), "source_tier": a.get("source_tier"),
                     "event_types": a.get("event_types"), "is_material": a.get("is_material")}
                    for a in (data.get("articles") or [])[:8]
                ],
                "flags": data.get("flags"),
                "confidence": confidence.get("score_pct"),
            }

        elif tool_name == "sentiment_score":
            summary[tool_name] = {
                "aggregate":          data.get("aggregate"),
                "negative_themes":    data.get("negative_themes"),
                "high_conviction":    [{"headline": h.get("headline"), "label": h.get("label"), "score": h.get("score")}
                                       for h in (data.get("high_conviction_signals") or [])[:5]],
                "agent_summary_line": data.get("agent_summary_line"),
                "flags":              data.get("flags"),
                "confidence":         confidence.get("score_pct"),
                "model_used":         result.get("metadata", {}).get("model_used"),
            }

        elif tool_name == "get_financials_history":
            summary[tool_name] = {
                "currency":       data.get("identity", {}).get("currency"),
                "quarters":       data.get("identity", {}).get("quarters_returned"),
                "ttm":            data.get("ttm_summary"),
                "trends":         data.get("trend_analysis"),
                "latest_quarter": (data.get("quarterly_data") or [{}])[0],
                "flags":          data.get("flags"),
                "confidence":     confidence.get("score_pct"),
            }

        elif tool_name == "get_peer_comparison":
            summary[tool_name] = {
                "peers":        data.get("peer_group"),
                "medians":      data.get("medians"),
                "rankings":     {k: v for k, v in (data.get("rankings") or {}).items()
                                 if k in ["pe_forward","ev_ebitda","gross_margin",
                                          "operating_margin","revenue_growth","roe","debt_to_equity"]},
                "positioning":  data.get("positioning"),
                "comp_table":   [(r.get("ticker"), r.get("valuation"), r.get("profitability"), r.get("growth"))
                                 for r in (data.get("comp_table") or [])[:6]],
                "flags":        data.get("flags"),
                "confidence":   confidence.get("score_pct"),
            }

        elif tool_name == "get_sec_filing_summary":
            sec_sections = data.get("sections") or {}
            summary[tool_name] = {
                "filing":     data.get("filing_metadata"),
                "risk_factors": (sec_sections.get("risk_factors") or "")[:1000],
                "mda":          (sec_sections.get("mda") or "")[:1000],
                "business":     (sec_sections.get("business_description") or "")[:500],
                "red_flags":    data.get("red_flags"),
                "metrics":      data.get("mentioned_metrics"),
                "flags":        data.get("flags"),
                "confidence":   confidence.get("score_pct"),
            }

        elif tool_name == "get_earnings_call_transcript":
            summary[tool_name] = {
                "identity":     data.get("identity"),
                "tone":         data.get("analysis", {}).get("tone"),
                "themes":       data.get("analysis", {}).get("key_themes"),
                "guidance":     data.get("analysis", {}).get("guidance_mentions"),
                "repeated":     data.get("analysis", {}).get("repeated_phrases"),
                "red_flags":    data.get("analysis", {}).get("red_flags"),
                "deflections":  [d.get("phrase") for d in (data.get("analysis", {}).get("deflections_detected") or [])],
                "agent_summary": data.get("agent_summary_line"),
                "flags":        data.get("flags"),
                "confidence":   confidence.get("score_pct"),
            }

    return f"""All research tools have completed for {ticker} ({company_name}).

Tool outputs summary:
{json.dumps(summary, indent=2, default=str)}

Now produce the final research brief as a single valid JSON object.
No markdown, no explanation, no preamble. Only the JSON object.

Required structure:
{{
  "company_snapshot": {{
    "ticker": "",
    "company_name": "",
    "sector": "",
    "industry": "",
    "exchange": "",
    "current_price": 0.0,
    "day_change_pct": 0.0,
    "market_cap": "",
    "week_52_position_pct": 0.0,
    "beta": 0.0
  }},
  "valuation": {{
    "pe_trailing": 0.0,
    "pe_forward": 0.0,
    "ev_ebitda": 0.0,
    "price_to_sales": 0.0,
    "price_to_book": 0.0,
    "peer_median_pe_forward": 0.0,
    "peer_median_ev_ebitda": 0.0,
    "valuation_quality_label": ""
  }},
  "financials": {{
    "currency": "",
    "ttm_revenue_m": 0.0,
    "ttm_net_income_m": 0.0,
    "ttm_fcf_m": 0.0,
    "ttm_ebitda_m": 0.0,
    "ttm_net_margin_pct": 0.0,
    "latest_net_debt_m": 0.0,
    "revenue_yoy_growth_pct": 0.0,
    "revenue_trend": "",
    "gross_margin_trend": "",
    "operating_margin_trend": "",
    "revenue_acceleration": ""
  }},
  "competitive_position": {{
    "peers_identified": [],
    "strengths_vs_peers": [],
    "weaknesses_vs_peers": [],
    "analyst_summary": ""
  }},
  "sentiment": {{
    "score": 0.0,
    "label": "",
    "positive_count": 0,
    "negative_count": 0,
    "total_headlines": 0,
    "negative_themes": [],
    "summary_line": ""
  }},
  "management_signals": {{
    "transcript_date": "",
    "dominant_tone": "",
    "tone_interpretation": "",
    "top_themes": [],
    "guidance_count": 0,
    "red_flags": [],
    "deflections": [],
    "summary_line": ""
  }},
  "risks": [],
  "analyst_summary": "",
  "data_quality": {{
    "tool_01_price": 0,
    "tool_02_news": 0,
    "tool_03_sentiment": 0,
    "tool_04_financials": 0,
    "tool_05_peers": 0,
    "tool_06_sec": 0,
    "tool_07_transcript": 0
  }}
}}

analyst_summary must be 3-5 sentences written as an institutional analyst would write them.
risks must be a flat list of strings — one risk per string, maximum 10.
All numeric fields must be numbers not strings. Use null for unavailable data."""


# ══════════════════════════════════════════════════════════════════════════════
# AGENT LOOP
# This is the core of the agent.
#
# The loop works like this:
# 1. Send messages to Claude with tool definitions
# 2. Claude responds with either a tool_use block or a text response
# 3. If tool_use: call the real function, append tool_result to messages, loop
# 4. If text (no more tool calls): Claude is done reasoning, exit loop
# 5. Run synthesis call to generate final JSON brief
# ══════════════════════════════════════════════════════════════════════════════

async def run_agent(
    ticker: str,
    company_name: Optional[str] = None,
    request_id: Optional[str] = None,
    ws_callback: Optional[Callable] = None,
) -> dict:
    """
    Run the full stock research agent for a given ticker.

    Args:
        ticker:       Stock ticker e.g. "AAPL"
        company_name: Optional full name e.g. "Apple Inc."
        request_id:   For WebSocket progress tracking (backend use)
        ws_callback:  Async function to stream progress events to frontend

    Returns:
        dict with keys: brief (structured JSON), tool_results, metadata
    """

    ticker       = ticker.strip().upper()
    start_time   = time.time()
    tool_results = {}     # accumulates all tool outputs
    context      = {}     # carries state between tool calls (e.g. headlines)
    tools_called = []     # tracks order and timing

    # ── Helper: send WebSocket event if callback provided ─────────────────────
    async def emit(event: dict):
        if ws_callback:
            try:
                await ws_callback(event)
            except Exception:
                pass  # never let WebSocket errors crash the agent

    await emit({"event": "agent_start", "ticker": ticker, "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()})


    # ── Agent loop ────────────────────────────────────────────────────────────
    # Max 12 iterations — 7 tools + small buffer for Gemini's reasoning turns
    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[GEMINI_TOOLS],
        ),
    )

    user_message = (
        f"Research {ticker}"
        + (f" ({company_name})" if company_name else "")
        + ". Use all 7 tools in the correct order to conduct comprehensive research."
    )

    response = await asyncio.to_thread(chat.send_message, user_message)

    for iteration in range(12):

        if not response.candidates:
            print(f"  [debug] no candidates returned, prompt_feedback: {response.prompt_feedback}")
            parts = []
        else:
            content = response.candidates[0].content
            if content is None or not content.parts:
                print(f"  [debug] empty content, finish_reason: {response.candidates[0].finish_reason}")
                parts = []
            else:
                parts = content.parts

        # ── Check if Gemini is done (no function calls in response) ───────────
        has_tool_call = any(getattr(part, "function_call", None) and part.function_call.name for part in parts)
        if not has_tool_call:
            break

        # ── Process all function_call parts in this response ──────────────────
        tool_results_for_this_turn = []

        for part in parts:
            if not getattr(part, "function_call", None) or not part.function_call.name:
                continue

            tool_name  = part.function_call.name
            tool_input = dict(part.function_call.args)  # proto map → plain dict
            tool_id    = tool_name  # Gemini doesn't use IDs; name is sufficient

            tool_start = time.time()

            await emit({
                "event":        "tool_start",
                "tool":         tool_name,
                "tool_number":  len(tools_called) + 1,
                "total_tools":  7,
                "timestamp":    datetime.utcnow().isoformat(),
            })

            # ── Call the real tool (in thread so async loop stays free) ───────
            try:
                result = await asyncio.to_thread(
                    dispatch_tool, tool_name, tool_input, context
                )
            except Exception as e:
                result = {"error": str(e), "data": None}

            duration_ms = int((time.time() - tool_start) * 1000)

            # Store result
            tool_results[tool_name] = result
            tools_called.append({
                "tool":        tool_name,
                "duration_ms": duration_ms,
                "success":     result.get("data") is not None,
            })

            # Build a short summary for the WebSocket event
            summary = _build_tool_summary(tool_name, result)

            await emit({
                "event":       "tool_complete",
                "tool":        tool_name,
                "tool_number": len(tools_called),
                "duration_ms": duration_ms,
                "summary":     summary,
                "timestamp":   datetime.utcnow().isoformat(),
            })

            # ── Prepare tool_result for Claude ────────────────────────────────
            # We don't pass the full result back to Claude — just the key data
            # and flags. This keeps the context window manageable.
            trimmed = _trim_for_claude(tool_name, result)

            tool_results_for_this_turn.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response={"result": trimmed},
                    )
                )
            )

        # Send all tool results back to Gemini and get next response
        if tool_results_for_this_turn:
            response = await asyncio.to_thread(
                chat.send_message, tool_results_for_this_turn
            )
        else:
            break

    # ── Synthesis: generate the final research brief ──────────────────────────
    await emit({"event": "synthesis_start", "timestamp": datetime.utcnow().isoformat()})

    if not company_name:
        company_name = context.get("company_name", ticker)

    brief = await _synthesise(ticker, company_name, tool_results)

    total_duration = int((time.time() - start_time) * 1000)

    await emit({
        "event":          "complete",
        "ticker":         ticker,
        "request_id":     request_id,
        "total_duration": total_duration,
        "tools_called":   len(tools_called),
        "timestamp":      datetime.utcnow().isoformat(),
    })

    return {
        "brief":        brief,
        "tool_results": tool_results,
        "metadata": {
            "ticker":         ticker,
            "company_name":   company_name,
            "tools_called":   tools_called,
            "total_duration_ms": total_duration,
            "model":          MODEL,
            "completed_at":   datetime.utcnow().isoformat(),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHESIS
# Separate Claude call at the end.
# All tool outputs → one structured JSON brief.
# ══════════════════════════════════════════════════════════════════════════════

async def _synthesise(ticker: str, company_name: str, tool_results: dict) -> dict:
    """
    Final Claude call: convert all tool outputs into the structured research brief.
    Uses a fresh conversation — no tool definitions, just synthesis.
    """
    prompt = build_synthesis_prompt(ticker, company_name, tool_results)

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are an institutional equity research analyst. "
                "Produce research briefs as valid JSON only. "
                "No markdown fences, no explanation, just the JSON object."
            ),
            response_mime_type="application/json",
            max_output_tokens=8192,
        ),
    )

    if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
        return {
            "error":        "synthesis_empty_response",
            "finish_reason": str(response.candidates[0].finish_reason) if response.candidates else "no_candidates",
            "ticker":       ticker,
            "company_name": company_name,
        }

    raw_text = response.text.strip()

    # Strip markdown fences if Claude adds them anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Claude returned malformed JSON — return what we have with an error flag
        return {
            "error":        "synthesis_json_parse_failed",
            "raw_response": raw_text[:2000],
            "ticker":       ticker,
            "company_name": company_name,
        }


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _trim_for_claude(tool_name: str, result: dict) -> dict:
    """
    Return a trimmed version of tool output to pass back to Claude.
    We keep the flags, key metrics, and confidence — not the full raw data.
    This keeps context window usage low across the 7-tool conversation.
    """
    if not result or not result.get("data"):
        return {
            "status":    "failed",
            "error":     result.get("validation_results", {}).get("error_message", "No data") if result else "Tool failed",
            "tool":      tool_name,
        }

    data       = result["data"]
    confidence = result.get("confidence_assessment", {})

    base = {
        "status":     "success",
        "confidence": confidence.get("label"),
        "flags":      data.get("flags", []),
    }

    if tool_name == "get_price_and_metrics":
        base.update({
            "ticker":      data.get("identity", {}).get("ticker"),
            "company":     data.get("identity", {}).get("company_name"),
            "sector":      data.get("identity", {}).get("sector"),
            "price":       data.get("price", {}).get("current"),
            "day_change":  data.get("price", {}).get("day_change_pct"),
            "market_cap":  data.get("size", {}).get("market_cap_formatted"),
            "pe_trailing": data.get("valuation_multiples", {}).get("pe_trailing"),
            "pe_forward":  data.get("valuation_multiples", {}).get("pe_forward"),
            "ev_ebitda":   data.get("valuation_multiples", {}).get("ev_to_ebitda"),
        })

    elif tool_name == "get_recent_news":
        summary = data.get("summary", {})
        base.update({
            "articles_found":  summary.get("total_articles_retrieved"),
            "material_events": summary.get("material_event_count"),
            "event_breakdown": summary.get("event_type_breakdown"),
            "dominant_themes": summary.get("dominant_themes"),
        })

    elif tool_name == "sentiment_score":
        agg = data.get("aggregate", {})
        base.update({
            "score":           agg.get("score"),
            "label":           agg.get("overall_label"),
            "positive":        agg.get("positive_count"),
            "negative":        agg.get("negative_count"),
            "total":           agg.get("total"),
            "negative_themes": data.get("negative_themes"),
            "summary":         data.get("agent_summary_line"),
        })

    elif tool_name == "get_financials_history":
        ttm   = data.get("ttm_summary", {})
        trend = data.get("trend_analysis", {})
        base.update({
            "ttm_revenue_m":    ttm.get("ttm_revenue_m"),
            "ttm_net_income_m": ttm.get("ttm_net_income_m"),
            "ttm_fcf_m":        ttm.get("ttm_free_cash_flow_m"),
            "ttm_ebitda_m":     ttm.get("ttm_ebitda_m"),
            "net_debt_m":       ttm.get("latest_net_debt_m"),
            "revenue_yoy":      trend.get("revenue", {}).get("yoy_growth_pct"),
            "revenue_dir":      trend.get("revenue", {}).get("4q_trend_direction"),
            "margin_dir":       trend.get("operating_margin", {}).get("4q_trend_direction"),
            "acceleration":     trend.get("revenue_acceleration"),
        })

    elif tool_name == "get_peer_comparison":
        pos = data.get("positioning", {})
        base.update({
            "peers":             data.get("peer_group", {}).get("peers_identified"),
            "valuation_quality": pos.get("valuation_quality_label"),
            "strengths":         pos.get("strengths_vs_peers"),
            "weaknesses":        pos.get("weaknesses_vs_peers"),
            "pe_fwd_rank":       data.get("rankings", {}).get("pe_forward", {}).get("vs_median_label"),
            "margin_rank":       data.get("rankings", {}).get("operating_margin", {}).get("vs_median_label"),
        })

    elif tool_name == "get_sec_filing_summary":
        base.update({
            "form_type":   data.get("filing_metadata", {}).get("form_type"),
            "filed_date":  data.get("filing_metadata", {}).get("filed_date"),
            "red_flags":   data.get("red_flags"),
            "sections_ok": [k for k, v in (data.get("sections") or {}).items() if v],
        })

    elif tool_name == "get_earnings_call_transcript":
        analysis = data.get("analysis", {})
        base.update({
            "transcript_date": data.get("identity", {}).get("transcript_date"),
            "source":          data.get("identity", {}).get("source"),
            "tone":            analysis.get("tone", {}).get("dominant_tone"),
            "themes":          [t.get("theme") for t in (analysis.get("key_themes") or [])[:3]],
            "guidance_count":  len(analysis.get("guidance_mentions") or []),
            "red_flags":       analysis.get("red_flags"),
            "deflections":     len(analysis.get("deflections_detected") or []),
            "summary":         data.get("agent_summary_line"),
        })

    return base


def _build_tool_summary(tool_name: str, result: dict) -> str:
    """Build a short one-line summary for WebSocket progress events."""
    if not result or not result.get("data"):
        return "No data returned"

    data = result["data"]

    if tool_name == "get_price_and_metrics":
        price = data.get("price", {}).get("current")
        mc    = data.get("size", {}).get("market_cap_formatted")
        pe    = data.get("valuation_multiples", {}).get("pe_forward")
        return f"Price: ${price}, Market Cap: {mc}, Forward PE: {pe}x"

    elif tool_name == "get_recent_news":
        n = data.get("summary", {}).get("total_articles_retrieved", 0)
        m = data.get("summary", {}).get("material_event_count", 0)
        return f"{n} articles, {m} material events"

    elif tool_name == "sentiment_score":
        agg = data.get("aggregate", {})
        return f"Sentiment: {agg.get('overall_label')} ({agg.get('score', 0):.2f}/1.0)"

    elif tool_name == "get_financials_history":
        ttm = data.get("ttm_summary", {})
        rev = ttm.get("ttm_revenue_m")
        ni  = ttm.get("ttm_net_income_m")
        return f"TTM Revenue: ${rev}M, TTM Net Income: ${ni}M"

    elif tool_name == "get_peer_comparison":
        pos = data.get("positioning", {})
        vq  = pos.get("valuation_quality_label", "N/A")
        n   = data.get("peer_group", {}).get("peer_count", 0)
        return f"Valuation: {vq}, {n} peers benchmarked"

    elif tool_name == "get_sec_filing_summary":
        filing = data.get("filing_metadata", {})
        rf     = len(data.get("red_flags") or [])
        return f"{filing.get('form_type')} filed {filing.get('filed_date')}, {rf} red flags"

    elif tool_name == "get_earnings_call_transcript":
        tone = data.get("analysis", {}).get("tone", {}).get("dominant_tone", "N/A")
        src  = data.get("identity", {}).get("source", "N/A")
        return f"Tone: {tone}, Source: {src}"

    return "Complete"


# ══════════════════════════════════════════════════════════════════════════════
# SYNC WRAPPER — for terminal use and testing
# ══════════════════════════════════════════════════════════════════════════════

def run_agent_sync(ticker: str, company_name: Optional[str] = None) -> dict:
    """
    Synchronous wrapper around run_agent for terminal and testing use.
    Prints live progress to stdout.
    """

    async def print_callback(event: dict):
        ev = event.get("event")
        if ev == "agent_start":
            print(f"\n{'='*60}")
            print(f"  STOCK RESEARCH AGENT — {event.get('ticker')}")
            print(f"{'='*60}")
        elif ev == "tool_start":
            print(f"\n  [{event.get('tool_number')}/7] Running {event.get('tool')}...", end="", flush=True)
        elif ev == "tool_complete":
            print(f" done ({event.get('duration_ms')}ms)")
            print(f"         → {event.get('summary')}")
        elif ev == "synthesis_start":
            print(f"\n  [8/8] Synthesising research brief...", end="", flush=True)
        elif ev == "complete":
            print(f" done")
            print(f"\n  Total time: {event.get('total_duration')}ms")
        elif ev == "error":
            print(f"\n  ⚠ Error in {event.get('tool')}: {event.get('message')}")

    return asyncio.run(run_agent(ticker, company_name, ws_callback=print_callback))


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT — terminal use
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent_core.py <TICKER> [company_name]")
        print("Examples:")
        print("  python agent_core.py AAPL")
        print("  python agent_core.py TSLA 'Tesla Inc'")
        sys.exit(1)

    ticker_arg  = sys.argv[1]
    company_arg = sys.argv[2] if len(sys.argv) > 2 else None

    result = run_agent_sync(ticker_arg, company_arg)

    print(f"\n{'='*60}")
    print("  RESEARCH BRIEF")
    print(f"{'='*60}")
    print(json.dumps(result["brief"], indent=2, default=str))

    print(f"\n{'='*60}")
    print("  TOOL PERFORMANCE")
    print(f"{'='*60}")
    for t in result["metadata"]["tools_called"]:
        status = "✓" if t["success"] else "✗"
        print(f"  {status} {t['tool']:45} {t['duration_ms']}ms")