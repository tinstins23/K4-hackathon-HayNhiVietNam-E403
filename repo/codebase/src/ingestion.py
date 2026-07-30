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
from openrouter_client import chat_completion, parse_json_content

EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "openai/gpt-4o-mini")

EXTRACTION_SYSTEM_PROMPT = """Bạn là Extraction Agent cho hệ thống quản lý lịch trình khóa học AI Thực Chiến trên Discord.

Nhiệm vụ: đọc 1 tin nhắn thông báo và quyết định nó có chứa thông tin LỊCH (buổi học, mentoring,
deadline, workshop, sự kiện) hay không, rồi trả về đúng 1 JSON object theo schema sau, KHÔNG thêm
text nào khác ngoài JSON:

{
  "action": "create" | "update" | "cancel" | "ignore",
  "target_id": "<id sự kiện đang active cần update/cancel, hoặc null nếu action=create/ignore>",
  "event": {
    "title": "string",
    "start_time": "YYYY-MM-DDTHH:MM:SS",
    "end_time": "YYYY-MM-DDTHH:MM:SS hoặc null nếu không rõ",
    "is_mandatory": true/false,
    "category": "CLASS" | "MENTORING" | "DEADLINE" | "WORKSHOP" | "EVENT",
    "host": "string hoặc null",
    "location": "string hoặc null"
  } | null
}

Quy tắc:
- "ignore": tin nhắn KHÔNG liên quan lịch trình cụ thể (chào hỏi, thông tin chung không có mốc thời gian).
  QUAN TRỌNG: KHÔNG được "ignore" nếu tin nhắn có chứa mốc thời gian cụ thể — dù trùng giờ với sự kiện khác,
  đây vẫn là sự kiện riêng biệt và phải "create".
- "create": tin nhắn báo 1 lịch/deadline CÓ CHỨA thời gian cụ thể, và tên sự kiện KHÔNG khớp với bất kỳ
  sự kiện nào trong danh sách active (khớp theo TÊN, không phải theo thời gian). Trùng giờ ≠ trùng sự kiện.
- "update": tin nhắn nói về việc DỜI GIỜ / SỬA THÔNG TIN của 1 sự kiện đã có trong danh sách active
  (khớp theo TÊN buổi học / host) -> bắt buộc phải trả target_id đúng, event chứa
  giá trị MỚI (giữ nguyên field nào không đổi bằng cách lấy lại giá trị cũ từ danh sách active).
  QUAN TRỌNG: nếu không tìm được sự kiện nào trong active list có TÊN khớp với nội dung tin nhắn,
  dù tin nhắn có từ "THAY ĐỔI"/"SỬA"/"DỜI" thì action phải là "create" (không được update nhầm
  vào sự kiện khác không liên quan). target_id CHỈ được trả khi chắc chắn khớp đúng tên sự kiện.
- "cancel": tin nhắn báo HỦY 1 sự kiện đã có trong danh sách active -> bắt buộc trả target_id đúng.
- Không tự bịa thời gian nếu tin nhắn không nói rõ. Nếu không đủ thông tin bắt buộc (start_time) -> "ignore".
- Ngày hiện tại (nếu tin nhắn dùng "hôm nay", "ngày mai", "thứ X tuần này") được cho trong phần CONTEXT.
- is_mandatory=true khi: tin nhắn từ BTC/Giảng viên thông báo buổi học chính thức, kỳ thi, deadline nộp bài,
  khai mạc/bế mạc, hoặc dùng từ "BẮT BUỘC"/"LƯU Ý"/"bắt buộc tham dự". is_mandatory=false khi: workshop
  tự chọn, mentoring 1-on-1 đăng ký tự nguyện, hoặc tin nhắn ghi rõ "tự chọn"/"tuỳ chọn"/"không bắt buộc".
- category: CLASS cho buổi học live/module; MENTORING cho 1-on-1/coaching; DEADLINE cho hạn nộp bài/CP;
  WORKSHOP cho workshop/seminar; EVENT cho khai mạc/bế mạc/sự kiện đặc biệt.
"""


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
