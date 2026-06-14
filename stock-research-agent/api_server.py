import os
import sys
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent_core import run_agent

app = FastAPI(title="Stock Research AI Agent API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for research requests
research_store: Dict[str, Dict[str, Any]] = {}

# Active WebSocket connections by request_id
active_websockets: Dict[str, List[WebSocket]] = {}

# Event history by request_id (to replay to late-connecting clients)
event_history: Dict[str, List[Dict[str, Any]]] = {}

class ResearchRequest(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    request_id: Optional[str] = None

# Async helper to broadcast events
async def broadcast_event(request_id: str, event: dict):
    # Store event in history
    if request_id not in event_history:
        event_history[request_id] = []
    event_history[request_id].append(event)
    
    # Broadcast to all connected WebSockets
    sockets = active_websockets.get(request_id, [])
    if sockets:
        async def send_to_socket(ws: WebSocket):
            try:
                await ws.send_json(event)
            except Exception:
                pass
        await asyncio.gather(*(send_to_socket(ws) for ws in sockets), return_exceptions=True)

# Background task to run research
async def run_research_task(request_id: str, ticker: str, company_name: Optional[str]):
    async def ws_callback(event: dict):
        if "request_id" not in event:
            event["request_id"] = request_id
        await broadcast_event(request_id, event)

    try:
        # Run agent
        result = await run_agent(
            ticker=ticker,
            company_name=company_name,
            request_id=request_id,
            ws_callback=ws_callback
        )
        
        # Update research store
        if request_id in research_store:
            research_store[request_id].update({
                "status": "complete",
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "brief": result.get("brief"),
                "tool_results": result.get("tool_results"),
                "metadata": result.get("metadata")
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        # Broadcast critical error event
        await broadcast_event(request_id, {
            "event": "error",
            "tool": None,
            "message": f"Critical agent failure: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Update research store
        if request_id in research_store:
            research_store[request_id].update({
                "status": "error",
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "error": str(e)
            })

@app.post("/api/research")
async def start_research(payload: ResearchRequest, background_tasks: BackgroundTasks):
    ticker = payload.ticker.strip().upper()
    if not ticker:
        return JSONResponse(status_code=400, content={
            "error": {
                "code": "INVALID_TICKER",
                "message": "Ticker cannot be empty"
            }
        })
        
    request_id = payload.request_id or str(uuid.uuid4())
    
    # Initialize request in memory
    research_store[request_id] = {
        "request_id": request_id,
        "ticker": ticker,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "completed_at": None,
        "brief": None,
        "tool_results": None
    }
    
    # Run the agent in the background
    background_tasks.add_task(run_research_task, request_id, ticker, payload.company_name)
    
    return {
        "request_id": request_id,
        "ticker": ticker,
        "status": "pending",
        "created_at": research_store[request_id]["created_at"]
    }

@app.get("/api/research/{request_id}")
async def get_research(request_id: str):
    if request_id not in research_store:
        return JSONResponse(status_code=404, content={
            "error": {
                "code": "NOT_FOUND",
                "message": f"Request {request_id} not found"
            }
        })
    return research_store[request_id]

@app.websocket("/ws/progress/{request_id}")
async def websocket_progress(websocket: WebSocket, request_id: str):
    await websocket.accept()
    
    # Register WebSocket
    if request_id not in active_websockets:
        active_websockets[request_id] = []
    active_websockets[request_id].append(websocket)
    
    # Replay event history to late-connecting clients (to handle race conditions)
    history = event_history.get(request_id, [])
    for event in history:
        try:
            await websocket.send_json(event)
        except Exception:
            break
            
    try:
        while True:
            # Maintain connection, handle client disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # Cleanup WebSocket registration
        if request_id in active_websockets:
            if websocket in active_websockets[request_id]:
                active_websockets[request_id].remove(websocket)
            if not active_websockets[request_id]:
                active_websockets.pop(request_id, None)

@app.get("/api/health")
async def health_check():
    import requests
    ml_online = False
    try:
        # Check sentiment server health on port 8001
        res = requests.get("http://localhost:8001/health", timeout=1.0)
        if res.status_code == 200:
            ml_online = True
    except Exception:
        pass
        
    return {
        "status": "ok",
        "ml_server_online": ml_online,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
