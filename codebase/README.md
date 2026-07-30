# PROTOTYPE CODEBASE — Trợ lý AI Sắp Xếp Lịch Trình Discord

> Đọc file này TRƯỚC KHI sửa bất kỳ code nào. Nguồn sự thật đầy đủ nhất về đề bài, tiêu chí
> chấm, và thiết kế đã chốt là `spec.md` (thư mục gốc repo `repo/spec.md`) — file README này
> chỉ tóm tắt phần liên quan tới việc code backend.

## Đây là dự án gì

Bài nộp của nhóm **HayNhiVietNam** (Zone 4) cho **Mini Hackathon AI — Batch 03** (xem
`README.md` gốc ở thư mục cha để biết luật, mốc CP1-CP6, cách chấm điểm). Đây **không phải**
sản phẩm thương mại hoàn chỉnh — đây là 1 **prototype 1,5 ngày** để chứng minh 1 lát cắt tính
năng AI chạy được thật, có bằng chứng, có đo lường — chấm theo `04-rubric.md`.

## Vấn đề đang giải quyết (job của người dùng)

Học viên khóa **AI Thực Chiến** nhận thông báo lịch học/deadline/mentoring rải rác trên nhiều
kênh Discord (`#thong-bao-chung`, `#lich-hoc-moi`...), thông báo dày và **hay đổi đột xuất**
(dời giờ, hủy buổi). Khảo sát 20 học viên → **>60%** xác nhận mất 30-45 phút/tuần để tự gom
lại thành lịch cá nhân, và hay phải hỏi lại Coach gây phiền. Chi tiết đầy đủ + quote nguyên văn:
`spec.md §1`.

## Sản phẩm build ra để giải quyết vấn đề đó

**1 trợ lý AI trong kênh Discord `#tro-ly-lich-trinh`**: học viên gõ câu hỏi tự nhiên
(VD: *"Tuần này tôi có lịch bắt buộc nào?"*, *"Xếp lịch làm bài tránh sáng T4 tôi bận"*) →
AI tự tra cứu DB lịch đã được trích xuất từ các thông báo Discord thật (không phải hỏi
Coach) → trả lời kèm **trích dẫn nguồn tin nhắn gốc** (để học viên tự kiểm chứng, không phải
tin mù) → nếu không tìm thấy lịch, nói rõ thay vì bịa. Lát cắt chính xác: `spec.md §4`.

## Kiến trúc kỹ thuật ở mức khái niệm (trước khi đọc code)

Có **2 luồng AI riêng biệt**, đừng nhầm lẫn khi đọc code:

1. **Ingestion (nền, tự động)** — mỗi khi có tin nhắn thông báo mới/sửa từ Coach/GV/BTC trong
   `#thong-bao-chung` hoặc `#lich-hoc-moi` → 1 "Extraction Agent" (LLM) đọc tin nhắn đó, quyết
   định đây là lịch mới / sửa lịch cũ / hủy lịch, rồi ghi vào DB có cấu trúc. Việc này chạy
   ngầm, học viên không thấy trực tiếp. Code: `src/ingestion.py`.
2. **Trả lời câu hỏi (khi học viên hỏi)** — 1 "ReAct Agent" (LLM có tool-calling) nhận câu hỏi
   học viên, tự gọi tool truy vấn DB (nhiều lần nếu cần) rồi tổng hợp câu trả lời kèm nguồn.
   Code: `src/agent.py`.

Cả 2 đều gọi qua **OpenRouter** (không phải gọi thẳng OpenAI/Anthropic) — xem `src/openrouter_client.py`.

## Mục tiêu cụ thể của việc code hôm nay/mai

Không phải "làm cho đẹp" — mục tiêu là đạt được các dòng cụ thể trong `04-rubric.md`:
- **R5 (8đ)**: prototype chạy **end-to-end thật**, có **≥1 lời gọi AI thật** ở quyết định trung
  tâm (không phải toàn bộ hardcode như `mock_ui` bản gốc).
- **R4 (15đ)**: ≥20 test case trong `eval/golden_set.json`, mỗi chiều chất lượng đo được, đặc
  biệt **100% câu trả lời về lịch phải kèm trích dẫn** `source_msg_id` — đây là lý do
  `agent.py` ép trích dẫn bằng code chứ không chỉ nhờ prompt (xem mục "Vì sao trích dẫn..."
  bên dưới).
- **R1-R3 đã chốt trong `spec.md`**, không cần code động vào — chỉ cần code **khớp đúng** với
  những gì spec đã khai (VD: 4 lớp chỗ khó ở `spec.md §5` phải thấy được trong logic code,
  không chỉ nằm trên giấy).

## Việc CẦN làm ngay khi bắt đầu 1 phiên Claude Code mới

Đọc thêm `PLAN.md` (cùng thư mục) để biết việc gì đã xong, việc gì đang thiếu, ưu tiên theo
thứ tự nào. Đừng tự ý đổi kiến trúc (FastAPI + SQLite + OpenRouter tool-calling) nếu không
được yêu cầu rõ — kiến trúc này đã được thống nhất và một phần đã test offline chạy đúng.

---

## Kiến trúc

```
mock_ui/index.html   [Mock UI]      giao diện Discord giả lập
        │  fetch('http://localhost:8000/chat')  ← ô chat tự do gọi AI THẬT
        ▼
src/main.py          [Working]      FastAPI — /chat /ingest /messages /schedules
        │
        ├── src/agent.py       ReAct Agent (OpenRouter, tool-calling) trả lời học viên
        ├── src/ingestion.py   Extraction Agent (OpenRouter) trích lịch từ tin nhắn
        ├── src/db.py          SQLite: messages (thô) + official_schedules (đã trích xuất)
        └── src/openrouter_client.py   wrapper gọi OpenRouter chat completions
```

Phân định mock/thật theo đúng yêu cầu README gốc của BTC:

| Thành phần | Mức | Ghi chú |
|---|---|---|
| `mock_ui/` — 5 nút kịch bản dựng sẵn | **Mock** | Giữ nguyên để demo an toàn không phụ thuộc mạng/API key lúc lên sân khấu |
| `mock_ui/` — ô nhập chat tự do | **Working** | Gọi thật `/chat`, đi qua ReAct Agent + OpenRouter + SQLite |
| `src/agent.py`, `src/ingestion.py` | **Working** | Gọi OpenRouter thật, có tool-calling loop thật |
| `src/db.py` | **Working** | SQLite thật, không hardcode data (trừ `seed_data.py` dùng để demo) |

## Cài đặt & chạy

```bash
cd codebase
python3 -m venv venv && source venv/bin/activate   # hoặc dùng venv có sẵn
pip install -r requirements.txt

cp .env.example .env
# mở .env, điền OPENROUTER_API_KEY (lấy tại https://openrouter.ai/keys)
# KHÔNG commit file .env

cd src
python seed_data.py         # nạp dữ liệu mẫu (đúng data trong mock_ui) qua Extraction Agent thật
uvicorn main:app --reload --port 8000
```

Mở `mock_ui/index.html` bằng trình duyệt (hoặc `python -m http.server` trong thư mục `mock_ui/`),
gõ câu hỏi vào ô chat trong kênh `#tro-ly-lich-trinh` — sẽ gọi thẳng vào backend vừa chạy ở `localhost:8000`.

Test nhanh bằng curl (không cần UI):

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tuần này tôi có những lịch học bắt buộc nào?"}'
```

## Vì sao trích dẫn (citation) luôn đạt 100%

`agent.py` không dựa vào việc LLM "nhớ" nhắc nguồn trong câu trả lời. Mọi `source_msg_id` xuất
hiện trong kết quả các tool đã gọi ở lượt hỏi đó được backend **tự động gom lại theo code**
(`_collect_citations`) và trả về ở field `citations` riêng, tách khỏi `reply`. UI luôn hiển thị
được nguồn dù model có quên nhắc trong text hay không — đáp ứng đúng quality bar
`spec.md §7`: "100% trích dẫn đúng ID thông báo Discord gốc".

## 4 lớp chỗ khó (spec.md §5) — chỗ nào xử lý ở đâu trong code

| # | Chỗ khó | Xử lý ở đâu |
|---|---|---|
| ① Nguồn sự thật | `agent.py` — system prompt cấm bịa; chỉ nói dựa trên kết quả tool. `ingestion.py` — set `status='canceled'` ngay khi có thông báo hủy |
| ② Mơ hồ | `agent.py` — system prompt yêu cầu hỏi lại khi ý định không rõ, thay vì đoán |
| ③ Ngoài phạm vi | `agent.py` — system prompt từ chối yêu cầu dời lịch chung/đề thi, hướng dẫn liên hệ Admin |
| ④ Đặc thù domain | `db.py update_schedule/cancel_schedule` — luôn ghi đè theo `updated_at` mới nhất; `agent.py` — ưu tiên lịch `is_mandatory=true` khi xung đột |

## Việc còn thiếu (để Tín/Hùng/Quân tiếp tục)

1. **Bot Discord thật** (`discord.py` listener) chưa có — hiện `/ingest` chỉ nhận qua HTTP
   (dùng `seed_data.py` hoặc curl để giả lập). Việc còn lại: viết 1 file `discord_bot.py` nhỏ,
   nghe `on_message`/`on_message_edit` trong `#thong-bao-chung` và `#lich-hoc-moi`, gọi
   `ingestion.ingest_message(...)` trực tiếp (không cần qua HTTP vì chạy chung process cũng được).
2. **2 nút kịch bản demo** (`triggerInstructorPostNewSpec`, `triggerInstructorEditMentoring` trong
   `mock_ui/index.html`) hiện chỉ đổi state JS phía client. Nên gọi thêm `fetch('/ingest', ...)`
   trong 2 hàm đó để backend thật sự ghi nhận thay đổi — khi đó phần "AI RE-SCHEDULING AFTER
   DYNAMIC DISCORD EDITS" (Nút 4) mới phản ánh đúng dữ liệu thật thay vì state giả lập.
3. **Golden set chỉ có 2/20 case** — rubric R4 yêu cầu ≥20 (≥2/lớp chỗ khó, 8-10 case thường,
   2-4 case hiếm, ≥10 case bám theo data mining thật). Việc của Quân: viết thêm case + script
   `eval_runner.py` gọi `/chat` thật rồi so khớp `expected_intent`/`expected_contains`/`requires_citation`.
4. **Personal busy slots** hiện có bảng `personal_busy_slots` nhưng chưa có tool cho agent đọc —
   MVP hiện xử lý lịch bận bằng cách để model đọc trực tiếp trong câu hỏi (đủ cho demo theo
   "lát cắt MỘT CÂU" trong spec.md §4). Nếu còn thời gian, thêm tool `add_busy_slot`/`list_busy_slots`
   vào `agent.py` để AI tự ghi nhớ lịch bận qua nhiều lượt hỏi.
