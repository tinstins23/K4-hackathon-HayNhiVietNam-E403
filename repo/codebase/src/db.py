import sqlite3
import json

DB_PATH = "schedules.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS official_schedules (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        is_mandatory INTEGER DEFAULT 1,
        category TEXT,
        host TEXT,
        location TEXT,
        source_msg_id TEXT,
        created_at TEXT
    )
    ''')
    
    sample_events = [
        ("SCH_001", "Buổi Mentoring Chấm CP2", "2026-07-30T17:00:00", "2026-07-30T18:00:00", 1, "MENTORING", "Coach Hùng", "Discord Voice 1", "msg_9821", "2026-07-30T09:00:00"),
        ("SCH_002", "Học Online Live - ReAct & Function Calling", "2026-07-31T14:00:00", "2026-07-31T16:30:00", 1, "CLASS", "Giảng viên Tín", "Zoom Class", "msg_9844", "2026-07-30T10:00:00"),
        ("SCH_003", "Hạn nộp Spec.md (CP4)", "2026-07-31T23:59:00", "2026-07-31T23:59:00", 1, "DEADLINE", "BTC", "Git Repo", "msg_9890", "2026-07-30T11:00:00")
    ]
    
    cursor.executemany('''
    INSERT OR REPLACE INTO official_schedules 
    (id, title, start_time, end_time, is_mandatory, category, host, location, source_msg_id, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_events)
    
    conn.commit()
    conn.close()

def query_schedules():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, start_time, end_time, is_mandatory, category, host, location, source_msg_id FROM official_schedules ORDER BY start_time ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "start_time": r[2], "end_time": r[3], "is_mandatory": bool(r[4]), "category": r[5], "host": r[6], "location": r[7], "source_msg_id": r[8]} for r in rows]

if __name__ == "__main__":
    init_db()
    print("Database initialized!")
