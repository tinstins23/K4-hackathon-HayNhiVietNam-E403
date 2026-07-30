"""
openrouter_client.py — wrapper mỏng gọi OpenRouter chat completions API.
OpenRouter tương thích format OpenAI, hỗ trợ `tools` (function calling).
Docs: https://openrouter.ai/docs
"""
import os
import json
import time
import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# 429 = rate limit (hay gặp với model :free), 5xx = provider lỗi tạm thời
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = int(os.getenv("OPENROUTER_MAX_RETRIES", "4"))
RETRY_BACKOFF = float(os.getenv("OPENROUTER_RETRY_BACKOFF", "1.0"))


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

    # Các model ":free" trên OpenRouter chập chờn — đo thực tế thấy ~20% lượt gọi trả
    # 500/429. Không retry thì demo trực tiếp rất dễ chết giữa chừng. Chỉ thử lại với
    # lỗi TẠM THỜI; lỗi 401/400 (sai key, sai payload) thì ném ngay, retry vô ích.
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(OPENROUTER_URL, headers=headers, json=payload)

            if resp.status_code in RETRYABLE_STATUS:
                last_err = RuntimeError(f"OpenRouter lỗi {resp.status_code}: {resp.text[:300]}")
            elif resp.status_code != 200:
                raise RuntimeError(f"OpenRouter lỗi {resp.status_code}: {resp.text[:500]}")
            else:
                data = resp.json()
                if "error" in data:
                    # OpenRouter đôi khi trả HTTP 200 nhưng body chứa error (VD provider 500)
                    last_err = RuntimeError(f"OpenRouter trả lỗi: {data['error']}")
                else:
                    return data["choices"][0]["message"]

        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = RuntimeError(f"Lỗi mạng tới OpenRouter: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF * (2 ** attempt))

    raise last_err


def parse_json_content(message):
    """Extraction Agent yêu cầu response_format json_object -> parse an toàn."""
    content = message.get("content") or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        cleaned = content.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        return json.loads(cleaned)
