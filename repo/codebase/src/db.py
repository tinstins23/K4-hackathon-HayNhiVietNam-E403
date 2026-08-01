"""
db.py — SQLite cho Trợ lý AI (schema messages-only).

Bảng:
  - messages: tin nhắn thô Discord (nguồn sự thật; agent search trực tiếp)
  - idempotency_locks: khoá chống xử lý trùng giữa nhiều tiến trình bot

Schema cũ `official_schedules` / `personal_busy_slots` bị DROP khi `init_db()`.
"""
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

# DB_PATH mặc định neo theo vị trí file db.py này, KHÔNG theo cwd.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_env_db_path = os.getenv("DB_PATH") or "schedules.db"
DB_PATH = _env_db_path if os.path.isabs(_env_db_path) else os.path.join(_SRC_DIR, _env_db_path)

ROLE_PRIORITY = {
    "admin": 4,
    "btc": 4,
    "coach": 3,
    "instructor": 3,
    "mentor": 3,
    "student": 1,
}

OFFICIAL_CHANNEL_IDS = {
    int(c.strip())
    for c in (os.getenv("ANNOUNCEMENT_CHANNEL_IDS") or os.getenv("WATCHED_CHANNEL_IDS") or "").split(",")
    if c.strip().isdigit()
}
OFFICIAL_CHANNELS = OFFICIAL_CHANNEL_IDS
MIN_OFFICIAL_ROLE = "coach"


def normalize_channel_name(name: str) -> str:
    if not name:
        return ""
    return name.strip().lstrip("#").lower()


def is_official_source(sender_role: str, channel_id: int = None, channel_name: str = None) -> bool:
    if OFFICIAL_CHANNEL_IDS and channel_id is not None:
        try:
            if int(channel_id) not in OFFICIAL_CHANNEL_IDS:
                return False
        except (ValueError, TypeError):
            pass
    return ROLE_PRIORITY.get(sender_role, 0) >= ROLE_PRIORITY[MIN_OFFICIAL_ROLE]


def _with_trust(row) -> dict:
    d = dict(row)
    d["is_official"] = is_official_source(d.get("sender_role"), channel_name=d.get("channel"))
    return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


VN_TZ = timezone(timedelta(hours=7))


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def to_vn_display(iso_str: str) -> str:
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


# Schema messages-only. Bảng cũ (official_schedules, personal_busy_slots) bị DROP khi init.
_LEGACY_TABLES = ("official_schedules", "personal_busy_slots")


def _drop_legacy_tables(conn):
    """Gỡ schema cũ khỏi file DB đã tồn tại (SQLite không có migration framework)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    for name in _LEGACY_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {name}")
    # Index gắn bảng lịch cũ (nếu còn sót tên)
    conn.execute("DROP INDEX IF EXISTS idx_sched_time")
    # sqlite_sequence còn lại sau khi DROP bảng AUTOINCREMENT cũ
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('personal_busy_slots', 'official_schedules')")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA foreign_keys = ON")


def init_db():
    with get_conn() as conn:
        _drop_legacy_tables(conn)
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_channel ON messages(channel, created_at)")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_locks (
            lock_key TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """)


def clear_db():
    """Xoá sạch dữ liệu; đảm bảo schema chỉ còn messages + idempotency_locks."""
    init_db()
    with get_conn() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM idempotency_locks")


def reset_db():
    clear_db()


def try_claim(lock_key: str) -> bool:
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
    if not msg_id:
        return ""
    cleaned = str(msg_id).strip().lstrip("#")
    if cleaned.startswith("msg_"):
        return cleaned
    if cleaned.isdigit():
        return f"msg_{cleaned}"
    return cleaned


def get_msg_id_candidates(msg_id: str) -> list:
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
        existing = conn.execute(
            f"SELECT msg_id FROM messages WHERE msg_id IN ({placeholders})", cands
        ).fetchone()
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
            f"SELECT * FROM messages WHERE msg_id IN ({placeholders})", cands
        ).fetchone()
        return _with_trust(row) if row else None


def list_messages(channel: str, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE channel=? ORDER BY created_at ASC LIMIT ?",
            (channel, limit),
        ).fetchall()
        return [_with_trust(r) for r in rows]


def list_recent_messages(limit: int = 50, only_official: bool = True, channel: str = None):
    """Liệt kê tin gần nhất (không cần keyword) — dùng khi hỏi lịch tuần/ngày."""
    q = "SELECT * FROM messages WHERE 1=1"
    params = []
    if channel:
        q += " AND channel=?"
        params.append(channel)
    q += " ORDER BY created_at DESC LIMIT ?"
    # lấy dư rồi lọc is_official nếu cần
    params.append(limit if not only_official else limit * 3)
    with get_conn() as conn:
        rows = [_with_trust(r) for r in conn.execute(q, params).fetchall()]
    if only_official:
        rows = [r for r in rows if r.get("is_official")]
    return rows[:limit]


def search_messages(keyword: str, channel: str = None, limit: int = 40,
                     sender_role: str = None, only_official: bool = None,
                     date_from: str = None, date_to: str = None):
    """Tìm theo từ khoá. date_from/date_to lọc theo thời điểm ĐĂNG tin (created_at),
    KHÔNG phải ngày sự kiện trong nội dung."""
    kw = (keyword or "").strip()
    # Keyword rỗng / quá chung chung -> liệt kê tin gần nhất thay vì LIKE '%' nhiễu
    if not kw or kw in (".", "*", "a", "all", "lịch", "lich"):
        return list_recent_messages(
            limit=limit,
            only_official=True if only_official is None else bool(only_official),
            channel=channel,
        )

    cands = get_msg_id_candidates(kw)
    tokens = [t for t in kw.split() if len(t) > 1] or [kw]

    cand_conds = " OR ".join(["msg_id = ?"] * len(cands))
    like_terms = " OR ".join(["(content LIKE ? OR msg_id LIKE ? OR msg_id = ?)"] * len(tokens))
    if cand_conds:
        like_terms = f"({like_terms}) OR ({cand_conds})"

    score = " + ".join(
        ["(CASE WHEN content LIKE ? OR msg_id LIKE ? THEN 1 ELSE 0 END)"] * len(tokens)
    )

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


def delete_message(msg_id: str) -> dict:
    cands = get_msg_id_candidates(msg_id)
    if not cands:
        return {"deleted_count": 0}
    placeholders = ",".join(["?"] * len(cands))
    with get_conn() as conn:
        cursor = conn.execute(f"DELETE FROM messages WHERE msg_id IN ({placeholders})", cands)
        return {"deleted_count": cursor.rowcount}


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_PATH}")
