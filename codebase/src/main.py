"""
main.py — FastAPI backend cho Trợ lý AI Sắp Xếp Lịch Trình Discord.

Chạy:  uvicorn main:app --reload --port 8000
Docs:  http://localhost:8000/docs

Endpoints:
  POST /ingest          — nạp 1 tin nhắn (bot Discord thật hoặc script seed gọi vào đây)
  POST /chat             — học viên hỏi, trả lời bằng ReAct Agent (đây là "lời gọi AI thật"
                            thay thế hoàn toàn phần setTimeout hardcode trong mock_ui)
  GET  /messages/{channel} — lấy lịch sử tin nhắn 1 kênh (để UI render thay vì channelsData cứng)
  GET  /schedules         — xem nhanh toàn bộ lịch đã trích xuất (debug/demo)
  GET  /health
"""
import os
from datetime import datetime, timezone
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import ingestion
import agent

db.init_db()

app = FastAPI(title="Discord Schedule Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    msg_id: str
    channel: str
    sender: str
    sender_role: str  # btc | instructor | coach | mentor | student
    content: str
    created_at: Optional[str] = None
    is_edited: bool = False


class ChatRequest(BaseModel):
    message: str
    user_label: str = "học viên"
    history: Optional[List[dict]] = None   # [{role:"user"/"assistant", content:"..."}]
    reference_date: Optional[str] = None    # override cho demo (vd. "2026-08-10"); mặc định = hôm nay


class ChatResponse(BaseModel):
    reply: str
    citations: list
    tool_trace: list


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest):
    try:
        result = ingestion.ingest_message(
            msg_id=req.msg_id, channel=req.channel, sender=req.sender,
            sender_role=req.sender_role, content=req.content,
            created_at=req.created_at, is_edited=req.is_edited,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    ref_date = req.reference_date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        result = agent.ask(
            user_query=req.message, reference_date=ref_date,
            history=req.history, user_label=req.user_label,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@app.get("/messages/{channel}")
def messages(channel: str, limit: int = 50):
    return db.list_messages(channel, limit=limit)


@app.get("/schedules")
def schedules(status: str = "active"):
    return db.query_schedules(status=status)
