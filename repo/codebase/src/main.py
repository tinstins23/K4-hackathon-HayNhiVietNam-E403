"""
main.py — FastAPI backend (messages-only).

Chạy:  uvicorn main:app --reload --port 8000
"""
import os
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import agent

db.init_db()

app = FastAPI(title="Discord Schedule Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    msg_id: str
    channel: str
    sender: str
    sender_role: str
    content: str
    created_at: Optional[str] = None
    is_edited: bool = False


class ChatRequest(BaseModel):
    message: str
    user_label: str = "học viên"
    history: Optional[List[dict]] = None
    reference_date: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    citations: list
    references: list = []
    tool_trace: list


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest):
    """Lưu 1 tin nhắn raw vào bảng messages (không extract lịch)."""
    return db.upsert_message(
        msg_id=req.msg_id, channel=req.channel, sender=req.sender,
        sender_role=req.sender_role, content=req.content,
        created_at=req.created_at, is_edited=req.is_edited,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    ref_date = req.reference_date or db.vn_now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        result = agent.ask(
            user_query=req.message, reference_date=ref_date,
            history=req.history, user_label=req.user_label,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@app.get("/messages/search")
def messages_search(keyword: str, channel: str = None, limit: int = 20,
                     sender_role: str = None, only_official: bool = None):
    return db.search_messages(
        keyword, channel=channel, limit=limit,
        sender_role=sender_role, only_official=only_official,
    )


@app.get("/messages/stats")
def messages_stats():
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT channel, sender_role, COUNT(*) AS count FROM messages
               GROUP BY channel, sender_role ORDER BY count DESC"""
        ).fetchall()
    return {
        "db_path": db.DB_PATH,
        "total": sum(r["count"] for r in rows),
        "breakdown": [
            {**dict(r), "is_official": db.is_official_source(r["sender_role"], channel_name=r["channel"])}
            for r in rows
        ],
    }


@app.get("/messages/{channel}")
def messages(channel: str, limit: int = 50):
    return db.list_messages(channel, limit=limit)
