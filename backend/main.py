from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import asyncio
import json
import requests
from backend.database import get_db, ResearchRequest
from backend.websocket_manager import manager
from agent_core import run_agent

app = FastAPI(title="Stock Research Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def error_response(code: str, message: str, status_code: int):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}}
    )

def format_datetime(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# --- Health ---
@app.get("/api/health")
def health():
    ml_online = False
    try:
        r = requests.get("http://localhost:8001/health", timeout=2)
        ml_online = r.status_code == 200
    except:
        pass
    return {
        "status": "ok",
        "ml_server_online": ml_online,
        "timestamp": format_datetime(datetime.now(timezone.utc))
    }

# --- Start research ---
class ResearchInput(BaseModel):
    ticker: str
    company_name: Optional[str] = None

@app.post("/api/research")
def start_research(body: ResearchInput, db: Session = Depends(get_db)):
    if not body.ticker or not body.ticker.strip():
        return error_response("INVALID_TICKER", "Ticker cannot be empty", 400)

    request = ResearchRequest(
        ticker=body.ticker.upper(),
        company=body.company_name
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    return {
        "request_id": request.id,
        "ticker": request.ticker,
        "status": request.status,
        "created_at": format_datetime(request.created_at)
    }

# --- Get result ---
@app.get("/api/research/{request_id}")
def get_research(request_id: str, db: Session = Depends(get_db)):
    request = db.query(ResearchRequest).filter(
        ResearchRequest.id == request_id
    ).first()

    if not request:
        return error_response("NOT_FOUND", f"Request {request_id} not found", 404)

    brief = None
    if request.brief_json:
        brief = json.loads(request.brief_json)

    return {
        "request_id": request.id,
        "ticker": request.ticker,
        "status": request.status,
        "brief": brief,
        "created_at": format_datetime(request.created_at)
    }

# --- WebSocket ---
@app.websocket("/ws/progress/{request_id}")
async def websocket_progress(websocket: WebSocket, request_id: str):
    await manager.connect(request_id, websocket)

    db = next(get_db())
    request = db.query(ResearchRequest).filter(
        ResearchRequest.id == request_id
    ).first()

    if not request:
        await websocket.close()
        return

    try:
        request.status = "running"
        db.commit()

        result = await run_agent(
            ticker=request.ticker,
            company_name=request.company,
            request_id=request_id,
            ws_callback=manager.send_wrapper(request_id)
        )

        request.brief_json = json.dumps(result["brief"])
        request.status = "complete"
        db.commit()

    except Exception as e:
        request.status = "failed"
        db.commit()
        await manager.send(request_id, {
            "event": "error",
            "message": str(e)
        })

    finally:
        manager.disconnect(request_id)
        db.close()
        