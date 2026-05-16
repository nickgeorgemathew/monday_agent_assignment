"""Skylark Drones BI Agent — FastAPI backend"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from backend.agent import run_agent

app = FastAPI(title="Skylark Drones BI Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_sessions: dict[str, list] = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    answer: str
    traces: list
    session_id: str

@app.get("/health")
def health():
    return {
        "status": "ok",
        "deals_board_configured": bool(os.environ.get("DEALS_BOARD_ID")),
        "wo_board_configured": bool(os.environ.get("WO_BOARD_ID")),
        "monday_token_configured": bool(os.environ.get("MONDAY_API_TOKEN")),
        "anthropic_token_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    deals_board_id = os.environ.get("DEALS_BOARD_ID", "")
    wo_board_id = os.environ.get("WO_BOARD_ID", "")
    if not deals_board_id or not wo_board_id:
        raise HTTPException(status_code=500, detail="Board IDs not configured. Set DEALS_BOARD_ID and WO_BOARD_ID.")
    history = _sessions.get(req.session_id, [])
    result = run_agent(req.message, history, deals_board_id, wo_board_id)
    _sessions[req.session_id] = result["updated_history"][-20:]
    return ChatResponse(answer=result["answer"], traces=result["traces"], session_id=req.session_id)

@app.delete("/chat/{session_id}")
def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"cleared": session_id}
