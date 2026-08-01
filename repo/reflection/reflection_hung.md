# REFLECTION CÁ NHÂN — Nguyễn Xuân Hùng (`2A202601640`)

**Vai trò**: Backend Codebase & Discord Interfacer — SQLite DB, ingestion pipeline, System Prompt.

## 1. Phần mình làm trong repo
- `codebase/src/db.py` — lớp lưu trữ SQLite: bảng `official_schedules`/`messages`, cơ chế idempotency (`idempotency_locks` + `try_claim()`) chống trích xuất/trả lời trùng khi 1 tin nhắn Discord bị xử lý nhiều lần, và quy đổi giờ UTC↔VN (`VN_TZ`, `to_vn_display()`, `vn_now()`) để AI không đọc nhầm giờ khi kể lại cho học viên.
- `codebase/src/ingestion.py` — Extraction Agent: gọi LLM trích tin nhắn thô thành lịch có cấu trúc (create/update/cancel), thêm cảnh báo/giới hạn độ dài cho tin nhắn quá dài để tránh tốn quota model free-tier.
- `codebase/src/discord_bot.py` — tích hợp bot Discord thật: dùng `asyncio.to_thread()` tách các lời gọi OpenRouter (đồng bộ, blocking) khỏi event loop chính để không treo heartbeat gây rớt kết nối/mất tin nhắn; định dạng trích dẫn nguồn kèm jump-link tới tin nhắn gốc trên Discord.
- `codebase/src/systemprompt.py` — viết System Prompt tiếng Anh cho ReAct Scheduler Agent: chống prompt-injection/thao túng, ép xác định phạm vi câu hỏi trước khi gọi tool (tiết kiệm token khi học viên đổi ý giữa chừng), bắt buộc đối chiếu `query_schedules` (kể cả `status=canceled`) trước khi khẳng định 1 sự kiện còn hiệu lực.

## 2. AI hỗ trợ thế nào
- Dùng AI để rà lỗi runtime (race condition khi trích xuất trùng, UNIQUE constraint do tái sử dụng ID, lệch múi giờ) bằng cách đối chiếu trực tiếp dữ liệu trong `schedules.db` với hành vi thực tế của bot, thay vì chỉ đoán từ log hoặc ảnh chụp màn hình.
- Phần mình **tự chịu trách nhiệm giải thích**: vì sao cần idempotency ở tầng DB (không chỉ ở tầng ứng dụng) khi có thể có nhiều tiến trình/luồng cùng ghi vào cùng 1 file DB; và vì sao timestamp hệ thống phải luôn lưu UTC ở tầng lưu trữ nhưng quy đổi ra giờ VN ở mọi nơi hiển thị/suy luận.

## 3. Bài học từ case fail của nhóm
- Case thật gặp phải: AI từng khẳng định chắc nịch 1 buổi họp đã bị hủy là "vẫn diễn ra" — nguyên nhân là tầng Q&A đọc thẳng `search_messages` (text thô) mà không đối chiếu lại `query_schedules`/`status`. Đây đúng là dạng lỗi tự tin-nhưng-sai góp phần vào kết quả eval của nhóm (pass **76.9%** so với bar **≥90%**, citation **60%** so với bar **100%**).
- Một case khác: thiếu khoá idempotency khiến 1 tin nhắn thông báo bị trích xuất 2 lần, tạo lịch trùng và trả lời trùng cho học viên — chỉ phát hiện được khi so trực tiếp dữ liệu trong DB, không thấy rõ nếu chỉ đọc log hoặc chỉ nhìn giao diện Discord.
- Bài học: độ tin cậy của Agent phụ thuộc rất nhiều vào tầng dữ liệu bên dưới — tool trả về đúng, đủ, không trùng, đúng múi giờ quan trọng ngang với việc viết prompt hay; sai ở tầng nào trong hai tầng này cũng dẫn tới câu trả lời sai mà rất khó phát hiện nếu không kiểm tra chéo với dữ liệu thật.
