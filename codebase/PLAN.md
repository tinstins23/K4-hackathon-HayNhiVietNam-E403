# Kế hoạch Backend + Chatbot — Nhóm HayNhiVietNam (Zone 4)

> Chưa rõ dự án này là gì / giải quyết vấn đề gì? Đọc `README.md` (cùng thư mục `codebase/`)
> mục "Đây là dự án gì" + "Vấn đề đang giải quyết" TRƯỚC — file này chỉ liệt kê việc cần làm,
> không nhắc lại bối cảnh.

Bám theo mốc còn lại trong `README.md` gốc ở thư mục cha (Khoá 4): CP4 23:59 hôm nay (nộp spec,
không chặn code) → CP5 14:00 ngày 2 (dry run) → CP6 15:00 ngày 2 (demo).

## Đã xong (trong nhánh code này)

- [x] `db.py` — schema `messages` + `official_schedules` + `personal_busy_slots`, có FK,
      có `update_schedule`/`cancel_schedule` ghi đè theo `updated_at` mới nhất.
- [x] `ingestion.py` — Extraction Agent gọi OpenRouter, tự quyết định create/update/cancel/ignore,
      so khớp với danh sách sự kiện active để không tạo trùng khi tin nhắn chỉ là "sửa giờ".
- [x] `agent.py` — ReAct Agent, tool-calling loop thật (`query_schedules`, `search_messages`,
      `get_message`), ép trích dẫn 100% bằng code chứ không chỉ bằng prompt.
- [x] `main.py` — FastAPI: `/chat`, `/ingest`, `/messages/{channel}`, `/schedules`, CORS mở
      để `mock_ui` gọi được từ `file://` hoặc `localhost`.
- [x] `seed_data.py` — nạp đúng data đang hiển thị trong `mock_ui/index.html` qua ingestion thật.
- [x] Patch `mock_ui/index.html`: ô chat tự do (`handleUserSubmit`) gọi thật `/chat` thay vì
      `setTimeout` hardcode. 5 nút kịch bản giữ nguyên mock để demo an toàn.
- [x] Đã test offline: `db.py` CRUD + FK constraint + `main.py` load routes — chạy sạch,
      không lỗi cú pháp. Chưa test được lượt gọi OpenRouter thật (cần API key, máy mình không
      có mạng ra ngoài domain đó) — **việc đầu tiên Tín/Hùng cần làm khi có key**.

## Việc cần làm ngay (ưu tiên theo thời gian còn lại)

### 1. Chạy thử thật với OPENROUTER_API_KEY (Tín/Hùng — trước hết)
```bash
cd codebase && cp .env.example .env   # điền key thật
cd src && python seed_data.py         # xem log action=create/update/cancel có đúng ý không
uvicorn main:app --reload --port 8000
```
Nếu Extraction Agent trích sai (VD: nhầm "update" thành "create" gây trùng lịch) → sửa
`EXTRACTION_SYSTEM_PROMPT` trong `ingestion.py`, đây là việc của **Quân** (prompt engineering).

### 2. Nối 2 nút kịch bản còn lại vào backend thật (Tín/Hùng)
`triggerInstructorPostNewSpec` và `triggerInstructorEditMentoring` trong `mock_ui/index.html`
mới chỉ đổi state JS. Thêm 1 lệnh `fetch('/ingest', {...})` trong mỗi hàm để backend thật ghi
nhận — khi đó Nút 4 ("AI RE-SCHEDULING") mới thật sự dùng dữ liệu đã cập nhật thay vì state giả.

### 3. Mở rộng golden set 2 → ≥20 case (Quân — gấp nhất cho R4, 15 điểm)
Cấu trúc đã có sẵn trong `eval/golden_set.json`. Cần thêm:
- ≥2 case cho mỗi lớp trong 4 lớp chỗ khó ở `spec.md §5` (hiện có 8 kịch bản mô tả sẵn, chỉ
  cần chuyển thành testcase có `expected_intent`/`expected_contains`/`requires_citation`)
- 8-10 case thường (giống TC_001, TC_002 đã có)
- 2-4 case hiếm (câu hỏi lạ, câu hỏi trống, câu hỏi ngoài phạm vi)
- ≥10 case cần bám vào **dữ liệu thật đã mining được** (không phải data giả) — nếu nhóm dùng
  data Discord thật của khóa để mining (theo README gốc: "teams mine Discord directly"), viết
  case dựa trên tin nhắn thật đó.

Viết thêm `eval/eval_runner.py` gọi thẳng `/chat`, so khớp kết quả tự động — không chấm tay.

### 4. Bot Discord thật (nếu còn thời gian — không bắt buộc cho prototype mức Working)
`spec.md §4` khai "Mức Working" nhưng cho phép phần mock (lịch bận cá nhân). Bot Discord thật
(nghe `on_message` → gọi `ingestion.ingest_message`) là điểm cộng cho R5 nhưng KHÔNG bắt buộc —
demo qua `mock_ui` + backend thật đã đủ đạt "≥1 lời gọi AI thật ở quyết định trung tâm".
Nếu làm, xem hướng dẫn trong `codebase/README.md` mục "Việc còn thiếu".

## Rủi ro cần biết trước CP5 (dry run)

- **Model OpenRouter chưa chọn cụ thể**: `.env.example` để mặc định `openai/gpt-4o-mini` —
  cần Tín/Hùng xác nhận model này có tool-calling ổn định và còn credit free/trả phí đủ dùng.
  Nếu đổi model, chỉ cần sửa biến môi trường, không đụng code.
- **Chi phí/tốc độ ReAct loop**: mỗi câu hỏi có thể tốn 2-4 lượt gọi API (`MAX_TURNS=6` trong
  `agent.py`) — nên test độ trễ thật trước khi demo trực tiếp trên sân khấu, tránh chờ lâu.
- **Golden set 2/20** là lỗ hổng điểm rõ ràng nhất hiện tại — ưu tiên xử lý trước khi lo thêm
  tính năng mới.
