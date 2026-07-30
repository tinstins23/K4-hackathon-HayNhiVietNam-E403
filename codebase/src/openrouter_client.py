"""
openrouter_client.py — wrapper mỏng gọi OpenRouter chat completions API.
OpenRouter tương thích format OpenAI, hỗ trợ `tools` (function calling).
Docs: https://openrouter.ai/docs
"""
import os
import json
import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _api_key():
    key = os.getenv("OPENROUTER_API_KEY")
    if not key or key.startswith("sk-or-v1-xxxx"):
        raise RuntimeError(
            "OPENROUTER_API_KEY chưa được set. Copy .env.example -> .env và điền key thật "
            "(lấy tại https://openrouter.ai/keys), KHÔNG commit file .env."
        )
    return key


def chat_completion(messages, model, tools=None, tool_choice=None,
                     temperature=0.2, response_format=None, timeout=60):
    """Gọi 1 lượt chat completion. Trả về message object thô từ API
    (có thể chứa .content hoặc .tool_calls)."""
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        # Khuyến nghị OpenRouter, không bắt buộc nhưng giúp app hiện đúng tên trên dashboard
        "HTTP-Referer": "https://github.com/tinstins23/K4-hackathon-HayNhiVietNam-E403",
        "X-Title": "Discord Schedule Assistant",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter lỗi {resp.status_code}: {resp.text[:500]}")
        data = resp.json()

    if "error" in data:
        raise RuntimeError(f"OpenRouter trả lỗi: {data['error']}")

    return data["choices"][0]["message"]


def parse_json_content(message):
    """Extraction Agent yêu cầu response_format json_object -> parse an toàn."""
    content = message.get("content") or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # fallback: model đôi khi bọc ```json ... ``` dù đã set response_format
        cleaned = content.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        return json.loads(cleaned)
