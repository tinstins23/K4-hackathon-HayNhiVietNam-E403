# Kế hoạch: Lưu tin nhắn người dùng Discord vào DB để AI retrieve

> Mục tiêu: mọi tin nhắn thật trong Discord (kể cả **học viên**, không chỉ thông báo từ
> BTC/Giảng viên) được ghi vào bảng `messages`, và ReAct Agent tra cứu được chúng.
> Bỏ demo `mock_ui` — đường đi duy nhất là Discord bot thật.

---

## 1. Hiện trạng: chỗ nào đang chặn

Có **đúng 2 chỗ chặn**, và tin tốt là phần lưu DB gần như đã sẵn sàng.

### Chặn 1 — Bot không bao giờ gọi ingest cho học viên

`src/discord_bot.py:59`

```python
if is_announcement and not message.author.bot and sender_role != "student":
                                                  ^^^^^^^^^^^^^^^^^^^^^^^^ chặn ở đây
    ingestion.ingest_message(...)
```

Tin nhắn học viên bị loại ngay tại bot, nên **không đi tới `ingest_message()` → không được lưu dòng nào**.

### Chặn 2 — Tool `search_messages` khoá cứng 2 kênh chính thức

`src/agent.py:79`

```python
"channel": {"type": "string", "enum": ["thong-bao-chung", "lich-hoc-moi"]},
```

Model không được phép hỏi các kênh khác. Mô tả tool cũng nói *"Tìm tin nhắn **thông báo** gốc"*
nên model không biết là có tin nhắn học viên tồn tại.

### Điều đã đúng sẵn — không cần sửa

`src/ingestion.py:77-82` lưu raw **trước** khi kiểm tra quyền:

```python
msg = upsert_message(...)              # dòng 77 — LUÔN chạy, mọi role, mọi kênh
result = {"message": msg, "extraction": None}
if not _should_ingest(sender_role, channel):   # dòng 81 — chỉ gác phần gọi LLM
    return result                              # dòng 82 — student thoát ở đây, KHÔNG tốn tiền API
```

Nghĩa là: **bỏ điều kiện `sender_role != "student"` ở bot là tin nhắn học viên tự động được lưu**,
mà không phát sinh lời gọi LLM nào. Kiến trúc phân tách sự thật (`official_schedules`) và
dữ liệu thô (`messages`) đã đúng từ đầu.

---

## 2. Luồng GHI (ingest) — sau khi sửa

```
   Discord: bất kỳ ai gõ tin nhắn ở kênh bot theo dõi
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ discord_bot.py :: on_message()                                │
│   • suy ra sender_role từ tên/role Discord (role_mapping)      │
│   • gọi: ingestion.ingest_message(msg_id, channel, sender,     │
│                                   sender_role, content, ...)   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ ingestion.py :: ingest_message()                              │
│                                                                │
│  ① db.upsert_message()  ────────────────►  bảng `messages`     │
│     LUÔN chạy — mọi role, mọi kênh        ★ TIN NHẮN USER      │
│                                              ĐƯỢC LƯU Ở ĐÂY    │
│                                                                │
│  ② _should_ingest(sender_role, channel)?                       │
│     ├── False → return  (student, hoặc kênh không chính thức)   │
│     │            KHÔNG gọi LLM, 0 chi phí                      │
│     └── True  → tiếp bước ③                                    │
│                  (btc/instructor/coach/mentor                  │
│                   + kênh thong-bao-chung | lich-hoc-moi)       │
│                                                                │
│  ③ openrouter_client.chat_completion()  ← Extraction Agent LLM │
│     → db.create_schedule() / update_schedule() / cancel_schedule│
│                          └───────────►  bảng `official_schedules`│
└───────────────────────────────────────────────────────────────┘
```

**Hai bảng, hai mức tin cậy — đây là điểm thiết kế cốt lõi:**

| Bảng | Nội dung | Ai ghi được | Mức tin cậy |
|---|---|---|---|
| `official_schedules` | lịch có cấu trúc | chỉ BTC/GV/Coach/Mentor ở kênh chính thức | **SỰ THẬT** — dùng để trả lời |
| `messages` | tin nhắn thô mọi người | **tất cả**, kể cả học viên | **NGỮ CẢNH** — không phải sự thật |

Giữ đúng chỗ khó ① trong `spec.md §5`: học viên đoán sai deadline trong chat không được
biến thành câu trả lời của AI.

---

## 3. Luồng ĐỌC (retrieve) — sau khi sửa

```
   Học viên hỏi trong #tro-ly-lich-trinh (hoặc @mention bot)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ discord_bot.py :: on_message()  (nhánh 2, dòng 76)            │
│   gọi: react_agent.ask(user_query, reference_date, user_label) │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ agent.py :: ask()   — vòng ReAct, tối đa MAX_TURNS = 6        │
│   openrouter_client.chat_completion(messages, tools=TOOLS)     │
│                                                                │
│   Model tự chọn tool:                                          │
│   ├─ query_schedules  → db.query_schedules()                   │
│   │                     → official_schedules   [SỰ THẬT]       │
│   ├─ search_messages  → db.search_messages()                   │
│   │                     → messages             [NGỮ CẢNH] ◄ SỬA│
│   └─ get_message      → db.get_message()                       │
│                         → messages                             │
│                                                                │
│   Sau mỗi tool: _collect_citations() gom msg_id      ◄─── SỬA  │
│   (cần tách 2 rổ: nguồn chính thức / tin nhắn học viên)        │
└───────────────────────────────────────────────────────────────┘
        │  { reply, citations, tool_trace }
        ▼
┌───────────────────────────────────────────────────────────────┐
│ discord_bot.py → discord.Embed(...)                            │
│   field "🔗 Trích dẫn nguồn sự thật"           ◄─── SỬA nhãn   │
└───────────────────────────────────────────────────────────────┘
```

### Vấn đề trust phải xử lý cùng lúc

`agent.py:115-126` `_collect_citations()` gom **mọi** `msg_id` từ kết quả tool vào một rổ
`citations`, rồi `discord_bot.py:104` in ra dưới nhãn **"🔗 Trích dẫn nguồn sự thật"**.

Sau khi mở `search_messages` cho tin nhắn học viên, một câu đoán sai của bạn cùng lớp sẽ được
Discord embed dán nhãn "nguồn sự thật". **Phải tách 2 rổ trước khi bật retrieval**, nếu không
đây thành lỗi ① nặng hơn cả trước khi làm.

---

## 4. Việc cần làm — theo thứ tự

### Bước 1 — Bot lưu mọi tin nhắn `src/discord_bot.py`

Tách `on_message` thành 2 việc độc lập (hiện đang bị gộp):

- **Việc A (mới): lưu raw.** Gọi `ingestion.ingest_message(...)` cho **mọi** tin nhắn người
  thật, ở mọi kênh được theo dõi. Bỏ `and sender_role != "student"` ở dòng 59.
- **Việc B (có sẵn): trích xuất lịch.** Không cần điều kiện ở bot nữa —
  `_should_ingest()` trong `ingestion.py:71` đã gác đúng (role ≥ mentor **và** kênh chính thức).

Đồng thời tách biến môi trường, vì hiện `ANNOUNCEMENT_CHANNEL_IDS` đang gánh 2 nghĩa:

```
WATCHED_CHANNEL_IDS=...        # kênh cần LƯU tin nhắn (rộng — gồm kênh học viên chat)
ANNOUNCEMENT_CHANNEL_IDS=...   # kênh thông báo chính thức (hẹp — để trích xuất lịch)
```

Sửa luôn `on_message_edit` (dòng 130) đang hardcode `sender_role="instructor"` — dùng chung
hàm suy role với `on_message` thay vì đoán.

### Bước 2 — `db.search_messages()` hỗ trợ lọc & gắn nhãn tin cậy `src/db.py:136`

- Thêm tham số `sender_role` (lọc theo vai) và `only_official` (chỉ kênh chính thức).
- Mỗi dòng trả về thêm field tính sẵn `is_official` = `channel in OFFICIAL_CHANNELS and
  ROLE_PRIORITY[sender_role] >= ROLE_PRIORITY["mentor"]`. Cả `agent.py` và Discord embed dùng
  field này để phân biệt, không tự suy lại logic ở 2 chỗ.
- Thêm `limit` mặc định cao hơn 10 và tham số `date_from`/`date_to` — tin nhắn học viên sẽ
  đông hơn thông báo rất nhiều.

### Bước 3 — Mở tool cho agent `src/agent.py`

- Dòng 79: bỏ `enum` cứng của `channel` → để string tự do (hoặc sinh enum từ
  `db.WATCHED_CHANNELS`), tránh sửa code mỗi lần thêm kênh.
- Thêm 2 tham số vào schema tool `search_messages`: `only_official` (bool) và `sender_role`.
- Sửa **mô tả tool**: nói rõ có 2 loại tin nhắn — thông báo chính thức (tin được) và tin nhắn
  học viên (chỉ là ngữ cảnh, không phải sự thật).
- Sửa `SYSTEM_PROMPT` nguyên tắc 1 (dòng 32): thông tin lịch **chỉ** lấy từ `query_schedules`
  hoặc tin nhắn `is_official=true`; nếu chỉ tìm thấy trong tin nhắn học viên thì phải nói rõ
  *"thông tin này do học viên khác nhắc, mình chưa thấy thông báo chính thức"*.
- `_collect_citations()` (dòng 115): trả **2 rổ** — `citations` (official) và
  `references` (unofficial).

### Bước 4 — Embed phân biệt 2 nguồn `src/discord_bot.py:100-104`

- Field `🔗 Trích dẫn nguồn sự thật` → chỉ `citations`.
- Thêm field `💬 Tin nhắn liên quan (chưa xác thực)` → `references`.

### Bước 5 — Backfill lịch sử Discord `src/backfill_discord.py` (file mới)

`on_message` chỉ thấy tin nhắn **mới từ lúc bot chạy**. Muốn AI retrieve được ngay thì phải
nạp lịch sử: script dùng `channel.history(limit=N)` của discord.py, gọi
`ingestion.ingest_message()` cho từng tin nhắn cũ.

Lưu ý khi viết: `_should_ingest` sẽ kích hoạt LLM cho **mọi** thông báo cũ của GV/BTC → tốn
API và có thể tạo lịch trùng/lịch quá khứ. Nên có cờ `--no-extract` để lần backfill đầu chỉ
lưu raw, extraction chạy riêng sau khi đã xem qua dữ liệu.

### Bước 6 — Endpoint tra cứu để test không cần Discord `src/main.py`

Thêm `GET /messages/search?keyword=&channel=&only_official=` gọi `db.search_messages()`.
Dùng để kiểm tra dữ liệu đã vào đúng chưa mà không phải mở Discord — cũng là cách viết
testcase cho `eval/`.

---

## 5. Bảng tóm tắt: file nào gọi file nào

| File | Gọi tới | Việc phải sửa |
|---|---|---|
| `src/discord_bot.py` | `ingestion.ingest_message()`, `agent.ask()`, `db.init_db()` | Bước 1, 4 |
| `src/ingestion.py` | `db.upsert_message()`, `db.create/update/cancel_schedule()`, `openrouter_client.chat_completion()` | **không sửa** |
| `src/agent.py` | `db.query_schedules/search_messages/get_message()`, `openrouter_client.chat_completion()` | Bước 3 |
| `src/db.py` | `sqlite3` | Bước 2 |
| `src/openrouter_client.py` | `httpx` → OpenRouter API | không sửa |
| `src/main.py` | `db`, `ingestion`, `agent` | Bước 6 |
| `src/backfill_discord.py` | `discord.py`, `ingestion.ingest_message()` | **tạo mới** (Bước 5) |
| `src/scheduler_agent.py` | `db.query_schedules()` | **stub không có AI — nên xoá**, xem §7 |

---

## 6. Cần bạn chốt trước khi tôi code

1. **Lưu tin nhắn ở những kênh nào?** Tất cả kênh bot thấy, hay whitelist? (ảnh hưởng khối
   lượng dữ liệu và độ ồn khi AI search)
2. **Có lưu chat của học viên với bot trong `#tro-ly-lich-trinh` không?** Nếu có thì AI nhớ
   được hội thoại nhiều lượt — hiện `history` không được truyền nên mỗi câu hỏi độc lập.
3. **AI được trích dẫn tin nhắn học viên ra ngoài không**, hay chỉ dùng làm ngữ cảnh nội bộ
   (không hiện trong embed)?
4. **Backfill bao nhiêu tin nhắn** mỗi kênh? (100 / 1000 / toàn bộ)

---

## 7. Rủi ro cần biết trước

- **`schedules.db` đang bị git track** (ở root repo, `.gitignore` chỉ có `.DS_Store`,
  `node_modules/`, `*.env`). Khi bắt đầu nạp tin nhắn Discord thật của học viên thật, mỗi
  commit sẽ đẩy tin nhắn người thật lên GitHub. `README.md` gốc §"Bảo mật dữ liệu" yêu cầu
  không commit dữ liệu thật vào repo nộp bài. **Nên thêm `*.db` vào `.gitignore` trước Bước 1**,
  hoặc ẩn danh `sender` khi lưu.
- **`DB_PATH=schedules.db` là đường dẫn tương đối.** DB đã seed nằm ở root repo, nhưng code ở
  `repo/codebase/src/`. Chạy từ `src/` sẽ tạo DB rỗng mới và AI trả "không tìm thấy lịch" cho
  mọi câu hỏi mà **không báo lỗi gì**. Nên đổi `DB_PATH` thành đường dẫn tuyệt đối tính từ
  vị trí `db.py`.
- **DB ở root hiện có 0 messages / 3 official_schedules** (3 event hardcode từ `db.py` stub cũ
  của Tín). Bản seed 12 messages + 10 schedules nằm trong git history tại
  `b9b55d2:codebase/src/schedules.db` — lấy lại được nếu cần.
- **`search_messages` dùng `content LIKE '%keyword%'`** — SQLite không dùng được index cho
  dạng này. Vài nghìn tin nhắn vẫn chạy tốt; nếu backfill toàn bộ lịch sử khoá thì cân nhắc
  bảng FTS5.
- **Tin nhắn học viên rất ồn** (chào hỏi, emoji, "ok bạn"). `search_messages` trả top-N theo
  `created_at DESC` chứ không theo độ liên quan → AI dễ nhận rác. Cân nhắc lọc độ dài tối
  thiểu hoặc bỏ tin nhắn chỉ có emoji/reaction ngay ở Bước 1.
- **Suy `sender_role` từ tên hiển thị Discord** (`discord_bot.py:44-54`) rất dễ sai — học
  viên tự đổi nickname thành "Coach ABC" là được nâng quyền ghi vào `official_schedules`.
  Nên ưu tiên đọc `message.author.roles` (role thật của server) và chỉ fallback sang tên.
