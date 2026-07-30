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

from db import query_schedules, search_messages, get_message, ROLE_PRIORITY
import tools
from openrouter_client import chat_completion

from systemprompt import SCHEDULER_SYSTEM_PROMPT as SYSTEM_PROMPT, get_scheduler_system_prompt

AGENT_MODEL = os.getenv("AGENT_MODEL", "google/gemini-2.0-flash-exp:free")
MAX_TURNS = 6


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_schedules",
            "description": "Truy vấn lịch học/deadline/mentoring chính thức đã được xác thực trong DB, lọc theo khoảng ngày/loại/trạng thái.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "ISO datetime, ví dụ 2026-07-30T00:00:00"},
                    "date_to": {"type": "string", "description": "ISO datetime"},
                    "category": {"type": "string", "enum": ["CLASS", "MENTORING", "DEADLINE", "WORKSHOP", "EVENT"]},
                    "status": {"type": "string", "enum": ["active", "canceled"], "description": "Mặc định 'active'"},
                    "mandatory_only": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_by_id",
            "description": "Truy vấn chi tiết 1 sự kiện lịch trình theo ID cụ thể (sched_id). Trả về thông tin đầy đủ gồm created_at, updated_at và source_msg_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sched_id": {"type": "string", "description": "ID lịch trình, ví dụ SCH_001"}
                },
                "required": ["sched_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_messages",
            "description": "Tìm tin nhắn thông báo gốc theo từ khóa (dùng khi cần thêm ngữ cảnh không có trong bảng lịch có cấu trúc, ví dụ slot bù, ghi chú thêm của Coach).",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "channel": {"type": "string", "enum": ["thong-bao-chung", "lich-hoc-moi"]},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_message",
            "description": "Lấy nguyên văn 1 tin nhắn theo msg_id để trích dẫn chính xác hoặc kiểm tra lại chi tiết.",
            "parameters": {
                "type": "object",
                "properties": {"msg_id": {"type": "string"}},
                "required": ["msg_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_busy_slots_from_db",
            "description": "Tra cứu danh sách thời gian bận cá nhân của học viên để né trùng giờ khi xếp thời khóa biểu.",
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
            "description": "Ghi nhận 1 khoảng thời gian bận cá nhân mới của học viên vào hệ thống.",
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


def _execute_tool(name, args):
    if name == "query_schedules":
        return query_schedules(
            date_from=args.get("date_from"), date_to=args.get("date_to"),
            category=args.get("category"), status=args.get("status", "active"),
            mandatory_only=args.get("mandatory_only"),
        )
    if name == "get_schedule_by_id":
        return tools.get_schedule_by_id(args.get("sched_id"))
    if name == "search_messages":
        return search_messages(args.get("keyword", ""), channel=args.get("channel"))
    if name == "get_message":
        msg = get_message(args.get("msg_id"))
        return msg or {"error": "not_found"}
    if name == "list_busy_slots_from_db":
        return tools.list_busy_slots_from_db(
            user_label=args.get("user_label"),
            date_from=args.get("date_from"),
            date_to=args.get("date_to")
        )
    if name == "add_personal_busy_slot":
        return tools.add_personal_busy_slot(
            user_label=args.get("user_label"),
            title=args.get("title"),
            start_time=args.get("start_time"),
            end_time=args.get("end_time")
        )
    return {"error": f"unknown tool {name}"}


def _collect_citations(tool_result):
    """Gom mọi source_msg_id / msg_id xuất hiện trong 1 kết quả tool (list hoặc dict)."""
    ids = set()
    items = tool_result if isinstance(tool_result, list) else [tool_result]
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("source_msg_id"):
            ids.add(it["source_msg_id"])
        if it.get("msg_id"):
            ids.add(it["msg_id"])
    return ids


def ask(user_query: str, reference_date: str, history: list = None, user_label: str = "học viên"):
    """Chạy 1 vòng ReAct loop đầy đủ, trả về dict:
    { reply: str, citations: [ {msg_id, channel, sender, time} ], tool_trace: [...] }
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\n\nreference_date: {reference_date}"}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_query})

    all_citation_ids = set()
    tool_trace = []

    try:
        for _ in range(MAX_TURNS):
            msg = chat_completion(messages=messages, model=AGENT_MODEL, tools=TOOLS, temperature=0.2)
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                reply_text = msg.get("content") or ""
                citations = []
                for msg_id in all_citation_ids:
                    m = get_message(msg_id)
                    if m:
                        citations.append({
                            "msg_id": m["msg_id"], "channel": m["channel"],
                            "sender": m["sender"], "time": m["created_at"],
                        })
                return {"reply": reply_text, "citations": citations, "tool_trace": tool_trace}

            # model muốn gọi tool -> append assistant turn kèm tool_calls, rồi thực thi từng cái
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
            for call in tool_calls:
                fn_name = call["function"]["name"]
                try:
                    fn_args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                result = _execute_tool(fn_name, fn_args)
                all_citation_ids |= _collect_citations(result)
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
        "citations": [],
        "tool_trace": tool_trace,
    }
