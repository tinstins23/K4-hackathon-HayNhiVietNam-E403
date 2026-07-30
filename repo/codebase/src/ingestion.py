"""
ingestion.py — Extraction Agent (chỗ khó ① + ④ trong spec.md §5)

Luồng: 1 tin nhắn mới/sửa từ kênh thông báo (#thong-bao-chung, #lich-hoc-moi)
  -> lưu raw vào bảng messages (nguồn sự thật, luôn giữ nguyên văn)
  -> nếu sender_role đủ tin cậy (btc/instructor/coach/mentor) -> gọi LLM trích xuất
  -> LLM tự quyết định: create sự kiện mới / update sự kiện cũ / cancel / ignore
     (so khớp với danh sách sự kiện đang active để tránh tạo trùng khi tin nhắn
     chỉ là "sửa giờ" của 1 sự kiện đã có)
  -> ghi vào official_schedules, LUÔN gắn source_msg_id = tin nhắn mới nhất

Học viên (sender_role='student') gửi trong kênh thông báo (hiếm khi xảy ra vì
kênh đó read-only) sẽ KHÔNG được ingest thành lịch chính thức -> chặn giả mạo.
"""
import os
import json
from datetime import datetime, timezone

from db import (
    upsert_message, ROLE_PRIORITY, OFFICIAL_CHANNELS,
    list_active_schedules_for_matching, create_schedule, update_schedule, cancel_schedule,
)
from systemprompt import EXTRACTION_SYSTEM_PROMPT
from openrouter_client import chat_completion, parse_json_content

EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "google/gemini-2.0-flash-exp:free")



def _should_ingest(sender_role: str, channel: str) -> bool:
    return channel in OFFICIAL_CHANNELS and ROLE_PRIORITY.get(sender_role, 0) >= ROLE_PRIORITY["mentor"]


def ingest_message(msg_id, channel, sender, sender_role, content, created_at=None,
                    is_edited=False, reference_date=None):
    """Điểm vào chính. Gọi hàm này mỗi khi có 1 tin nhắn mới/sửa từ Discord."""
    msg = upsert_message(msg_id, channel, sender, sender_role, content, created_at, is_edited)

    result = {"message": msg, "extraction": None}

    if not _should_ingest(sender_role, channel):
        return result

    active_events = list_active_schedules_for_matching()
    ref_date = reference_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    user_prompt = f"""CONTEXT:
- Ngày hôm nay (reference_date): {ref_date}
- Danh sách sự kiện đang active trong DB (để so khớp update/cancel):
{json.dumps(active_events, ensure_ascii=False, indent=2)}

TIN NHẮN CẦN TRÍCH XUẤT (từ {sender}, role={sender_role}, kênh #{channel}):
\"\"\"{content}\"\"\"
"""

    message = chat_completion(
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        model=EXTRACTION_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
    )
    parsed = parse_json_content(message)
    result["extraction"] = parsed

    action = parsed.get("action")
    event = parsed.get("event") or {}
    target_id = parsed.get("target_id")

    if action == "create" and event.get("start_time"):
        result["schedule"] = create_schedule(
            title=event.get("title", "(Không rõ tiêu đề)"),
            start_time=event["start_time"],
            end_time=event.get("end_time"),
            is_mandatory=event.get("is_mandatory", True),
            category=event.get("category", "EVENT"),
            host=event.get("host"),
            location=event.get("location"),
            source_msg_id=msg_id,
            source_channel=channel,
        )
    elif action == "update" and target_id:
        result["schedule"] = update_schedule(
            target_id, source_msg_id=msg_id, source_channel=channel,
            title=event.get("title"), start_time=event.get("start_time"),
            end_time=event.get("end_time"), is_mandatory=event.get("is_mandatory"),
            category=event.get("category"), host=event.get("host"), location=event.get("location"),
        )
    elif action == "cancel" and target_id:
        result["schedule"] = cancel_schedule(target_id, source_msg_id=msg_id, source_channel=channel)

    return result
