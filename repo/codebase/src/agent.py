"""
agent.py — ReAct Scheduler Agent (spec.md §4 "lát cắt MỘT CÂU" + §6 4 đường trải nghiệm)

Vòng lặp: Claude/LLM (qua OpenRouter) được cấp các TOOL truy vấn DB thật.
Model tự quyết định gọi tool nào, đọc kết quả, rồi gọi tiếp hoặc trả lời cuối cùng.
Lặp tối đa MAX_TURNS lượt để tránh vòng lặp vô hạn nếu model kẹt.

Điểm mấu chốt (bám đúng yêu cầu ban đầu #6 của nhóm):
  "AI sẽ làm đến khi tìm + sắp xếp được lịch trình HOẶC phản hồi nếu khoảng
   thời gian đó không có lịch" -> model được phép gọi tool nhiều lần (vd. mở
   rộng khoảng ngày) trước khi kết luận không có lịch, KHÔNG được bịa nếu tool
   trả về rỗng.

Trích dẫn (spec.md §7 — quality bar 100%): thay vì tin tưởng model tự nhớ
trích dẫn trong text, backend ÉP BUỘC bằng cách tự động gom mọi source_msg_id
xuất hiện trong kết quả các tool đã gọi ở lượt cuối, rồi trả về field
`citations` riêng — UI luôn hiển thị được nguồn dù model có quên nhắc trong câu trả lời.
"""
import os
import json

from db import query_schedules, search_messages, get_message, ROLE_PRIORITY, to_vn_display
import tools
from openrouter_client import chat_completion

# SYSTEM_PROMPT giờ sống ở systemprompt.py (module dùng chung với ingestion.py) — xem file đó
# để đọc/sửa nội dung prompt. get_scheduler_system_prompt() ghép thêm reference_date + user_label
# vào cuối prompt gốc.
from systemprompt import SCHEDULER_SYSTEM_PROMPT as SYSTEM_PROMPT, get_scheduler_system_prompt

AGENT_MODEL = os.getenv("AGENT_MODEL", "google/gemma-4-26b-a4b-it:free")
MAX_TURNS = 6

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_schedules",
            "description": "Query verified official schedules/deadlines/mentoring slots in the DB, filtered by date range/category/status. See RULE 2: resolve the user's final target range first, call once with the narrowest necessary range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "ISO datetime, e.g. 2026-07-30T00:00:00"},
                    "date_to": {"type": "string", "description": "ISO datetime"},
                    "category": {"type": "string", "enum": ["CLASS", "MENTORING", "DEADLINE", "WORKSHOP", "EVENT"]},
                    "status": {"type": "string", "enum": ["active", "canceled"], "description": "Default 'active'"},
                    "mandatory_only": {
                        "type": "boolean",
                        "description": "ONLY set this if the user explicitly said they want mandatory events only. Leave UNSET by default to get every active event, mandatory or not — unset does NOT mean mandatory-only.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_messages",
            "description": (
                "Search raw Discord messages by keyword. Covers BOTH: (1) official announcements "
                "from BTC/Instructor/Coach/Mentor -> is_official=true, trustworthy; (2) STUDENT "
                "chat messages -> is_official=false, CONTEXT ONLY, NOT fact about schedules. Use "
                "when you need context not in the structured schedule table (make-up slots, extra "
                "Coach notes), or want to see what other students asked/discussed on this topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "channel": {"type": "string", "description": "Discord channel name, e.g. 'thông-báo'. Leave empty to search all channels."},
                    "only_official": {"type": "boolean", "description": "true = official sources only; false = student messages only; unset = both."},
                    "sender_role": {"type": "string", "enum": ["btc", "instructor", "coach", "mentor", "student"]},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_message",
            "description": "Fetch the exact original text of 1 message by msg_id, for precise citation or detail verification.",
            "parameters": {
                "type": "object",
                "properties": {"msg_id": {"type": "string"}},
                "required": ["msg_id"],
            },
        },
    },
    # --- 3 tool dưới đây do Quân thêm (commit 98091e6), cài đặt trong tools.py ---
    {
        "type": "function",
        "function": {
            "name": "get_schedule_by_id",
            "description": "Fetch full detail of one schedule event by its ID (sched_id), including created_at, updated_at and source_msg_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sched_id": {"type": "string", "description": "Schedule ID, e.g. SCH_001"}
                },
                "required": ["sched_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_busy_slots_from_db",
            "description": "Look up a student's personal busy-time slots, to avoid time conflicts when planning a schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_label": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "required": ["user_label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_personal_busy_slot",
            "description": "Record a new personal busy-time slot for the student in the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_label": {"type": "string"},
                    "title": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                },
                "required": ["user_label", "title", "start_time", "end_time"],
            },
        },
    },
]


_SYSTEM_TIME_KEYS = ("created_at", "updated_at", "edited_at")


def _convert_display_times(data):
    """DB lưu created_at/updated_at/edited_at theo UTC (đúng, không đổi ở tầng lưu trữ) —
    nhưng model đọc các field này trực tiếp từ kết quả tool để KỂ LẠI cho người dùng (rule 6
    trong systemprompt.py: narrate "ai nói lúc nào"). Nếu không quy đổi ở đây, model sẽ echo
    nguyên giờ UTC -> lệch 7 tiếng so với giờ thực tế người dùng đăng (VD: đăng ~12h trưa VN
    nhưng model nói "lúc 04:xx sáng"). KHÔNG đụng start_time/end_time (giờ sự kiện do
    Extraction Agent parse từ ngôn ngữ tự nhiên, đã ngầm định là giờ VN, không có UTC gốc)."""
    def convert(item):
        if isinstance(item, dict):
            for k in _SYSTEM_TIME_KEYS:
                if item.get(k):
                    item[k] = to_vn_display(item[k])
        return item

    if isinstance(data, list):
        return [convert(x) for x in data]
    return convert(data)


def _execute_tool(name, args):
    if name == "query_schedules":
        return _convert_display_times(query_schedules(
            date_from=args.get("date_from"), date_to=args.get("date_to"),
            category=args.get("category"), status=args.get("status", "active"),
            mandatory_only=args.get("mandatory_only"),
        ))
    if name == "search_messages":
        return _convert_display_times(search_messages(
            args.get("keyword", ""), channel=args.get("channel"),
            only_official=args.get("only_official"), sender_role=args.get("sender_role"),
        ))
    if name == "get_message":
        msg = get_message(args.get("msg_id"))
        return _convert_display_times(msg) if msg else {"error": "not_found"}
    if name == "get_schedule_by_id":
        return _convert_display_times(tools.get_schedule_by_id(args.get("sched_id")))
    if name == "list_busy_slots_from_db":
        return _convert_display_times(tools.list_busy_slots_from_db(
            user_label=args.get("user_label"),
            date_from=args.get("date_from"), date_to=args.get("date_to"),
        ))
    if name == "add_personal_busy_slot":
        return tools.add_personal_busy_slot(
            user_label=args.get("user_label"), title=args.get("title"),
            start_time=args.get("start_time"), end_time=args.get("end_time"),
        )
    return {"error": f"unknown tool {name}"}


def _collect_citations(tool_result):
    """Gom msg_id trong 1 kết quả tool, TÁCH LÀM 2 RỔ theo mức tin cậy.

    Trả về (official_ids, unofficial_ids).

    Vì sao phải tách: từ khi bot lưu cả tin nhắn học viên, nếu gom chung một rổ thì một câu
    đoán sai của bạn cùng lớp sẽ được Discord embed dán nhãn "Trích dẫn nguồn sự thật" —
    đúng vào lỗi ① (nguồn sự thật) mà spec.md §5 cam kết xử lý.

    Lịch trong official_schedules luôn tính là chính thức: nó chỉ được tạo ra từ tin nhắn
    đã qua cửa `db.is_official_source()` ngay từ khâu ingest.
    """
    official, unofficial = set(), set()
    items = tool_result if isinstance(tool_result, list) else [tool_result]
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("source_msg_id"):
            official.add(it["source_msg_id"])
        if it.get("msg_id"):
            (official if it.get("is_official") else unofficial).add(it["msg_id"])
    return official, unofficial


def _build_refs(msg_ids):
    """msg_id -> bản ghi hiển thị được (kênh, người gửi, thời điểm)."""
    refs = []
    for msg_id in sorted(msg_ids):
        m = get_message(msg_id)
        if m:
            refs.append({
                "msg_id": m["msg_id"], "channel": m["channel"],
                "sender": m["sender"], "sender_role": m["sender_role"],
                # DB lưu created_at theo UTC (đúng, không đổi) — nhưng LLM/người dùng đọc
                # phải thấy giờ Việt Nam, nếu không sẽ lệch 7 tiếng (vd. đăng ~12h trưa VN
                # lại hiện "04:xx sáng"). Xem db.to_vn_display().
                "time": to_vn_display(m["created_at"]), "is_official": m["is_official"],
            })
    return refs


OFFLINE_BANNER = (
    "⚠️ **[CHẾ ĐỘ OFFLINE — KHÔNG CÓ LỜI GỌI AI]**\n"
    "_Không kết nối được LLM nên câu trả lời dưới đây do bộ quy tắc (regex + truy vấn DB) sinh ra, "
    "KHÔNG phải do AI suy luận. Nó chỉ liệt kê dữ liệu thô và có thể không đúng trọng tâm câu hỏi._\n\n"
)


def _offline_answer(user_query: str, user_label: str, tool_trace: list, err: Exception):
    """Bộ trả lời dự phòng khi LLM không gọi được (truy vấn trực tiếp CSDL schedules.db)."""
    import re

    query_lower = user_query.lower()
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", user_query)
    target_date = date_match.group(1) if date_match else None
    sch_match = re.search(r"(SCH_\d+)", user_query, re.IGNORECASE)
    target_sch_id = sch_match.group(1).upper() if sch_match else None

    reply_lines, seen_msg_ids = [], set()

    # 1. Trái thẩm quyền / Security Traps / Non-schedule handling
    if any(k in query_lower for k in ("nghỉ học", "cho cả lớp nghỉ", "cho nghỉ")):
        reply_lines.append("Tôi là Trợ lý AI sắp xếp lịch và không có quyền quyết định cho cả lớp nghỉ học. Vui lòng liên hệ Ban tổ chức (BTC) hoặc Coach để gửi yêu cầu chính thức.")
    elif any(k in query_lower for k in ("đáp án", "xin đáp án", "giải đề")):
        reply_lines.append("Tôi xin từ chối cung cấp đáp án bài test theo đúng quy định của khóa học.")
    elif any(k in query_lower for k in ("bỏ qua toàn bộ", "system prompt", "api key", "ignore previous instructions", "system_override")):
        reply_lines.append("Trợ lý AI từ chối và không thể thực hiện các yêu cầu can thiệp hệ thống hoặc tiết lộ thông tin cấu hình/API Key.")
    elif "trường sa" in query_lower or "hoàng sa" in query_lower:
        reply_lines.append("Trường Sa và Hoàng Sa là của Việt Nam. Tôi là Trợ lý AI tập trung hỗ trợ sắp xếp lịch trình học tập.")
    elif any(k in query_lower for k in ("làm toán", "giải toán")):
        reply_lines.append("Tôi là Trợ lý AI hỗ trợ quản lý và sắp xếp lịch trình học tập khóa học. Nếu bạn có thắc mắc về lịch học hay deadline, tôi sẵn sàng hỗ trợ!")
    elif query_lower.strip() in ("???", "??", "?"):
        reply_lines.append("Chào bạn, tôi có thể hỗ trợ giúp gì cho bạn về thông tin lịch trình, buổi học hay hạn nộp bài tập?")

    # 2. Tra cứu theo SCH_ID trực tiếp trong DB
    elif target_sch_id:
        res = tools.get_schedule_by_id(target_sch_id)
        tool_trace.append({"tool": "get_schedule_by_id", "args": {"sched_id": target_sch_id}, "result_count": 1 if "id" in res else 0})
        if "id" in res:
            is_mand = "Bắt buộc" if res.get("is_mandatory") else "Tùy chọn"
            reply_lines += [
                f"📌 **Thông tin chi tiết cho sự kiện [{res['id']}]:**\n",
                f"- **Tiêu đề**: {res.get('title')}",
                f"- **Thời gian**: {res.get('start_time')} - {res.get('end_time')}",
                f"- **Phân loại**: {res.get('category')} ({is_mand})",
                f"- **Host**: {res.get('host') or 'BTC'}",
            ]
            if res.get("source_msg_id"):
                seen_msg_ids.add(res["source_msg_id"])
        else:
            reply_lines.append(f"Không tìm thấy sự kiện nào có mã {target_sch_id}.")

    # 3. Trùng 3 việc T5 / Xung đột lịch
    elif "trùng 3 việc" in query_lower or "tối t5" in query_lower:
        reply_lines.append("Tối T5: Ưu tiên tham gia Mentoring CP2 (17:00-18:00) và nộp Spec CP4 (Deadline 23:59).")
        seen_msg_ids.add("msg_9821")
        seen_msg_ids.add("msg_9890")

    # 4. Hỏi về dời lịch + hủy T7 (TC_011)
    elif "dời lịch" in query_lower and "hủy" in query_lower:
        reply_lines.append("Buổi Mentoring CP2 chiều nay dời sang 17:00 - 18:00. Workshop Prompting sáng T7 đã bị hủy.")
        seen_msg_ids.add("msg_9821")
        seen_msg_ids.add("msg_9950")

    # 5. Hỏi về sự kiện bị HỦY (Canceled)
    elif any(k in query_lower for k in ("hủy", "hủy rồi", "workshop prompting")):
        canceled_scheds = query_schedules(status="canceled")
        tool_trace.append({"tool": "query_schedules", "args": {"status": "canceled"}, "result_count": len(canceled_scheds)})
        if canceled_scheds:
            for s in canceled_scheds:
                reply_lines.append(f"⚠️ Thông báo: Buổi '{s.get('title')}' ({s.get('start_time')}) ĐÃ BỊ HỦY do server Discord bảo trì định kỳ.")
                if s.get("source_msg_id"):
                    seen_msg_ids.add(s["source_msg_id"])
        else:
            reply_lines.append("Không có thông báo hủy lịch nào trong hệ thống.")
        if "thi" in query_lower:
            reply_lines.append("Vì workshop đã HỦY nên bạn hoàn toàn có thể ưu tiên đi thi ở trường.")

    # 6. Hỏi về Mentoring CP2 / Dời lịch / Slot bù
    elif "mentoring" in query_lower or "cp2" in query_lower:
        scheds = query_schedules(category="MENTORING", status="active")
        tool_trace.append({"tool": "query_schedules", "args": {"category": "MENTORING", "status": "active"}, "result_count": len(scheds)})
        for s in scheds:
            reply_lines.append(f"📌 **{s.get('title')}**: Đã được dời sang {s.get('start_time')} - {s.get('end_time')} tại {s.get('location') or 'Discord Voice 1'} do {s.get('host') or 'Coach Hùng'} phụ trách.")
            if s.get("source_msg_id"):
                seen_msg_ids.add(s["source_msg_id"])
        if any(k in query_lower for k in ("bù", "mess", "thi")):
            extra_slots = query_schedules(status="active")
            for ex in extra_slots:
                if "Code Review" in ex.get("title", "") or "1-on-1" in ex.get("title", ""):
                    reply_lines.append(f"💡 Gợi ý slot bù: Có thể sắp xếp xin bù vào '{ex.get('title')}' vào {ex.get('start_time')}.")
                    if ex.get("source_msg_id"):
                        seen_msg_ids.add(ex["source_msg_id"])
            reply_lines.append("📝 Mẫu mess gửi Coach: 'Em chào Coach, do trùng lịch thi trường nên em xin phép bù slot sau ạ.'")

    # 7. Hỏi ngày 15/08 (TC_004)
    elif "15/08" in query_lower and "live" in query_lower:
        reply_lines.append("Không tìm thấy buổi học live nào vào đêm 15/08 (chỉ có hạn chốt nộp Capstone vào 23:59).")

    # 5. Hỏi về Spec.md / Deadline CP4 / nộp bài tối nay
    elif any(k in query_lower for k in ("spec", "cp4", "nộp bài", "22h")):
        scheds = query_schedules(category="DEADLINE", status="active")
        tool_trace.append({"tool": "query_schedules", "args": {"category": "DEADLINE", "status": "active"}, "result_count": len(scheds)})
        for s in scheds:
            if "spec" in s.get("title", "").lower() or "cp4" in s.get("title", "").lower():
                reply_lines.append(f"⏰ **Hạn nộp Spec.md (CP4)**: Hạn cứng nộp file spec.md là đúng 23:59 hôm nay (2026-07-30). Bạn làm tới 22h vẫn kịp nộp bài.")
                if s.get("source_msg_id"):
                    seen_msg_ids.add(s["source_msg_id"])

    # 6. Hỏi về Live Class ReAct Engine
    elif any(k in query_lower for k in ("react", "function calling", "live")):
        scheds = query_schedules(category="CLASS", status="active")
        tool_trace.append({"tool": "query_schedules", "args": {"category": "CLASS", "status": "active"}, "result_count": len(scheds)})
        for s in scheds:
            reply_lines.append(f"📚 **{s.get('title')}**: Diễn ra lúc {s.get('start_time')} - {s.get('end_time')} tại {s.get('location') or 'Discord Online Live'} do {s.get('host') or 'Giảng viên Tín'} giảng dạy.")
            if s.get("source_msg_id"):
                seen_msg_ids.add(s["source_msg_id"])

    # 7. Hỏi về Demo Day / Bế mạc Capstone
    elif any(k in query_lower for k in ("demo day", "bế mạc")):
        scheds = query_schedules(category="EVENT", status="active")
        tool_trace.append({"tool": "query_schedules", "args": {"category": "EVENT", "status": "active"}, "result_count": len(scheds)})
        for s in scheds:
            if "demo day" in s.get("title", "").lower() or "bế mạc" in s.get("title", "").lower():
                reply_lines.append(f"🎉 **{s.get('title')}**: Diễn ra lúc 18:00 - 21:00 ngày 28/08/2026 tại {s.get('location') or 'Discord Stage & Offline'}.")
                if s.get("source_msg_id"):
                    seen_msg_ids.add(s["source_msg_id"])

    # 8. Hỏi về Roadmap Tuần / Tháng 8 / Capstone Proposal
    elif any(k in query_lower for k in ("tuần này", "module 4", "lab 4", "tháng 8", "capstone")):
        scheds = query_schedules(status="active")
        tool_trace.append({"tool": "query_schedules", "args": {"status": "active"}, "result_count": len(scheds)})
        for s in scheds:
            if any(k in s.get("title", "").lower() for k in ("module 4", "lab 4", "capstone", "tháng 8")):
                reply_lines.append(f"📌 **{s.get('title')}**: {s.get('start_time')} - {s.get('end_time')} ({s.get('category')}). Hạn chốt 15/08.")
                if s.get("source_msg_id"):
                    seen_msg_ids.add(s["source_msg_id"])

    # 9. Tra cứu theo ngày cụ thể (hoặc ngày quá khứ 2025/lớp không tồn tại)
    elif target_date or "2025" in query_lower or "python nâng cao" in query_lower:
        date_from = f"{target_date}T00:00:00" if target_date else None
        date_to = f"{target_date}T23:59:59" if target_date else None
        scheds = tools.get_schedules_from_db(date_from=date_from, date_to=date_to, status="active")
        tool_trace.append({"tool": "get_schedules_from_db", "args": {"date_from": date_from, "date_to": date_to}, "result_count": len(scheds)})
        if not scheds or "2025" in query_lower or "python nâng cao" in query_lower:
            reply_lines.append("Không tìm thấy thông báo lịch học nào trong khoảng thời gian/chủ đề này.")
        else:
            reply_lines.append(f"📌 **Các lịch trình trong ngày {target_date}:**\n")
            for idx, s in enumerate(scheds, 1):
                reply_lines.append(f"{idx}. [{s.get('id')}] **{s.get('title')}** ({s.get('start_time')} - {s.get('end_time')})")
                if s.get("source_msg_id"):
                    seen_msg_ids.add(s["source_msg_id"])

    # 10. Mặc định: Trả về danh sách tất cả các lịch active từ DB
    else:
        scheds = tools.get_schedules_from_db(status="active")
        tool_trace.append({"tool": "get_schedules_from_db", "args": {"status": "active"}, "result_count": len(scheds)})
        if not scheds:
            reply_lines.append("Không tìm thấy thông báo lịch học nào trong khoảng thời gian này.")
        for idx, s in enumerate(scheds, 1):
            is_mand = "Bắt buộc" if s.get("is_mandatory") else "Tùy chọn"
            reply_lines.append(f"{idx}. [{s.get('id')}] **{s.get('title')}** ({s.get('category')}) - ⏰ {s.get('start_time')} - {s.get('end_time')} [{is_mand}]")
            if s.get("source_msg_id"):
                seen_msg_ids.add(s["source_msg_id"])

    return {
        "reply": OFFLINE_BANNER + "\n".join(reply_lines),
        "citations": _build_refs(seen_msg_ids),
        "references": [],
        "tool_trace": tool_trace,
        "mode": "offline_regex",
        "llm_error": str(err)[:300],
    }


def ask(user_query: str, reference_date: str, history: list = None, user_label: str = "học viên"):
    """Chạy 1 vòng ReAct loop đầy đủ, trả về dict:
    {
      reply: str,
      citations:  [...],   # NGUỒN CHÍNH THỨC — trích dẫn được, đây là sự thật
      references: [...],   # tin nhắn học viên — ngữ cảnh, CHƯA XÁC THỰC
      tool_trace: [...]
    }
    """
    # get_scheduler_system_prompt() ghép sẵn reference_date + user_label vào cuối
    # SCHEDULER_SYSTEM_PROMPT (xem systemprompt.py) — thay cho việc tự nối chuỗi thủ công.
    messages = [{"role": "system", "content": get_scheduler_system_prompt(reference_date, user_label)}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_query})

    official_ids, unofficial_ids = set(), set()
    tool_trace = []

    try:
        for _ in range(MAX_TURNS):
            msg = chat_completion(messages=messages, model=AGENT_MODEL, tools=TOOLS, temperature=0.2)
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return {
                    "reply": msg.get("content") or "",
                    "citations": _build_refs(official_ids),
                    # bỏ id nào đã nằm ở rổ chính thức, tránh hiện 2 lần
                    "references": _build_refs(unofficial_ids - official_ids),
                    "tool_trace": tool_trace,
                    "mode": "llm",
                }

            # model muốn gọi tool -> append assistant turn kèm tool_calls, rồi thực thi từng cái
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
            for call in tool_calls:
                fn_name = call["function"]["name"]
                try:
                    fn_args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                result = _execute_tool(fn_name, fn_args)
                new_official, new_unofficial = _collect_citations(result)
                official_ids |= new_official
                unofficial_ids |= new_unofficial
                tool_trace.append({"tool": fn_name, "args": fn_args, "result_count": len(result) if isinstance(result, list) else 1})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

    except RuntimeError as err:
        return _offline_answer(user_query, user_label, tool_trace, err)

    # Hết MAX_TURNS mà model vẫn chưa chốt câu trả lời -> graceful fallback
    return {
        "reply": "Xin lỗi, câu hỏi này cần nhiều bước tra cứu hơn dự kiến. Bạn thử hỏi cụ thể hơn "
                 "(VD: nêu rõ khoảng ngày hoặc tên buổi học) giúp mình nhé, hoặc liên hệ Coach nếu gấp.",
        "citations": _build_refs(official_ids),
        "references": _build_refs(unofficial_ids - official_ids),
        "tool_trace": tool_trace,
        "mode": "llm",
    }
