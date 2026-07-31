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

import hashlib

from db import (
    upsert_message, ROLE_PRIORITY, OFFICIAL_CHANNELS, is_official_source,
    list_active_schedules_for_matching, create_schedule, update_schedule, cancel_schedule,
    try_claim,
)
from systemprompt import EXTRACTION_SYSTEM_PROMPT
from openrouter_client import chat_completion, parse_json_content

EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "google/gemini-2.0-flash-exp:free")

# EXTRACTION_SYSTEM_PROMPT giờ sống ở systemprompt.py (import ở đầu file) — schema LỒNG NHAU
# (event/target_id/action="ignore") khớp đúng với cách parse bên dưới, KHÔNG đổi sang schema
# phẳng nếu chưa sửa lại `ingest_message()`, xem cảnh báo trong systemprompt.py.


def _should_ingest(sender_role: str, channel: str) -> bool:
    """Có gọi Extraction Agent (LLM) để trích thành lịch chính thức không.

    Dùng chung định nghĩa với field `is_official` của bảng messages — xem
    `db.is_official_source()`. Tin nhắn KHÔNG đạt vẫn được lưu raw ở `upsert_message`
    bên dưới, chỉ là không được biến thành lịch chính thức.
    """
    return is_official_source(sender_role, channel)


def ingest_message(msg_id, channel, sender, sender_role, content, created_at=None,
                    is_edited=False, reference_date=None):
    """Điểm vào chính. Gọi hàm này mỗi khi có 1 tin nhắn mới/sửa từ Discord."""
    msg = upsert_message(msg_id, channel, sender, sender_role, content, created_at, is_edited)

    result = {"message": msg, "extraction": None}

    if not _should_ingest(sender_role, channel):
        return result

    # --- Chặn trích xuất trùng lặp (chỗ khó gây ra lỗi "tạo trùng lịch" / "trả lời 2 lần") ---
    # ingest_message() có thể bị gọi > 1 lần cho CÙNG 1 msg_id nếu: lỡ chạy 2 tiến trình
    # discord_bot.py cùng lúc, chạy backfill_discord.py trong lúc bot live vẫn đang chạy,
    # hoặc Discord gateway lặp lại sự kiện. Không có khoá này thì mỗi lần gọi lại sẽ tốn
    # thêm 1 lời gọi LLM VÀ tạo thêm 1 dòng official_schedules trùng lặp (đã từng xảy ra:
    # SCH_012/SCH_013 và SCH_014/SCH_015 trùng y hệt nhau, cách nhau 1 giây).
    # Tin nhắn MỚI: khoá theo msg_id, chỉ trích xuất 1 lần duy nhất trong vòng đời tin nhắn.
    # Tin nhắn EDIT: khoá theo msg_id + hash nội dung, để 1 lượt sửa chỉ trích xuất 1 lần,
    # nhưng NHIỀU lượt sửa khác nhau (nội dung khác nhau) vẫn được trích xuất lại như thiết kế.
    content_hash = hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:16]
    lock_key = f"extract:{msg_id}:{content_hash}" if is_edited else f"extract:{msg_id}"
    if not try_claim(lock_key):
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
