# TEARSHEET — Agentic Equity Research (Frontend)

One ticker in → a live 7-tool agent pipeline → a standardized, **auditable**
research brief out. Built for the "agentic stock research for junior analysts"
project, and designed around the judge feedback: trust, provenance, data
freshness, and honest uncertainty.

## Run it (no build step)

Single self-contained `index.html` (React via CDN) + `mockData.js`.

```bash
cd stock-research-frontend
python -m http.server 5050
# open http://localhost:5050
```
(Double-clicking `index.html` also works.)

## Files

- `index.html` — the app (UI + the live-pipeline state machine).
- `mockData.js` — **single source of truth for data.** Components read only
  from here. Matches the API contract's brief schema.
- `README.md` — this file.

## What it shows

- **Ticker input** — try `TSLA`, `AAPL`, `NVDA`; any other symbol generates a
  consistent demo brief.
- **Live agent pipeline** — the 7 tools run in sequence, each reporting its own
  **confidence rating** as it completes. Tools that degrade (e.g. a news-feed
  timeout) show a warning instead of a hard failure — the agent continues.
- **The brief** — company snapshot, a **Confidence-by-Source** bar chart, a
  **Data Quality & Limitations** panel (`data_quality.flags` +
  `missing_information`), key metrics, sentiment gauge, risks, strengths, and an
  analyst summary. Every section is labelled with the tool that produced it.

## Connecting the real backend (the "one URL" swap)

The async contract is already wired in `index.html`:

```js
const USE_BACKEND = false;          // flip to true
const API_URL = "http://localhost:8000";
const WS_URL  = "ws://localhost:8000";
```

Live flow:
1. `POST {API_URL}/api/research { ticker }` → `request_id`
2. `WS {WS_URL}/ws/progress/{request_id}` → `tool_start` / `tool_complete` /
   `error` / `complete` events (drive the live pipeline)
3. `GET {API_URL}/api/research/{request_id}` → the brief

The mock emulates all three, so the UI is identical with or without the
backend. If the API errors, it falls back to mock data so demos never break.

### Brief schema (in `mockData.js`)

Mirrors contract section 3, plus the two fields the team added:
`confidence_assessment` (per-tool rating array) and `data_quality`
(`overall_score`, `flags[]`, `missing_information[]`).

### Moving to a Vite/CRA project

`mockData.js` is currently an IIFE that sets `window.MOCK` (so it works as a
plain `<script>`). To import it as an ES module, replace the IIFE wrapper with
`export const TOOLS = ...` / `export function getResearch(...)` — the data
objects stay identical.

> Demo figures are simulated mock data. Not investment advice.
