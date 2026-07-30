# PROTOTYPE CODEBASE

Tài liệu hướng dẫn cấu trúc Prototype cho Trợ lý AI Quản Lý & Sắp Xếp Lịch Trình từ Discord.

## 📌 Phân định thành phần Prototype

| Thư mục / Thành phần | Mức Prototype | Mô tả chi tiết |
|---|---|---|
| `codebase/mock_ui/` | **[Mock]** | Giao diện HTML/CSS/JS mô phỏng Discord Chat UI. Cho phép bấm tương tác và mô phỏng phản hồi từ AI Bot. |
| `codebase/src/` | **[Working]** | Mã nguồn thật chạy Python: <br/>- `db.py`: SQLite Ingestion & Schema lưu trữ thông báo từ Discord.<br/>- `scheduler_agent.py`: AI Agent Core thực hiện vòng lặp ReAct truy xuất DB & tối ưu thời khóa biểu. |

## 🚀 Hướng dẫn chạy thử nghiệm (Working Component)

```bash
cd codebase/src
python db.py              # Khởi tạo Database SQLite và nạp dữ liệu mẫu từ Discord
python scheduler_agent.py # Chạy thử ReAct Scheduler Agent với testcase mẫu
```
