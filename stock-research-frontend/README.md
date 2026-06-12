# Stock Research Frontend

React frontend for the Stock Research AI Agent. Connects to your backend via REST and WebSocket.

## Requirements

- Node.js 18+
- Backend running at `http://localhost:8000` (see `stock-research-agent/`)

## Setup

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Build for production

```bash
npm run build
npm run preview
```

## How it works

1. Enter a ticker (e.g. `AAPL`) and hit **Run Research**
2. The frontend calls `POST /api/research` to start the agent
3. It immediately connects to `WS /ws/progress/{request_id}` for live tool-by-tool progress
4. Falls back to polling `GET /api/research/{request_id}` if WebSocket is unavailable
5. Once complete, renders the full research brief with:
   - Company snapshot & valuation metrics
   - TTM financials
   - Sentiment score (circular gauge)
   - Management signals & tone
   - Competitive positioning
   - Key risks
   - Per-tool data quality / confidence bars

## API contract

The frontend expects the backend defined in `API_CONTRACT.md`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/research` | POST | Start research job |
| `/api/research/{id}` | GET | Poll for result |
| `/ws/progress/{id}` | WS | Live progress stream |
| `/api/health` | GET | Health check |

## Environment

To point at a different backend, edit `vite.config.js` proxy targets or update `BASE_URL` in `src/components/StockResearchAgent.jsx`.

## Project structure

```
stock-research-frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── components/
│   │   └── StockResearchAgent.jsx   ← main component
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css                    ← CSS variables + dark mode
├── index.html
├── vite.config.js                   ← proxy config for /api and /ws
└── package.json
```
