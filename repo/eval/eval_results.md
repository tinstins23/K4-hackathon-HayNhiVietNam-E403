# BẢNG KẾT QUẢ KIỂM THỬ EVALUATION (EVAL RESULTS)

> **Bộ test**: `eval/golden_set.json` (20 testcases)  
> **Quality Bar**: ≥90% pass rate, 100% trích dẫn đúng `source_msg_id` Discord cho câu hỏi về lịch.

## Kết quả lượt chạy (Evaluation History)

| Lượt chạy | Thời điểm | Số case Pass / Tổng | Tỷ lệ Pass (%) | Trích dẫn Source (%) | Ghi chú & Cải tiến |
|---|---|---|---|---|---|
| **Run 1** | 2026-07-30 14:00 | 16 / 20 | 80% | 85% | Bị lỗi phân loại câu hỏi mơ hồ |
| **Run 2** | 2026-07-30 16:30 | 19 / 20 | 95% | 100% | Đã bổ sung ReAct agent prompt & Few-shot tool schemas |
