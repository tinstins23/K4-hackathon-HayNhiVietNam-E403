# 🤖 TRỢ LÝ AI SẮP XẾP LỊCH TRÌNH DISCORD (SCHEDULE AI ASSISTANT)

> **Dự án Hackathon Batch 03 — Nhóm HayNhiVietNam (Zone 4)**  
> Hệ thống Trợ lý AI tự động trích xuất, quản lý và sắp xếp lịch trình cá nhân hóa cho học viên trên Discord.  
> Được xây dựng trên kiến trúc **ReAct LLM Engine + SQLite Storage Layer + Real-time Discord Bot + FastAPI REST API + Mock UI Prototype**.

---

## 📋 MỤC LỤC
1. [Cấu Trúc Mã Nguồn & Thư Mục](#-1-cấu-trúc-mã-nguồn--thư-mục)
2. [Yêu Cầu Tiền Trạm & Môi Trường](#-2-yêu-cầu-tiền-trạm--môi-trường)
3. [Cài Đặt & Cấu Hình (.env)](#-3-cài-đặt--cấu-hình-env)
4. [Hướng Dẫn Khởi Chạy Chi Tiết](#-4-hướng-dẫn-khởi-chạy-chi-tiết)
   - [Bước 1: Nạp & Đồng Bộ Lịch Sử Discord (Backfill Data)](#bước-1-nạp--đồng-bộ-lịch-sử-discord-backfill-data)
   - [Bước 2: Chạy Real-time Discord Bot (Start Bot)](#bước-2-chạy-real-time-discord-bot-start-bot)
   - [Bước 3: Chạy FastAPI REST API Server](#bước-3-chạy-fastapi-rest-api-server)
   - [Bước 4: Chạy Thử Nghiệm CLI Agent](#bước-4-chạy-thử-nghiệm-cli-agent)
   - [Bước 5: Xem Giao Diện Demo (Mock UI)](#bước-5-xem-giao-diện-demo-mock-ui)
5. [Chạy Bộ Kiểm Thử Đánh Giá (Evaluation Suite)](#-5-chạy-bộ-kiểm-thử-đánh-giá-evaluation-suite)
6. [Quy Định Phân Quyền & Chống Hallucination](#-6-quy-định-phân-quyền--chống-hallucination)

---

## 📌 1. Cấu Trúc Mã Nguồn & Thư Mục

Cấu trúc thư mục chi tiết tại `repo/codebase/`:

```
repo/codebase/
├── .env.example              # Mẫu khai báo biến môi trường
├── requirements.txt          # Danh sách thư viện Python cần thiết
├── README.md                 # Hướng dẫn chạy source và start bot (File này)
├── mock_ui/                  # Prototype Giao diện Discord
│   └── index.html            # Web UI mô phỏng kênh chat Discord (HTML/CSS/JS)
└── src/                      # Source code chính của ứng dụng Backend & Bot
    ├── main.py               # REST API Server (FastAPI)
    ├── discord_bot.py        # Bot Discord Real-time (discord.py)
    ├── agent.py              # Core suy luận ReAct Loop qua OpenRouter LLM
    ├── ingestion.py          # Extraction Pipeline trích xuất lịch từ thông báo
    ├── db.py                 # SQLite Storage Layer & phân quyền nguồn tin
    ├── backfill_discord.py   # Tool đồng bộ tin nhắn lịch sử từ Discord về DB
    ├── tools.py              # Các hàm Database Tools cho Agent gọi (SQL Query/Busy Slot)
    ├── systemprompt.py       # Prompt hệ thống quy định luật trích dẫn & chống bịa đặt
    ├── openrouter_client.py  # Client kết nối API OpenRouter LLM
    └── scheduler_agent.py    # CLI script chạy thử nghiệm Agent nhanh trên Terminal
```

### Chi tiết các file xử lý chính (`src/`):

| File | Vai Trò | Mô Tả Chi Tiết |
|---|---|---|
| `discord_bot.py` | **[Real-time Bot]** | Lắng nghe tin nhắn Discord real-time. Tự động nạp thông báo từ `Coach`/`Admin` vào DB và trả lời học viên khi được `@mention` hoặc trong kênh `#tro-ly-lich-trinh`. |
| `main.py` | **[REST API Backend]** | FastAPI Server cung cấp REST endpoints (`/chat`, `/ingest`, `/messages`, `/schedules`). |
| `agent.py` | **[ReAct Engine]** | Vòng suy luận ReAct (Reasoning + Acting) sử dụng OpenRouter API. Tự động gọi Tools (`query_schedules`, `search_messages`, `list_busy_slots_from_db`, `add_personal_busy_slot`) để trả lời kèm trích dẫn `msg_id`. |
| `db.py` | **[SQLite Storage]** | Quản lý CSDL SQLite (`schedules.db`). Xử lý lọc Channel ID, xác thực phân quyền `admin`/`coach`/`student`, và quản lý lịch cá nhân/chính thức. |
| `backfill_discord.py` | **[Data Backfill]** | Đồng bộ toàn bộ tin nhắn raw lịch sử từ các kênh Discord được chỉ định vào SQLite DB local mà không tiêu tốn lượt gọi AI. |
| `ingestion.py` | **[Extraction Pipeline]** | Extraction Agent phân tích bài đăng chính thức của BTC/Coach để trích xuất lịch có cấu trúc (bản ghi sự kiện, deadline, thời gian). |
| `systemprompt.py` | **[System Prompt]** | Định nghĩa luật ứng xử của AI: Chống bịa đặt (No Hallucination), phân định nguồn chính thức vs. kênh thảo luận, xử lý thời gian mơ hồ. |

---

## ⚙️ 2. Yêu Cầu Tiền Trạm & Môi Trường

- **Python**: Version `3.10` trở lên (Khuyến nghị Python `3.11`).
- **Discord Bot Token**: Token tạo từ [Discord Developer Portal](https://discord.com/developers/applications).
- **OpenRouter API Key**: API key cấp tại [OpenRouter.ai](https://openrouter.ai/keys) (Hỗ trợ các model miễn phí như Gemini 2.0 Flash / Qwen 2.5 / Llama 3.1).

---

## 🛠️ 3. Cài Đặt & Cấu Hình (.env)

### 3.1. Cài Đặt Thư Viện Dependencies

Mở Terminal tại thư mục gốc của dự án (`d:\K4-hackathon-HayNhiVietNam-E403`) và khởi tạo Virtual Environment:

```bash
# 1. Tạo môi trường ảo Python
python -m venv venv

# 2. Kích hoạt môi trường ảo
# Trên Windows (PowerShell / CMD):
.\venv\Scripts\activate
# Trên Linux / macOS:
source venv/bin/activate

# 3. Cài đặt các thư viện phụ thuộc
pip install -r repo/codebase/requirements.txt
```

### 3.2. Cấu Hình File Môi Trường `.env`

Tạo file `.env` tại thư mục `repo/codebase/src/.env` (hoặc ngay thư mục root `repo/codebase/.env`):

```env
# 1. DISCORD BOT TOKEN (Lấy từ Discord Developer Portal -> Bot -> Reset Token)
DISCORD_BOT_TOKEN=your-discord-bot-token-here

# 2. OPENROUTER API KEY (Lấy miễn phí tại https://openrouter.ai/keys)
OPENROUTER_API_KEY=sk-or-v1-your-openrouter-key-here

# 3. MODEL LLM (Sử dụng các model FREE active trên OpenRouter)
AGENT_MODEL=google/gemini-2.0-flash-exp:free
EXTRACTION_MODEL=google/gemini-2.0-flash-exp:free

# 4. KÊNH LƯU TIN NHẮN VÀO DB (Khai báo mã Snowflake ID từ Discord, phân cách bằng dấu phẩy)
#    Để TRỐNG = lưu tất cả các kênh Bot nhìn thấy
WATCHED_CHANNEL_IDS=

# 5. KÊNH THÔNG BÁO CHÍNH THỨC (Chỉ những kênh này mới được trích xuất thành lịch chính thức)
#    Để TRỐNG = lọc theo vai trò người gửi (Coach / Admin)
ANNOUNCEMENT_CHANNEL_IDS=

# 6. Ngưỡng lọc tin nhắn ngắn / nhiễu ("ok", "vâng", emoji...)
MIN_CONTENT_LENGTH=10
```

> 💡 **Mẹo lấy Channel ID (Snowflake ID) trên Discord**:
> Bật **Developer Mode** trong Discord (`User Settings` -> `Advanced` -> `Developer Mode`). Sau đó click chuột phải vào kênh bất kỳ -> Chọn **Copy Channel ID**.

---

## 🚀 4. Hướng Dẫn Khởi Chạy Chi Tiết

> **Lưu ý về đường dẫn**: Bạn có thể chạy trực tiếp tất cả lệnh bên dưới từ **thư mục gốc dự án** (`d:\K4-hackathon-HayNhiVietNam-E403`), hoặc di chuyển vào `repo/codebase/src`.

---

### Bước 1: Nạp & Đồng Bộ Lịch Sử Discord (Backfill Data)

Trước khi khởi chạy Bot lần đầu, cần kéo tin nhắn lịch sử từ các kênh Discord chính thức về CSDL SQLite local để Agent có dữ liệu tra cứu:

#### A. Đồng bộ tin nhắn lịch sử (Không tốn chi phí AI):
```bash
python repo/codebase/src/backfill_discord.py --limit 500
```

#### B. Xem thống kê dữ liệu hiện có trong DB local:
```bash
python repo/codebase/src/backfill_discord.py --stats
```

#### C. Xóa sạch dữ liệu DB về 0 (khi cần Reset CSDL):
```bash
python repo/codebase/src/backfill_discord.py --clear-only
```

---

### Bước 2: Chạy Real-time Discord Bot (Start Bot)

Khởi chạy Bot Discord trực tiếp để lắng nghe tin nhắn mới và tương tác với học viên:

```bash
python repo/codebase/src/discord_bot.py
```

Khi Terminal hiển thị log thành công:
```text
✅ Bot AI đã sẵn sàng hoạt động trên Discord dưới tên: <Tên_Bot>
🤖 Đang kết nối ReAct LLM Agent qua OpenRouter model: google/gemini-2.0-flash-exp:free
```

**Cách tương tác với Bot trên Discord**:
1. Chat trực tiếp trong kênh `#tro-ly-lich-trinh`.
2. `@Mention` tên Bot ở bất kỳ kênh nào mà Bot có quyền truy cập.
3. Ví dụ câu hỏi:
   - `Hôm nay mình có lịch học gì không bot?`
   - `Khi nào đến deadline nộp bài Hackathon?`
   - `Tuần sau có buổi Mentor nào rảnh lúc 14h không?`

---

### Bước 3: Chạy FastAPI REST API Server

Nếu bạn cần sử dụng REST API backend cho Web App / Dashboard hoặc tích hợp hệ thống ngoài:

```bash
uvicorn repo.codebase.src.main:app --reload --port 8000
```

Sau khi server khởi chạy:
- **API Base URL**: `http://localhost:8000`
- **Tài liệu Swagger UI**: `http://localhost:8000/docs`

**Các API Endpoints chính**:
- `POST /chat`: Gửi câu hỏi của học viên tới ReAct Agent để nhận phản hồi kèm trích dẫn nguồn.
- `POST /ingest`: Nạp 1 tin nhắn mới vào CSDL.
- `GET /schedules`: Truy vấn danh sách lịch trình chính thức đã trích xuất.
- `GET /messages/{channel}`: Lấy lịch sử tin nhắn theo kênh.
- `GET /messages/search`: Tìm kiếm tin nhắn theo từ khóa, lọc chính thức / học viên.
- `GET /health`: Kiểm tra trạng thái hoạt động của API Server.

---

### Bước 4: Chạy Thử Nghiệm CLI Agent

Dành cho Developers muốn test nhanh khả năng phản hồi của ReAct Agent từ dòng lệnh Terminal mà không cần bật Discord:

```bash
python repo/codebase/src/scheduler_agent.py
```

---

### Bước 5: Xem Giao Diện Demo (Mock UI)

Dự án cung cấp một giao diện Discord Mockup bằng HTML/CSS/JS phục vụ việc minh họa & demo trải nghiệm người dùng:

- Mở trực tiếp file `repo/codebase/mock_ui/index.html` bằng trình duyệt web bất kỳ (Chrome, Edge, Firefox).
- Hoặc sử dụng extension **Live Server** trong VS Code để mở.

---

## 🧪 5. Chạy Bộ Kiểm Thử Đánh Giá (Evaluation Suite)

Hệ thống đi kèm bộ testcases đánh giá tự động (Golden Set 26 kịch bản) theo đầy đủ tiêu chuẩn chất lượng:

Chạy script đánh giá:
```bash
python repo/eval/eval_runner.py
```

Kết quả báo cáo đánh giá chi tiết sẽ được tự động xuất ra file:
`repo/eval/eval_results.md`

---

## 🛡️ 6. Quy Định Phân Quyền & Chống Hallucination

1. **Phân Quyền Vai Trò (Roles)**:
   - `Admin` / `Ban Tổ Chức`: Quyền cao nhất, mọi thông báo lịch trình đều là nguồn sự thật.
   - `Coach` / `Giảng Viên` / `Mentor`: Quyền đăng tải lịch trình chính thức.
   - `Student` / `Học Viên`: Tin nhắn thảo luận chỉ mang tính chất tham khảo ngữ cảnh, **KHÔNG** được tự động trích xuất thành lịch chính thức.

2. **Chống Bịa Đặt (No Hallucination & Source Citation)**:
   - Mọi câu trả lời liên quan tới lịch trình đều bắt buộc phải kèm mã trích dẫn tin nhắn gốc (`#msg_id`).
   - Nếu dữ liệu không tồn tại trong CSDL, Agent sẽ báo chưa có thông tin chính thức thay vì tự suy đoán.
