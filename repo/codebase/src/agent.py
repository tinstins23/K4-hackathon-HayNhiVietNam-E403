"""
agent.py — ReAct agent: chỉ tra cứu bảng messages (search_messages / get_message).
"""
import os
import json

from db import search_messages, get_message, list_recent_messages, to_vn_display
from openrouter_client import chat_completion
from systemprompt import SCHEDULER_SYSTEM_PROMPT as SYSTEM_PROMPT, get_scheduler_system_prompt

AGENT_MODEL = os.getenv("AGENT_MODEL", "google/gemma-4-26b-a4b-it:free")
MAX_TURNS = 6
# Trả lời liệt kê lịch tuần cần nhiều token hơn mặc định 250 của openrouter_client.
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "1200"))

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_official_messages",
            "description": (
                "List recent OFFICIAL Discord announcements (newest first), with full content. "
                "USE THIS FIRST for questions like 'lịch tuần sau', 'ngày mai học gì', weekly roadmap. "
                "Do not invent schedules — extract from returned content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max messages (default 50).",
                    },
                    "channel": {
                        "type": "string",
                        "description": "Optional channel name filter.",
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
                "Keyword search in raw Discord messages. Prefer list_official_messages for "
                "broad week/day questions; use this to refine (e.g. 'mentoring', 'deadline'). "
                "date_from/date_to filter POST time (created_at), NOT event date in the text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "channel": {
                        "type": "string",
                        "description": "Discord channel name. Empty = all.",
                    },
                    "only_official": {
                        "type": "boolean",
                        "description": "true = official only (recommended for schedules).",
                    },
                    "sender_role": {
                        "type": "string",
                        "enum": ["btc", "instructor", "coach", "mentor", "student"],
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Filter by message created_at (UTC ISO). Not event date.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Filter by message created_at (UTC ISO). Not event date.",
                    },
                    "limit": {"type": "integer", "description": "Default 40."},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_message",
            "description": "Fetch the exact original text of 1 message by msg_id.",
            "parameters": {
                "type": "object",
                "properties": {"msg_id": {"type": "string"}},
                "required": ["msg_id"],
            },
        },
    },
]

_SYSTEM_TIME_KEYS = ("created_at", "updated_at", "edited_at")


def _convert_display_times(data):
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
    if name == "list_official_messages":
        return _convert_display_times(list_recent_messages(
            limit=int(args.get("limit") or 50),
            only_official=True,
            channel=args.get("channel"),
        ))
    if name == "search_messages":
        return _convert_display_times(search_messages(
            args.get("keyword", ""),
            channel=args.get("channel"),
            only_official=args.get("only_official"),
            sender_role=args.get("sender_role"),
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            limit=int(args.get("limit") or 40),
        ))
    if name == "get_message":
        msg = get_message(args.get("msg_id"))
        return _convert_display_times(msg) if msg else {"error": "not_found"}
    return {"error": f"unknown tool {name}"}


def _collect_citations(tool_result):
    """Gom msg_id theo mức tin cậy (official vs student)."""
    official, unofficial = set(), set()
    items = tool_result if isinstance(tool_result, list) else [tool_result]
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("msg_id"):
            (official if it.get("is_official") else unofficial).add(it["msg_id"])
    return official, unofficial


def _build_refs(msg_ids):
    refs = []
    for msg_id in sorted(msg_ids):
        m = get_message(msg_id)
        if m:
            refs.append({
                "msg_id": m["msg_id"], "channel": m["channel"],
                "sender": m["sender"], "sender_role": m["sender_role"],
                "time": to_vn_display(m["created_at"]), "is_official": m["is_official"],
            })
    return refs


ERROR_DEFAULT = (
    "⚠️ **Hệ thống AI hiện đang bận hoặc gặp sự cố kết nối tạm thời.**\n\n"
    "Bạn vui lòng thử lại sau giây lát hoặc liên hệ trực tiếp Ban Tổ Chức / Coach qua các kênh chính thức nhé!"
)


def ask(user_query: str, reference_date: str, history: list = None, user_label: str = "học viên"):
    messages = [{"role": "system", "content": get_scheduler_system_prompt(reference_date, user_label)}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_query})

    official_ids, unofficial_ids = set(), set()
    tool_trace = []

    try:
        for _ in range(MAX_TURNS):
            msg = chat_completion(
                messages=messages,
                model=AGENT_MODEL,
                tools=TOOLS,
                temperature=0.1,
                max_tokens=AGENT_MAX_TOKENS,
            )
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return {
                    "reply": msg.get("content") or "",
                    "citations": _build_refs(official_ids),
                    "references": _build_refs(unofficial_ids - official_ids),
                    "tool_trace": tool_trace,
                    "mode": "llm",
                }

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
                tool_trace.append({
                    "tool": fn_name,
                    "args": fn_args,
                    "result_count": len(result) if isinstance(result, list) else 1,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

    except RuntimeError as err:
        # Log rõ nguyên nhân (429/key/model...) — trước đây nuốt im -> khó debug mode=error.
        print(f"❌ [ReAct LLM RuntimeError]: {err}")
        return {
            "reply": ERROR_DEFAULT,
            "citations": [],
            "references": [],
            "tool_trace": tool_trace,
            "mode": "error",
            "llm_error": str(err)[:500],
        }

    return {
        "reply": "Xin lỗi, câu hỏi này cần nhiều bước tra cứu hơn dự kiến. Bạn thử hỏi cụ thể hơn "
                 "(VD: nêu rõ khoảng ngày hoặc tên buổi học) giúp mình nhé, hoặc liên hệ Coach nếu gấp.",
        "citations": _build_refs(official_ids),
        "references": _build_refs(unofficial_ids - official_ids),
        "tool_trace": tool_trace,
        "mode": "llm",
    }
