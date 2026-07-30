# Kế hoạch Backend + Chatbot — Nhóm HayNhiVietNam (Zone 4)

> Chưa rõ dự án này là gì / giải quyết vấn đề gì? Đọc `README.md` (cùng thư mục `codebase/`)
> mục "Đây là dự án gì" + "Vấn đề đang giải quyết" TRƯỚC.

Bám theo mốc còn lại trong `README.md` gốc ở thư mục cha: CP4 23:59 hôm nay (nộp spec) → CP5 14:00 ngày 2 (dry run) → CP6 15:00 ngày 2 (demo).

## Đã hoàn thành

- [x] `db.py` — schema `messages` + `official_schedules` + `personal_busy_slots`, có FK, `update_schedule`/`cancel_schedule`.
- [x] `ingestion.py` — Extraction Agent (OpenRouter) tự trích xuất create/update/cancel/ignore.
- [x] `agent.py` — ReAct Agent tool-calling loop (`query_schedules`, `search_messages`, `get_message`), ép trích dẫn nguồn.
- [x] `main.py` — FastAPI: `/chat`, `/ingest`, `/messages/{channel}`, `/schedules`.
- [x] `seed_data.py` — nạp dữ liệu mẫu hiển thị trong `mock_ui/index.html`.
- [x] `discord_bot.py` — Tích hợp Bot Discord thật với biến môi trường `.env`.
- [x] `mock_ui/index.html` — Interactive UI mượt mà với logo SVG Discord, 5 nút kịch bản AI Planning, nút giả lập đăng/sửa bài real-time, jump-to-message citation link.

## Hướng dẫn khởi chạy

```bash
cd repo/codebase
pip install -r requirements.txt
cp .env.example .env

# Chạy FastAPI backend
uvicorn src.main:app --reload --port 8000

# Hoặc chạy Discord Bot thật
python src/discord_bot.py
```
