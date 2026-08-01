# REFLECTION CÁ NHÂN — HÙNG

**Vai trò**: Phụ trách Build Backend Codebase & Discord Interfacer

## 1. Bài học tâm đắc nhất
- Đưa dữ liệu thông báo thô từ Discord về dạng dữ liệu có cấu trúc (`official_schedules`) giúp chặn hoàn toàn lỗi ảo giác (hallucination).
- Idempotency (khoá theo msg_id) là bắt buộc khi 1 sự kiện Discord có thể kích hoạt ingest nhiều lần — thiếu nó gây trùng lịch/trả lời trùng, rất khó phát hiện nếu không đối chiếu trực tiếp DB.
- Timestamp hệ thống phải LUÔN lưu UTC ở tầng dữ liệu, chỉ quy đổi giờ Việt Nam ở tầng hiển thị — trộn lẫn 2 múi giờ ngay trong DB gây lỗi âm ỉ, khó truy vết hơn nhiều so với sai ngay từ đầu.

## 2. Điểm đã làm tốt
- Viết SQLite database wrapper gọn nhẹ và giao diện HTML mock UI.
- Tách các lời gọi HTTP đồng bộ (OpenRouter) ra `asyncio.to_thread()` để không treo heartbeat Discord gateway — dứt điểm lỗi mất tin nhắn khi model phản hồi chậm.
- Viết system prompt chống prompt-injection/thao túng, ép AI luôn đối chiếu `query_schedules` (kể cả trạng thái đã hủy) trước khi khẳng định 1 sự kiện còn hiệu lực, tránh trả lời tự tin nhưng sai.
