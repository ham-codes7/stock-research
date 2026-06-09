//BASE URL-SECTION 1
Development:  http://localhost:8000
All requests: Content-Type: application/json

//START A RESEARCH REQUEST - SECTION 2
POST /api/research

Request body:
{
  "ticker": "AAPL",
  "company_name": "Apple Inc."   ← optional
}

Success response (200):
{
  "request_id": "uuid-1234",
  "ticker": "AAPL",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}

Error response (400):
{
  "error": {
    "code": "INVALID_TICKER",
    "message": "Ticker cannot be empty"
  }
}

//GET COMPLETED RESULT -SECTION 3
GET /api/research/{request_id}

Success response (200):
{
  "request_id": "uuid-1234",
  "ticker": "AAPL",
  "status": "complete",
  "brief": {
    "company_snapshot": {
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "current_price": 211.45,
      "market_cap": "$3.18T",
      "day_change_pct": 1.48,
      "sector": "Technology"
    },
    "valuation": {
      "pe_forward": 27.8,
      "ev_ebitda": 22.3,
      "valuation_quality_label": "FAIRLY_PRICED"
    },
    "sentiment": {
      "score": 0.68,
      "label": "BULLISH",
      "positive_count": 8,
      "negative_count": 2,
      "total_headlines": 12
    },
    "risks": [
      "ELEVATED_PE — forward PE above sector median",
      "Revenue growth below peer median"
    ],
    "analyst_summary": "Apple delivered..."
  }
}

Error response (404):
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Request uuid-1234 not found"
  }
}

//WEB-SOCKET PROGRESS STREAM - SECTION 4
WS /ws/progress/{request_id}

Connect immediately after POST /api/research.

Messages arrive as JSON. Four event types:

1. Tool started:
{
  "event": "tool_start",
  "tool": "get_price_and_metrics",
  "tool_number": 1,
  "total_tools": 7
}

2. Tool finished:
{
  "event": "tool_complete",
  "tool": "get_price_and_metrics",
  "tool_number": 1,
  "duration_ms": 850,
  "summary": "Price: $211.45, Market Cap: $3.18T"
}

3. All done:
{
  "event": "complete",
  "request_id": "uuid-1234"
}

4. A tool errored (agent continues):
{
  "event": "error",
  "tool": "get_recent_news",
  "message": "NewsAPI unavailable, using fallback"
}

//HEALTH CHECK - SECTION 5
GET /api/health

Response (200):
{
  "status": "ok",
  "ml_server_online": true,
  "timestamp": "2024-01-15T10:30:00Z"
}

//ERROR FORMAT - SECTION 6
{
  "error": {
    "code": "ERROR_CODE_IN_CAPS",
    "message": "Human readable explanation"
  }
}