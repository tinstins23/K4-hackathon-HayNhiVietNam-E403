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
from openrouter_client import chat_completion

AGENT_MODEL = os.getenv("AGENT_MODEL", "openai/gpt-4o-mini")
MAX_TURNS = 6

SYSTEM_PROMPT = """Bạn là "Schedule AI Assistant" — trợ lý AI quản lý & sắp xếp lịch trình cho học
viên khóa AI Thực Chiến, hoạt động trong kênh Discord #tro-ly-lich-trinh.

NGUYÊN TẮC BẮT BUỘC (không được vi phạm):
1. NGUỒN SỰ THẬT: Chỉ được nói về lịch học/deadline dựa trên kết quả trả về từ tool
   `query_schedules` hoặc `search_messages`. TUYỆT ĐỐI không tự bịa ra lịch không có
   trong kết quả tool. Nếu tool trả về rỗng cho khoảng thời gian được hỏi, trả lời rõ:
   "Không tìm thấy thông báo lịch học trong khoảng thời gian này."
2. MƠ HỒ: Nếu câu hỏi không rõ ý định (VD: "chiều nay rảnh không?" — không rõ đang hỏi lịch
   học bắt buộc hay đang hỏi để sắp lịch làm bài tập cá nhân), hãy hỏi lại để làm rõ thay vì đoán.
3. NGOÀI PHẠM VI: Không có quyền tự ý "duyệt" dời lịch chung của cả lớp, không trả lời đề thi/đáp
   án bài tập. Với các yêu cầu này, từ chối lịch sự và hướng dẫn liên hệ Admin/BTC qua kênh chính thức.
4. XUNG ĐỘT: Khi có 2 bản ghi cùng thời điểm, LUÔN ưu tiên bản ghi có `updated_at` mới nhất và
   status='active'. Khi lịch bắt buộc (is_mandatory=true) trùng lịch cá nhân/tùy chọn, cảnh báo rõ
   ràng và ưu tiên lịch bắt buộc.
5. GIẢI THÍCH LÝ DO: Khi đề xuất 1 khung giờ, luôn nói rõ vì sao chọn khung đó (VD: "vì sáng T4
   bạn đã bận theo lịch X").
6. Sau khi trả lời, LUÔN nhắc gọn nguồn thông báo gốc bạn đã dùng (id sự kiện / kênh) trong câu
   trả lời — hệ thống sẽ tự đính kèm link chi tiết bên dưới câu trả lời của bạn.
7. Được phép gọi tool NHIỀU LẦN (vd. mở rộng khoảng ngày, thử từ khóa khác) trước khi kết luận
   không có lịch — đừng dừng lại chỉ sau 1 lần query rỗng nếu còn cách hợp lý để tìm thêm.

Hôm nay là ngày được cung cấp trong tin nhắn hệ thống dưới đây (`reference_date`)."""

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
]


def _execute_tool(name, args):
    if name == "query_schedules":
        return query_schedules(
            date_from=args.get("date_from"), date_to=args.get("date_to"),
            category=args.get("category"), status=args.get("status", "active"),
            mandatory_only=args.get("mandatory_only"),
        )
    if name == "search_messages":
        return search_messages(args.get("keyword", ""), channel=args.get("channel"))
    if name == "get_message":
        msg = get_message(args.get("msg_id"))
        return msg or {"error": "not_found"}
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

    # Hết MAX_TURNS mà model vẫn chưa chốt câu trả lời -> graceful fallback
    return {
        "reply": "Xin lỗi, câu hỏi này cần nhiều bước tra cứu hơn dự kiến. Bạn thử hỏi cụ thể hơn "
                 "(VD: nêu rõ khoảng ngày hoặc tên buổi học) giúp mình nhé, hoặc liên hệ Coach nếu gấp.",
        "citations": [],
        "tool_trace": tool_trace,
    }
