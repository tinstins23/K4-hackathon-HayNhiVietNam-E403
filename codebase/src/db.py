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
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "schedules.db")

ROLE_PRIORITY = {
    "btc": 4,
    "instructor": 3,
    "coach": 3,
    "mentor": 2,
    "student": 1,
}

# Các kênh được coi là "nguồn thông báo chính thức" -> mới chạy Extraction Agent.
# Kênh tro-ly-lich-trinh là kênh hỏi-đáp với AI, KHÔNG phải nguồn thông báo.
OFFICIAL_CHANNELS = {"thong-bao-chung", "lich-hoc-moi"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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

        # Lịch bận cá nhân do học viên tự khai trong câu hỏi (chưa có auth thật nên
        # dùng user_label tự do; đủ cho prototype "augment" theo spec.md §4).
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


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

def upsert_message(msg_id, channel, sender, sender_role, content, created_at=None, is_edited=False):
    created_at = created_at or now_iso()
    with get_conn() as conn:
        existing = conn.execute("SELECT msg_id FROM messages WHERE msg_id=?", (msg_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE messages SET content=?, is_edited=1, edited_at=? WHERE msg_id=?""",
                (content, now_iso(), msg_id),
            )
        else:
            conn.execute(
                """INSERT INTO messages (msg_id, channel, sender, sender_role, content, created_at, is_edited, edited_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, channel, sender, sender_role, content, created_at, int(is_edited), None),
            )
    return get_message(msg_id)


def get_message(msg_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM messages WHERE msg_id=?", (msg_id,)).fetchone()
        return dict(row) if row else None


def list_messages(channel: str, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE channel=? ORDER BY created_at ASC LIMIT ?",
            (channel, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def search_messages(keyword: str, channel: str = None, limit: int = 10):
    q = "SELECT * FROM messages WHERE content LIKE ?"
    params = [f"%{keyword}%"]
    if channel:
        q += " AND channel=?"
        params.append(channel)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# official_schedules
# ---------------------------------------------------------------------------

def next_schedule_id():
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM official_schedules").fetchone()
        return f"SCH_{row['c'] + 1:03d}"


def create_schedule(title, start_time, end_time, is_mandatory, category, host, location,
                     source_msg_id, source_channel):
    sched_id = next_schedule_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO official_schedules
               (id, title, start_time, end_time, is_mandatory, category, host, location,
                status, source_msg_id, source_channel, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (sched_id, title, start_time, end_time, int(is_mandatory), category, host, location,
             source_msg_id, source_channel, ts, ts),
        )
    return get_schedule(sched_id)


def update_schedule(sched_id, source_msg_id, source_channel, **fields):
    """Ghi đè theo bản tin MỚI NHẤT — đúng nguyên tắc chỗ khó ④ trong spec.md."""
    allowed = {"title", "start_time", "end_time", "is_mandatory", "category", "host", "location", "status"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?")
            params.append(v)
    sets += ["source_msg_id=?", "source_channel=?", "updated_at=?"]
    params += [source_msg_id, source_channel, now_iso(), ]
    params.append(sched_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE official_schedules SET {', '.join(sets)} WHERE id=?", params)
    return get_schedule(sched_id)


def cancel_schedule(sched_id, source_msg_id, source_channel):
    return update_schedule(sched_id, source_msg_id, source_channel, status="canceled")


def get_schedule(sched_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM official_schedules WHERE id=?", (sched_id,)).fetchone()
        return dict(row) if row else None


def list_active_schedules_for_matching(limit=30):
    """Danh sách event đang active, đưa cho Extraction Agent để nó tự quyết định
    tin nhắn mới là 'create' (sự kiện mới) hay 'update/cancel' (sửa sự kiện cũ)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, title, start_time, end_time, category, host, status
               FROM official_schedules WHERE status='active'
               ORDER BY start_time DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def query_schedules(date_from=None, date_to=None, category=None, status="active", mandatory_only=None):
    """Tool chính mà ReAct Agent gọi để trả lời câu hỏi học viên."""
    q = "SELECT * FROM official_schedules WHERE 1=1"
    params = []
    if status:
        q += " AND status=?"
        params.append(status)
    if date_from:
        q += " AND end_time >= ?"
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


# ---------------------------------------------------------------------------
# personal_busy_slots
# ---------------------------------------------------------------------------

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
