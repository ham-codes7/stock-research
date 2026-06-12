# API Contract — Stock Research AI Agent

## Section 1: Base URL

```
Development:  http://localhost:8000
All requests: Content-Type: application/json
```

---

## Section 2: Start a Research Request

```
POST /api/research
```

**Request body:**
```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc."   // optional
}
```

**Success response (200):**
```json
{
  "request_id": "uuid-1234",
  "ticker": "AAPL",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Error response (400):**
```json
{
  "error": {
    "code": "INVALID_TICKER",
    "message": "Ticker cannot be empty"
  }
}
```

---

## Section 3: Get Research Result

```
GET /api/research/{request_id}
```

**Status values:** `"pending"` | `"complete"` | `"error"`

**Success response (200) — status: "complete":**
```json
{
  "request_id": "uuid-1234",
  "ticker": "AAPL",
  "status": "complete",
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:30:58Z",
  "brief": {
    "company_snapshot": {
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "sector": "Technology",
      "current_price": 211.45,
      "market_cap": "$3.18T",
      "day_change_pct": 1.48,
      "beta": 1.21
    },
    "valuation": {
      "pe_trailing": 29.4,
      "pe_forward": 27.8,
      "ev_ebitda": 22.3,
      "price_to_sales": 7.9,
      "peer_median_pe_forward": 26.1,
      "valuation_quality_label": "FAIRLY_PRICED"
    },
    "financials": {
      "ttm_revenue_m": 391035,
      "ttm_net_income_m": 96995,
      "ttm_fcf_m": 99584,
      "ttm_ebitda_m": 134661,
      "revenue_yoy_growth_pct": 4.9,
      "revenue_trend": "STEADY_GROWTH"
    },
    "competitive_position": {
      "peers_identified": ["MSFT", "GOOGL", "DELL", "HPQ"],
      "strengths_vs_peers": ["Higher margins", "Stronger brand loyalty"],
      "weaknesses_vs_peers": ["Slower revenue growth than MSFT"],
      "analyst_summary": "Apple maintains premium positioning relative to hardware peers..."
    },
    "sentiment": {
      "score": 0.68,
      "label": "BULLISH",
      "positive_count": 8,
      "negative_count": 2,
      "negative_themes": ["Supply chain concerns in China"],
      "summary_line": "Recent coverage skews positive, driven by strong earnings reaction."
    },
    "management_signals": {
      "dominant_tone": "CONFIDENT",
      "top_themes": ["AI integration", "Services growth"],
      "guidance_count": 3,
      "red_flags": [],
      "deflections": ["Avoided direct question on China unit sales"]
    },
    "risks": [
      "ELEVATED_PE — forward PE above sector median",
      "Revenue growth below peer median"
    ],
    "analyst_summary": "Apple delivered a solid quarter with services growth offsetting hardware softness...",
    "data_quality": {
      "tool_01_price": 95,
      "tool_02_news": 80,
      "tool_03_financials": 92,
      "tool_04_peer_comparison": 88,
      "tool_05_sec_filing": 75,
      "tool_06_sentiment": 85,
      "tool_07_earnings_call": 70
    }
  }
}
```

**Response — status: "pending" (request still processing):**
```json
{
  "request_id": "uuid-1234",
  "ticker": "AAPL",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": null,
  "brief": null
}
```

**Error response (404):**
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Request uuid-1234 not found"
  }
}
```

---

## Section 4: WebSocket Progress Stream

```
WS /ws/progress/{request_id}
```

Connect immediately after `POST /api/research`. Messages arrive as JSON. Four event types:

**1. Tool started:**
```json
{
  "event": "tool_start",
  "tool": "get_price_and_metrics",
  "tool_number": 1,
  "total_tools": 7
}
```

**2. Tool finished:**
```json
{
  "event": "tool_complete",
  "tool": "get_price_and_metrics",
  "tool_number": 1,
  "duration_ms": 850,
  "summary": "Price: $211.45, Market Cap: $3.18T"
}
```

**3. All done:**
```json
{
  "event": "complete",
  "request_id": "uuid-1234"
}
```

**4. A tool errored (agent continues, falls back):**
```json
{
  "event": "error",
  "tool": "get_recent_news",
  "message": "NewsAPI unavailable, using fallback"
}
```

---

## Section 5: Health Check

```
GET /api/health
```

**Response (200):**
```json
{
  "status": "ok",
  "ml_server_online": true,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Section 6: Standard Error Format

```json
{
  "error": {
    "code": "ERROR_CODE_IN_CAPS",
    "message": "Human readable explanation"
  }
}
```

---

## Changelog

- **v1.1**: Added `completed_at` field (null until status is "complete"). Added full `brief` schema — `financials`, `competitive_position`, `management_signals`, `data_quality` were missing from the previous example. Added explicit `status: "pending"` response shape and `"error"` as a valid status value.