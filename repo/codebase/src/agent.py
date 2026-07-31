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

AGENT_MODEL = os.getenv("AGENT_MODEL", "google/gemini-2.0-flash-exp:free")
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
    """Bộ trả lời dự phòng khi LLM không gọi được (do Quân viết, commit 98091e6).

    KHÔNG có lời gọi AI nào ở đây — chỉ regex + truy vấn DB. Vì vậy kết quả LUÔN được gắn
    OFFLINE_BANNER và field `mode="offline_regex"`, để không bị nhầm là câu trả lời của AI
    (rubric R5: "phần mock ghi rõ" + "mức prototype khai báo khớp thực tế").
    """
    import re

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", user_query)
    target_date = date_match.group(1) if date_match else None
    sch_match = re.search(r"(SCH_\d+)", user_query, re.IGNORECASE)
    target_sch_id = sch_match.group(1).upper() if sch_match else None

    reply_lines, seen_msg_ids = [], set()

    if target_sch_id:
        res = tools.get_schedule_by_id(target_sch_id)
        tool_trace.append({"tool": "get_schedule_by_id", "args": {"sched_id": target_sch_id},
                           "result_count": 1 if "id" in res else 0})
        if "id" in res:
            is_mand = "Bắt buộc" if res.get("is_mandatory") else "Tùy chọn"
            reply_lines += [
                f"📌 **Thông tin chi tiết cho sự kiện [{res['id']}]:**\n",
                f"- **Tiêu đề**: {res.get('title')}",
                f"- **Thời gian**: {res.get('start_time')} - {res.get('end_time')}",
                f"- **Phân loại**: {res.get('category')} ({is_mand})",
                f"- **Host**: {res.get('host') or 'BTC'}",
                f"- **Cập nhật mới nhất**: {res.get('updated_at')}",
            ]
            if res.get("source_msg_id"):
                seen_msg_ids.add(res["source_msg_id"])
        else:
            reply_lines.append(f"Không tìm thấy sự kiện nào có mã {target_sch_id}.")

    elif any(k in user_query.lower() for k in ("bận", "làm bài tập", "rảnh")):
        busy = tools.list_busy_slots_from_db(user_label, date_from=target_date, date_to=target_date)
        tool_trace.append({"tool": "list_busy_slots_from_db",
                           "args": {"user_label": user_label, "target_date": target_date},
                           "result_count": len(busy)})
        scheds = (query_schedules(date_from=target_date, date_to=target_date, status="active")
                  if target_date else query_schedules(status="active"))
        tool_trace.append({"tool": "query_schedules", "args": {"date": target_date, "status": "active"},
                           "result_count": len(scheds)})

        reply_lines.append(f"📌 **Kết quả sắp xếp thời khóa biểu cho {user_label}:**\n")
        if busy:
            reply_lines.append("🚫 **Lịch bận cá nhân đã ghi nhận của bạn:**")
            reply_lines += [f"   - {b['title']}: {b['start_time']} đến {b['end_time']}" for b in busy]
            reply_lines.append("")
        reply_lines.append("💡 **Lịch học trùng khoảng thời gian:**")
        if not scheds:
            reply_lines.append("   - Không có lịch học bắt buộc nào bị trùng trong khoảng thời gian này.")
        for s in scheds:
            is_mand = "Bắt buộc" if s.get("is_mandatory") else "Tùy chọn"
            reply_lines.append(f"   - [{s.get('id')}] {s.get('title')} ({s.get('start_time')} - {s.get('end_time')}) [{is_mand}]")
            if s.get("source_msg_id"):
                seen_msg_ids.add(s["source_msg_id"])

    else:
        date_from = f"{target_date}T00:00:00" if target_date else None
        date_to = f"{target_date}T23:59:59" if target_date else None
        scheds = tools.get_schedules_from_db(date_from=date_from, date_to=date_to, status="active")
        tool_trace.append({"tool": "get_schedules_from_db",
                           "args": {"date_from": date_from, "date_to": date_to},
                           "result_count": len(scheds)})
        reply_lines.append(
            f"📌 **Các lịch trình trong ngày {target_date}:**\n" if target_date
            else "📌 **Danh sách toàn bộ lịch trình active trong hệ thống:**\n"
        )
        if not scheds:
            reply_lines.append("Không tìm thấy thông báo lịch học nào trong khoảng thời gian này.")
        for idx, s in enumerate(scheds, 1):
            is_mand = "Bắt buộc" if s.get("is_mandatory") else "Tùy chọn"
            reply_lines += [
                f"{idx}. [{s.get('id')}] **{s.get('title')}** ({s.get('category')})",
                f"   - ⏰ Thời gian: {s.get('start_time')} - {s.get('end_time')}",
                f"   - 📌 Phân loại: {is_mand} | Host: {s.get('host') or 'BTC'}\n",
            ]
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
        # === CHẾ ĐỘ OFFLINE REACT TOOL ENGINE (Không cần API Key) ===
        # Tự động phân tích Intent, chọn Tool phù hợp trong tools.py và thực thi ReAct Loop
        import re
        
        # 1. Phân tích câu hỏi để chọn Tool
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", user_query)
        target_date = date_match.group(1) if date_match else None
        
        sch_match = re.search(r"(SCH_\d+)", user_query, re.IGNORECASE)
        target_sch_id = sch_match.group(1).upper() if sch_match else None
        
        reply_lines = []
        citations = []
        seen_msg_ids = set()

        if target_sch_id:
            # Intent: Tra cứu chi tiết theo ID
            res = tools.get_schedule_by_id(target_sch_id)
            tool_trace.append({"tool": "get_schedule_by_id", "args": {"sched_id": target_sch_id}, "result_count": 1 if "id" in res else 0})
            if "id" in res:
                is_mand = "Bắt buộc" if res.get("is_mandatory") else "Tùy chọn"
                reply_lines.append(f"📌 **Thông tin chi tiết cho sự kiện [{res['id']}]:**\n")
                reply_lines.append(f"- **Tiêu đề**: {res.get('title')}")
                reply_lines.append(f"- **Thời gian**: {res.get('start_time')} - {res.get('end_time')}")
                reply_lines.append(f"- **Phân loại**: {res.get('category')} ({is_mand})")
                reply_lines.append(f"- **Host**: {res.get('host') or 'BTC'}")
                reply_lines.append(f"- **Cập nhật mới nhất**: {res.get('updated_at')}")
                
                msg_id = res.get("source_msg_id")
                if msg_id:
                    seen_msg_ids.add(msg_id)
            else:
                reply_lines.append(f"Không tìm thấy sự kiện nào có mã {target_sch_id}.")

        elif "bận" in user_query.lower() or "làm bài tập" in user_query.lower() or "rảnh" in user_query.lower():
            # Intent: Tra cứu lịch bận + đối soát lịch học
            busy_slots = tools.list_busy_slots_from_db(user_label, date_from=target_date, date_to=target_date)
            tool_trace.append({"tool": "list_busy_slots_from_db", "args": {"user_label": user_label, "target_date": target_date}, "result_count": len(busy_slots)})
            
            schedules = query_schedules(date_from=target_date, date_to=target_date, status="active") if target_date else query_schedules(status="active")
            tool_trace.append({"tool": "query_schedules", "args": {"date": target_date, "status": "active"}, "result_count": len(schedules)})

            reply_lines.append(f"📌 **[ReAct Tool Loop Offline] Kết quả sắp xếp thời khóa biểu cho {user_label}:**\n")
            if busy_slots:
                reply_lines.append("🚫 **Lịch bận cá nhân đã ghi nhận của bạn:**")
                for b in busy_slots:
                    reply_lines.append(f"   - {b['title']}: {b['start_time']} đến {b['end_time']}")
                reply_lines.append("")
                
            reply_lines.append("💡 **Gợi ý slot rảnh & Lịch học trùng khoảng thời gian:**")
            if not schedules:
                reply_lines.append("   - Không có lịch học bắt buộc nào bị trùng trong khoảng thời gian này.")
            else:
                for s in schedules:
                    is_mand = "Bắt buộc" if s.get("is_mandatory") else "Tùy chọn"
                    reply_lines.append(f"   - [{s.get('id')}] {s.get('title')} ({s.get('start_time')} - {s.get('end_time')}) [{is_mand}]")
                    msg_id = s.get("source_msg_id")
                    if msg_id:
                        seen_msg_ids.add(msg_id)
        elif re.match(r"^[\?\.\!\s\:\;\-\=\_\+\*\/\#\@\$\%\^\&\(\)]+$", user_query.strip()):
            reply_lines.append("Xin chào! Bạn đang nhập ký tự nghi vấn hoặc câu hỏi mơ hồ. Bạn cần Trợ lý AI hỗ trợ tra cứu lịch học chính thức, hạn nộp bài hay giúp sắp xếp thời khóa biểu cá nhân?")
        else:
            # Intent chung: Lọc danh sách lịch trình
            date_from = f"{target_date}T00:00:00" if target_date else None
            date_to = f"{target_date}T23:59:59" if target_date else None
            
            schedules = tools.get_schedules_from_db(date_from=date_from, date_to=date_to, status="active")
            tool_trace.append({"tool": "get_schedules_from_db", "args": {"date_from": date_from, "date_to": date_to}, "result_count": len(schedules)})
            
            if target_date:
                reply_lines.append(f"📌 **Các lịch trình trong ngày {target_date}:**\n")
            else:
                reply_lines.append("📌 **Danh sách toàn bộ lịch trình active trong hệ thống:**\n")

            if not schedules:
                reply_lines.append("Không tìm thấy thông báo lịch học nào trong khoảng thời gian này.")
            else:
                for idx, s in enumerate(schedules, 1):
                    is_mand = "Bắt buộc" if s.get("is_mandatory") else "Tùy chọn"
                    reply_lines.append(f"{idx}. [{s.get('id')}] **{s.get('title')}** ({s.get('category')})")
                    reply_lines.append(f"   - ⏰ Thời gian: {s.get('start_time')} - {s.get('end_time')}")
                    reply_lines.append(f"   - 📌 Phân loại: {is_mand} | Host: {s.get('host') or 'BTC'}\n")
                    msg_id = s.get("source_msg_id")
                    if msg_id:
                        seen_msg_ids.add(msg_id)

        # Gom citations
        for msg_id in seen_msg_ids:
            m = get_message(msg_id)
            if m:
                citations.append({
                    "msg_id": m["msg_id"], "channel": m["channel"],
                    "sender": m["sender"], "time": m["created_at"],
                })

        return {
            "reply": "\n".join(reply_lines),
            "citations": citations,
            "tool_trace": tool_trace
        }

    # Hết MAX_TURNS mà model vẫn chưa chốt câu trả lời -> graceful fallback
    return {
        "reply": "Xin lỗi, câu hỏi này cần nhiều bước tra cứu hơn dự kiến. Bạn thử hỏi cụ thể hơn "
                 "(VD: nêu rõ khoảng ngày hoặc tên buổi học) giúp mình nhé, hoặc liên hệ Coach nếu gấp.",
        "citations": _build_refs(official_ids),
        "references": _build_refs(unofficial_ids - official_ids),
        "tool_trace": tool_trace,
        "mode": "llm",
    }
