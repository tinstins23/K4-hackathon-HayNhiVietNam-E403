"""
db.py — Lớp lưu trữ SQLite cho Trợ lý AI Sắp Xếp Lịch Trình Discord.

Hai bảng:
  - messages:            tin nhắn thô từ Discord (nguồn sự thật để trích dẫn / jump-link)
  - official_schedules:  sự kiện lịch đã được Extraction Agent trích xuất có cấu trúc

Thiết kế bám theo spec.md §5 (4 lớp chỗ khó):
  - status='canceled' khi có thông báo hủy  (chỗ khó ①)
  - updated_at + source_msg_id LUÔN được ghi đè theo bản tin mới nhất (chỗ khó ④)
  - is_mandatory để agent ưu tiên lịch bắt buộc khi có xung đột (chỗ khó ④)

Vai trò người gửi (sender_role) dùng để:
  1. Quyết định tin nhắn có đáng tin để trích xuất thành lịch chính thức không
     (chỉ btc/instructor/coach/mentor mới được ingest vào official_schedules)
  2. Rank độ ưu tiên khi agent tổng hợp câu trả lời

ROLE_PRIORITY: số càng cao càng đáng tin khi có xung đột thông tin.
"""
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

# DB_PATH mặc định neo theo vị trí file db.py này, KHÔNG theo cwd — nếu để tương đối thì
# chạy từ thư mục khác sẽ lặng lẽ tạo một DB rỗng mới và AI trả "không tìm thấy lịch" cho
# mọi câu hỏi mà không báo lỗi gì. Muốn đổi chỗ lưu thì set biến môi trường DB_PATH.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_env_db_path = os.getenv("DB_PATH") or "schedules.db"
# Đường dẫn tương đối (kể cả khi lấy từ .env) luôn được neo về thư mục src/, không theo cwd.
# Chỉ đường dẫn tuyệt đối mới được tôn trọng nguyên vẹn.
DB_PATH = _env_db_path if os.path.isabs(_env_db_path) else os.path.join(_SRC_DIR, _env_db_path)

ROLE_PRIORITY = {
    "admin": 4,
    "btc": 4,
    "coach": 3,
    "instructor": 3,
    "mentor": 3,
    "student": 1,
}

# Kênh được coi là nguồn thông báo chính thức -> lọc trực tiếp theo ID trong .env
OFFICIAL_CHANNEL_IDS = {
    int(c.strip())
    for c in (os.getenv("ANNOUNCEMENT_CHANNEL_IDS") or os.getenv("WATCHED_CHANNEL_IDS") or "").split(",")
    if c.strip().isdigit()
}
OFFICIAL_CHANNELS = OFFICIAL_CHANNEL_IDS

# Vai tối thiểu để tin nhắn được coi là nguồn chính thức (Coach hoặc Admin).
MIN_OFFICIAL_ROLE = "coach"


def normalize_channel_name(name: str) -> str:
    """Chuẩn hoá tên kênh (bỏ dấu #, chuyển chữ thường, strip)."""
    if not name:
        return ""
    return name.strip().lstrip("#").lower()


def is_official_source(sender_role: str, channel_id: int = None, channel_name: str = None) -> bool:
    """Tin nhắn này có đáng tin để coi là NGUỒN SỰ THẬT về lịch không?
    Lọc bắt buộc theo Channel ID từ biến môi trường ANNOUNCEMENT_CHANNEL_IDS.
    """
    if OFFICIAL_CHANNEL_IDS and channel_id is not None:
        try:
            if int(channel_id) not in OFFICIAL_CHANNEL_IDS:
                return False
        except (ValueError, TypeError):
            pass

    return ROLE_PRIORITY.get(sender_role, 0) >= ROLE_PRIORITY[MIN_OFFICIAL_ROLE]


def _with_trust(row) -> dict:
    """Chuyển 1 row bảng messages thành dict + gắn sẵn nhãn tin cậy."""
    d = dict(row)
    d["is_official"] = is_official_source(d.get("sender_role"), d.get("channel"))
    return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Múi giờ Việt Nam (UTC+7, không có DST) ---
# discord.py trả `message.created_at` ở UTC -> ta LƯU nguyên UTC vào DB (đúng, không đổi),
# nhưng mọi chỗ TÍNH "hôm nay là ngày nào" hoặc HIỂN THỊ giờ cho người dùng/LLM đọc phải quy
# đổi sang giờ Việt Nam, nếu không "hôm nay" có thể lệch 1 ngày (khung UTC 17:00-23:59 =
# 00:00-06:59 giờ VN hôm sau) và giờ hiển thị trong trích dẫn sẽ lệch 7 tiếng so với thực tế
# người dùng đăng (vd. đăng lúc ~11h55 sáng VN nhưng AI đọc thấy "04:55 sáng" trong DB).
VN_TZ = timezone(timedelta(hours=7))


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def to_vn_display(iso_str: str) -> str:
    """Chuyển 1 chuỗi ISO timestamp (mặc định coi là UTC nếu không có tzinfo) sang giờ VN,
    dạng dễ đọc 'HH:MM DD/MM/YYYY' để đưa vào prompt LLM / hiển thị cho người dùng."""
    if not iso_str:
        return iso_str
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ).strftime("%H:%M %d/%m/%Y")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            msg_id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            sender TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_edited INTEGER DEFAULT 0,
            edited_at TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS official_schedules (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            is_mandatory INTEGER DEFAULT 1,
            category TEXT,
            host TEXT,
            location TEXT,
            status TEXT DEFAULT 'active',   -- active | canceled
            source_msg_id TEXT NOT NULL,
            source_channel TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (source_msg_id) REFERENCES messages(msg_id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS personal_busy_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_label TEXT NOT NULL,
            title TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_time ON official_schedules(start_time, end_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_channel ON messages(channel, created_at)")

        # Bảng khoá idempotency dùng CHUNG file DB (schedules.db) làm điểm điều phối giữa
        # NHIỀU tiến trình (vd. lỡ chạy 2 instance discord_bot.py, hoặc chạy backfill_discord.py
        # trong lúc bot live vẫn đang chạy). Khi 1 sự kiện Discord (msg_id) bị xử lý > 1 lần,
        # INSERT thứ 2 sẽ đụng PRIMARY KEY và thất bại -> try_claim() trả về False -> nơi gọi
        # biết là "đã có người xử lý rồi" và tự bỏ qua. Đây là gốc rễ sửa lỗi "trả lời 2 lần" /
        # "tạo trùng lịch": bug không nằm ở 1 hàm cụ thể mà ở việc ingest_message()/on_message
        # trước đây có thể bị gọi nhiều lần cho CÙNG 1 tin nhắn mà không hàm nào tự biết điều đó.
        conn.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_locks (
            lock_key TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """)


def clear_db():
    """Xoá sạch 100% dữ liệu trong DB về 0 (messages = 0, official_schedules = 0, personal_busy_slots = 0, idempotency_locks = 0)."""
    init_db()
    with get_conn() as conn:
        conn.execute("DELETE FROM official_schedules")
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM personal_busy_slots")
        conn.execute("DELETE FROM idempotency_locks")


def reset_db():
    """Xoá sạch toàn bộ dữ liệu trong DB về 0 (100% dữ liệu đến từ Discord)."""
    clear_db()



def try_claim(lock_key: str) -> bool:
    """Cố gắng 'giành quyền' xử lý 1 việc chỉ-làm-một-lần, định danh bởi `lock_key`.

    Trả về True nếu ĐÂY LÀ LẦN ĐẦU claim (nơi gọi được phép tiếp tục xử lý).
    Trả về False nếu key đã được claim trước đó (nơi gọi PHẢI bỏ qua, tránh làm trùng
    việc — vd. gọi LLM trích xuất lịch 2 lần, hoặc gửi 2 embed trả lời cho cùng 1 câu hỏi).

    An toàn khi nhiều tiến trình cùng dùng chung 1 file SQLite: INSERT vào PRIMARY KEY
    trùng sẽ ném IntegrityError, ta bắt lỗi đó và coi là "thua cuộc giành khoá".
    """
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO idempotency_locks (lock_key, created_at) VALUES (?, ?)",
                (lock_key, now_iso()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def normalize_msg_id(msg_id: str) -> str:
    """Chuẩn hoá msg_id: hỗ trợ cả dạng số Discord thô (1532621992203649024), có hoặc không có tiền tố 'msg_' hay dấu '#'."""
    if not msg_id:
        return ""
    cleaned = str(msg_id).strip().lstrip("#")
    if cleaned.startswith("msg_"):
        return cleaned
    if cleaned.isdigit():
        return f"msg_{cleaned}"
    return cleaned


def get_msg_id_candidates(msg_id: str) -> list:
    """Trả về danh sách các biến thể có thể có của msg_id (ví dụ: '1532621992203649024', 'msg_1532621992203649024', '#1532621992203649024')
    để đảm bảo truy vấn CSDL luôn khớp 100% dù dữ liệu trong DB đang lưu dưới dạng thô hay dạng chuẩn hoá."""
    if not msg_id:
        return []
    s = str(msg_id).strip().lstrip("#")
    candidates = [str(msg_id).strip(), s]
    if s.startswith("msg_"):
        pure = s[4:]
        if pure:
            candidates.append(pure)
    else:
        candidates.append(f"msg_{s}")
    
    seen = set()
    result = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def upsert_message(msg_id, channel, sender, sender_role, content, created_at=None, is_edited=False):
    created_at = created_at or now_iso()
    norm_id = normalize_msg_id(msg_id)
    cands = get_msg_id_candidates(msg_id)
    placeholders = ",".join(["?"] * len(cands))
    with get_conn() as conn:
        existing = conn.execute(f"SELECT msg_id FROM messages WHERE msg_id IN ({placeholders})", cands).fetchone()
        target_id = existing["msg_id"] if existing else norm_id
        if existing:
            conn.execute(
                """UPDATE messages SET content=?, is_edited=1, edited_at=? WHERE msg_id=?""",
                (content, now_iso(), target_id),
            )
        else:
            conn.execute(
                """INSERT INTO messages (msg_id, channel, sender, sender_role, content, created_at, is_edited, edited_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (target_id, channel, sender, sender_role, content, created_at, int(is_edited), None),
            )
    return get_message(target_id)


def get_message(msg_id):
    if not msg_id:
        return None
    cands = get_msg_id_candidates(msg_id)
    if not cands:
        return None
    placeholders = ",".join(["?"] * len(cands))
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT * FROM messages WHERE msg_id IN ({placeholders})",
            cands
        ).fetchone()
        return _with_trust(row) if row else None


def list_messages(channel: str, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE channel=? ORDER BY created_at ASC LIMIT ?",
            (channel, limit),
        ).fetchall()
        return [_with_trust(r) for r in rows]


def search_messages(keyword: str, channel: str = None, limit: int = 20,
                     sender_role: str = None, only_official: bool = None,
                     date_from: str = None, date_to: str = None):
    """Tìm tin nhắn thô theo từ khoá — gồm CẢ tin nhắn học viên, không chỉ thông báo. Hỗ trợ tra cứu theo ID tin nhắn.

    Mỗi kết quả có field `is_official`: True = nguồn chính thức đáng tin,
    False = tin nhắn học viên (chỉ là ngữ cảnh, KHÔNG phải sự thật về lịch).
    """
    cands = get_msg_id_candidates(keyword)
    tokens = [t for t in (keyword or "").split() if len(t) > 1] or [keyword or ""]
    
    cand_conds = " OR ".join(["msg_id = ?"] * len(cands))
    like_terms = " OR ".join(["(content LIKE ? OR msg_id LIKE ? OR msg_id = ?)"] * len(tokens))
    if cand_conds:
        like_terms = f"({like_terms}) OR ({cand_conds})"
    
    score = " + ".join(["(CASE WHEN content LIKE ? OR msg_id LIKE ? THEN 1 ELSE 0 END)"] * len(tokens))
    
    score_params = []
    where_params = []
    for t in tokens:
        score_params.extend([f"%{t}%", f"%{t}%"])
        where_params.extend([f"%{t}%", f"%{t}%", t])
    where_params.extend(cands)
    
    q = f"SELECT *, ({score}) AS _score FROM messages WHERE ({like_terms})"
    params = score_params + where_params

    if channel:
        q += " AND channel=?"
        params.append(channel)
    if sender_role:
        q += " AND sender_role=?"
        params.append(sender_role)
    if date_from:
        q += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        q += " AND created_at <= ?"
        params.append(date_to)
    q += " ORDER BY _score DESC, created_at DESC LIMIT ?"
    params.append(limit if only_official is None else limit * 5)

    with get_conn() as conn:
        rows = [_with_trust(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        r.pop("_score", None)
    if only_official is not None:
        rows = [r for r in rows if r["is_official"] is bool(only_official)]
    return rows[:limit]


def next_schedule_id():
    """Sinh ID mới dựa trên SỐ LỚN NHẤT đang có trong `id` (SCH_014 -> SCH_015), KHÔNG dùng
    COUNT(*) như trước đây. COUNT(*) từng gây lỗi 'UNIQUE constraint failed: official_schedules.id':
    hễ có dòng nào bị xoá (vd. dọn lịch trùng do bug) thì count tụt xuống, sinh lại đúng 1 ID đã
    tồn tại -> insert tiếp theo văng lỗi. Đếm theo MAX thì có xoá bao nhiêu dòng giữa chừng cũng
    không bao giờ sinh trùng ID cũ."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM official_schedules").fetchall()
    max_n = 0
    for r in rows:
        try:
            max_n = max(max_n, int(str(r["id"]).rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return f"SCH_{max_n + 1:03d}"


def create_schedule(title, start_time, end_time, is_mandatory, category, host, location,
                     source_msg_id, source_channel, status="active"):
    ts = now_iso()
    last_err = None
    for _ in range(5):
        sched_id = next_schedule_id()
        try:
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO official_schedules
                       (id, title, start_time, end_time, is_mandatory, category, host, location,
                        status, source_msg_id, source_channel, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sched_id, title, start_time, end_time, int(is_mandatory), category, host, location,
                     status, source_msg_id, source_channel, ts, ts),
                )
            return get_schedule(sched_id)
        except sqlite3.IntegrityError as e:
            last_err = e
            continue
    raise RuntimeError(f"Không thể sinh ID lịch mới sau nhiều lần thử: {last_err}")


def update_schedule(sched_id, source_msg_id, source_channel, **fields):
    allowed = {"title", "start_time", "end_time", "is_mandatory", "category", "host", "location", "status"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?")
            params.append(v)
    sets += ["source_msg_id=?", "source_channel=?", "updated_at=?"]
    params += [normalize_msg_id(source_msg_id), source_channel, now_iso()]
    params.append(sched_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE official_schedules SET {', '.join(sets)} WHERE id=?", params)
    return get_schedule(sched_id)


def cancel_schedule(sched_id, source_msg_id, source_channel):
    return update_schedule(sched_id, source_msg_id, source_channel, status="canceled")


def cancel_schedules_by_source_msg_id(source_msg_id: str) -> list:
    """Khi tin nhắn thông báo bị xóa trên Discord -> Tự động chuyển tất cả lịch trích xuất từ tin nhắn đó sang status='canceled'."""
    cands = get_msg_id_candidates(source_msg_id)
    if not cands:
        return []
    placeholders = ",".join(["?"] * len(cands))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id FROM official_schedules WHERE source_msg_id IN ({placeholders}) AND status='active'",
            cands
        ).fetchall()
        canceled_ids = []
        for r in rows:
            conn.execute(
                "UPDATE official_schedules SET status='canceled', updated_at=? WHERE id=?",
                (now_iso(), r["id"])
            )
            canceled_ids.append(r["id"])
        return canceled_ids


def delete_message(msg_id: str) -> dict:
    """Xóa tin nhắn thô khỏi bảng messages và chuyển các lịch liên quan sang status='canceled'."""
    cands = get_msg_id_candidates(msg_id)
    if not cands:
        return {"deleted_count": 0, "canceled_schedules": []}
    placeholders = ",".join(["?"] * len(cands))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id FROM official_schedules WHERE source_msg_id IN ({placeholders}) AND status='active'",
            cands
        ).fetchall()
        canceled_ids = [r["id"] for r in rows]

        conn.execute(
            f"UPDATE official_schedules SET status='canceled', updated_at=? WHERE source_msg_id IN ({placeholders})",
            [now_iso()] + cands
        )

        conn.execute("PRAGMA foreign_keys = OFF")
        cursor = conn.execute(f"DELETE FROM messages WHERE msg_id IN ({placeholders})", cands)
        deleted_count = cursor.rowcount
        conn.execute("PRAGMA foreign_keys = ON")

        return {"deleted_count": deleted_count, "canceled_schedules": canceled_ids}


def get_schedule(sched_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM official_schedules WHERE id=?", (sched_id,)).fetchone()
        return dict(row) if row else None


def list_active_schedules_for_matching(limit=30):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, title, start_time, end_time, category, host, status
               FROM official_schedules WHERE status='active'
               ORDER BY start_time DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def query_schedules(date_from=None, date_to=None, category=None, status="active", mandatory_only=None):
    q = "SELECT * FROM official_schedules WHERE 1=1"
    params = []
    if status:
        q += " AND status=?"
        params.append(status)
    if date_from:
        # end_time CÓ THỂ NULL (deadline chỉ có mốc bắt đầu). Trong SQLite `NULL >= x` ra
        # NULL -> bị coi là false -> sự kiện đó biến mất khỏi MỌI query có date_from mà
        # không báo lỗi. Đây từng làm "Hạn nộp Đồ án Capstone" không bao giờ tra được.
        # Không có end_time thì lấy start_time làm mốc so sánh.
        q += " AND COALESCE(end_time, start_time) >= ?"
        params.append(date_from)
    if date_to:
        q += " AND start_time <= ?"
        params.append(date_to)
    if category:
        q += " AND category=?"
        params.append(category)
    if mandatory_only is not None:
        q += " AND is_mandatory=?"
        params.append(int(mandatory_only))
    q += " ORDER BY start_time ASC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def add_busy_slot(user_label, title, start_time, end_time):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO personal_busy_slots (user_label, title, start_time, end_time, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_label, title, start_time, end_time, now_iso()),
        )


def list_busy_slots(user_label, date_from=None, date_to=None):
    q = "SELECT * FROM personal_busy_slots WHERE user_label=?"
    params = [user_label]
    if date_from:
        q += " AND end_time >= ?"
        params.append(date_from)
    if date_to:
        q += " AND start_time <= ?"
        params.append(date_to)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_PATH}")
