"""
tools.py — Các Tool xử lý dữ liệu SQLite cho Trợ lý AI Sắp Xếp Lịch Trình Discord.

Đảm bảo bám sát spec.md §5:
  - Tra cứu theo ID (get_schedule_by_id) để kiểm tra chi tiết sự kiện.
  - Bao gồm timestamp created_at & updated_at trong kết quả để Agent kiểm tra bản tin mới nhất.
  - Đính kèm source_msg_id để phục vụ trích dẫn nguồn sự thật 100% (R4 Rubric).
"""
import sqlite3
from db import get_conn, now_iso, DB_PATH

def get_schedule_by_id(sched_id: str):
    """
    Truy vấn chi tiết 1 sự kiện lịch trình theo ID.
    Trả về đầy đủ thông tin bao gồm created_at, updated_at và source_msg_id
    để Agent đối soát bản tin mới nhất (Spec.md §5 - Chỗ khó ④).
    """
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, title, start_time, end_time, is_mandatory, category, 
                      host, location, status, source_msg_id, source_channel, 
                      created_at, updated_at 
               FROM official_schedules 
               WHERE id = ?""", 
            (sched_id,)
        ).fetchone()
        
        return dict(row) if row else {"error": f"Không tìm thấy lịch trình có ID: {sched_id}"}


def get_schedules_from_db(category: str = None, status: str = "active", date_from: str = None, date_to: str = None):
    """
    Truy vấn danh sách lịch trình từ SQLite database.
    Bao gồm updated_at & source_msg_id để phục vụ trích dẫn và kiểm tra độ mới của lịch.
    """
    query = """SELECT id, title, start_time, end_time, is_mandatory, category, 
                      host, location, status, source_msg_id, created_at, updated_at 
               FROM official_schedules WHERE 1=1"""
    params = []
    
    if status:
        query += " AND status = ?"
        params.append(status)
    if category:
        query += " AND category = ?"
        params.append(category)
    if date_from:
        query += " AND end_time >= ?"
        params.append(date_from)
    if date_to:
        query += " AND start_time <= ?"
        params.append(date_to)
        
    query += " ORDER BY start_time ASC, updated_at DESC"
    
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def add_or_update_schedule(sched_id: str, title: str, start_time: str, end_time: str, 
                           source_msg_id: str, category: str = "EVENT", is_mandatory: int = 1, 
                           host: str = "", location: str = "", source_channel: str = "thong-bao-chung"):
    """
    Thêm mới hoặc cập nhật một lịch trình vào DB.
    Tự động cập nhật updated_at = thời điểm hiện tại nếu sửa đổi lịch đột xuất (Spec.md §5 - Chỗ khó ④).
    """
    current_ts = now_iso()
    with get_conn() as conn:
        conn.execute('''
            INSERT INTO official_schedules 
            (id, title, start_time, end_time, is_mandatory, category, host, location, status, source_msg_id, source_channel, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                is_mandatory = excluded.is_mandatory,
                category = excluded.category,
                host = excluded.host,
                location = excluded.location,
                source_msg_id = excluded.source_msg_id,
                updated_at = ?
        ''', (sched_id, title, start_time, end_time, int(is_mandatory), category, host, location, 
              source_msg_id, source_channel, current_ts, current_ts, current_ts))
              
    return f"Đã lưu/cập nhật thành công sự kiện [{sched_id}]: {title} (Cập nhật lúc: {current_ts})"


def add_personal_busy_slot(user_label: str, title: str, start_time: str, end_time: str):
    """Thêm một khoảng thời gian bận cá nhân của học viên vào DB để AI tránh xếp trùng."""
    current_ts = now_iso()
    with get_conn() as conn:
        conn.execute('''
            INSERT INTO personal_busy_slots (user_label, title, start_time, end_time, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_label, title, start_time, end_time, current_ts))
    return f"Đã ghi nhận lịch bận cá nhân: {title} ({start_time} - {end_time})"


def list_busy_slots_from_db(user_label: str, date_from: str = None, date_to: str = None):
    """Tra cứu danh sách thời gian bận cá nhân của học viên."""
    query = "SELECT * FROM personal_busy_slots WHERE user_label = ?"
    params = [user_label]
    if date_from:
        query += " AND end_time >= ?"
        params.append(date_from)
    if date_to:
        query += " AND start_time <= ?"
        params.append(date_to)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# Dictionary chứa danh sách các tool có thể gọi
AVAILABLE_TOOLS = {
    "get_schedule_by_id": get_schedule_by_id,
    "get_schedules_from_db": get_schedules_from_db,
    "add_or_update_schedule": add_or_update_schedule,
    "add_personal_busy_slot": add_personal_busy_slot,
    "list_busy_slots_from_db": list_busy_slots_from_db
}
