# PROTOTYPE CODEBASE

Tài liệu hướng dẫn cấu trúc Prototype & tích hợp Discord thật cho Trợ lý AI Quản Lý & Sắp Xếp Lịch Trình.

## 📌 Phân định thành phần Prototype

| Thư mục / Thành phần | Mức Prototype | Mô tả chi tiết |
|---|---|---|
| `codebase/mock_ui/` | **[Mock]** | Giao diện HTML/CSS/JS mô phỏng Discord Chat UI độc lập. Cho phép bấm nút giả lập Giảng viên đăng/sửa bài real-time và mô phỏng phản hồi từ AI Bot. |
| `codebase/src/` | **[Working]** | Mã nguồn thật chạy Python: <br/>- `db.py`: SQLite Ingestion & Schema lưu trữ thông báo từ Discord.<br/>- `scheduler_agent.py`: AI Agent Engine thực hiện ReAct Loop đối soát & tối ưu thời khóa biểu.<br/>- `discord_bot.py`: Tích hợp Discord Bot thật lắng nghe sự kiện `on_message` & `on_message_edit`. |

---

## ⚙️ Hướng dẫn cấu hình Biến môi trường (.env)

Tạo file `.env` tại thư mục `codebase/.env` (hoặc copy từ `.env.example`) và điền các thông tin:

```env
# DISCORD BOT ENVIRONMENT CONFIGURATION
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
ANNOUNCEMENT_CHANNEL_IDS=123456789012345678,876543210987654321
```

---

## 🚀 Hướng dẫn chạy thử nghiệm (Working Components)

### 1. Chạy mô phỏng Agent & Database nội bộ:

```bash
cd codebase/src
python db.py              # Khởi tạo Database SQLite và nạp dữ liệu thông báo
python scheduler_agent.py # Chạy thử ReAct Scheduler Agent với query mẫu
```

### 2. Chạy Discord Bot kết nối Server Discord thật:

```bash
pip install -r requirements.txt
python codebase/src/discord_bot.py
```
