"""
seed_data.py — Nạp bộ tin nhắn seed & lịch trình chính thức vào SQLite DB
Đảm bảo cả demo UI, Agent và Evaluation Runner đều dùng chung bộ dữ liệu mẫu chuẩn.
"""
import os
from dotenv import load_dotenv
load_dotenv()

import db
import ingestion

db.init_db()

SENDER_ROLE = {
    "BTC Hackathon": "btc",
    "Giảng viên Tín": "instructor",
    "Hội Đồng Chấm Capstone": "instructor",
    "Coach Hùng": "coach",
    "Coach Quân": "coach",
    "Mentor Doanh Nghiệp": "mentor",
}

SEED_MESSAGES = [
    # --- #thong-bao-chung ---
    dict(msg_id="msg_9801", channel="thong-bao-chung", sender="BTC Hackathon",
         created_at="2026-07-28T08:00:00",
         content="KHAI MẠC HACKATHON BATCH 03: Phát đề bài và phát động CP1 Chốt Canvas (09:00 - 11:30 ngày 1)."),
    dict(msg_id="msg_9844", channel="thong-bao-chung", sender="Giảng viên Tín",
         created_at="2026-07-29T09:00:00",
         content="Buổi học Live chiều Thứ 4 tuần này (2026-07-31, 14:00 - 16:30) học về ReAct Engine & Function Calling."),
    dict(msg_id="msg_9890", channel="thong-bao-chung", sender="BTC Hackathon",
         created_at="2026-07-30T11:00:00",
         content="LƯU Ý HẠN NỘP BÀI CP4: Hạn cứng nộp file spec.md là đúng 23:59 hôm nay (2026-07-30)."),
    dict(msg_id="msg_10010", channel="thong-bao-chung", sender="Giảng viên Tín",
         created_at="2026-07-28T14:00:00",
         content="LỊCH WEEK 2: Thứ 2 tới (2026-08-03, 09:00 - 11:30) khởi động Module 4 - Agentic RAG & GraphRAG. Hạn nộp Bài Lab 4 vào 23:59 Thứ 6 (2026-08-07)."),
    dict(msg_id="msg_10100", channel="thong-bao-chung", sender="Hội Đồng Chấm Capstone",
         created_at="2026-07-25T10:00:00",
         content="Hạn chốt nộp Đề xuất Đồ án Tốt nghiệp Capstone là 23:59 ngày 2026-08-15."),
    dict(msg_id="msg_10200", channel="thong-bao-chung", sender="BTC Hackathon",
         created_at="2026-07-20T15:00:00",
         content="LỄ BẾ MẠC & DEMO DAY CAPSTONE: Diễn ra vào 18:00 - 21:00 ngày 2026-08-28 tại Discord Stage & Offline."),

    # --- #lich-hoc-moi ---
    dict(msg_id="msg_9810", channel="lich-hoc-moi", sender="Coach Hùng",
         created_at="2026-07-29T14:00:00",
         content="LỊCH MENTORING: Buổi Mentoring Chấm CP2 sẽ diễn ra lúc 15:00 - 16:30 hôm nay (2026-07-30) tại Discord Voice 1."),
    dict(msg_id="msg_9700", channel="lich-hoc-moi", sender="Coach Quân",
         created_at="2026-07-27T10:00:00",
         content="WORKSHOP TỰ CHỌN: 'Kỹ năng Prompting Nâng Cao' diễn ra sáng Thứ 7 (2026-08-01, 09:30 - 11:30)."),
    dict(msg_id="msg_9821", channel="lich-hoc-moi", sender="Coach Hùng",
         created_at="2026-07-30T09:30:00",
         content="THAY ĐỔI LỊCH MENTORING: Buổi Mentoring Chấm CP2 chiều nay diễn ra lúc 17:00 - 18:00 tại Discord Voice 1 (2026-07-30)."),
    dict(msg_id="msg_9905", channel="lich-hoc-moi", sender="Coach Quân",
         created_at="2026-07-30T13:00:00",
         content="LỊCH CP5: Chiều Thứ 5 (2026-07-31, 14:00 - 16:00) tiến hành Dry Run tại Voice 2."),
    dict(msg_id="msg_9950", channel="lich-hoc-moi", sender="BTC Hackathon",
         created_at="2026-07-30T14:15:00",
         content="THÔNG BÁO HỦY LỊCH: Do server Discord bảo trì định kỳ, buổi Workshop tự chọn 'Kỹ năng Prompting Nâng Cao' sáng Thứ 7 (2026-08-01, 09:30 - 11:30) ĐÃ BỊ HỦY."),
    dict(msg_id="msg_10025", channel="lich-hoc-moi", sender="Coach Hùng",
         created_at="2026-07-29T16:00:00",
         content="LỊCH TUẦN 2: Mở thêm slot 1-on-1 Code Review & Fix bug với Coach vào 15:00 - 16:30 Thứ 4 (2026-08-05) tại Discord Voice 3."),
    dict(msg_id="msg_10150", channel="lich-hoc-moi", sender="Mentor Doanh Nghiệp",
         created_at="2026-07-26T11:00:00",
         content="WORKSHOP THÁNG 8: Session Định hướng Sự nghiệp & Review CV 1-1 với Mentor diễn ra vào 19:30 - 21:30 ngày 2026-08-20 trên Discord Stage."),
]

PRESET_SCHEDULES = [
    {
        "id": "SCH_001",
        "title": "Buổi Mentoring Chấm CP2",
        "start_time": "2026-07-30T17:00:00",
        "end_time": "2026-07-30T18:00:00",
        "is_mandatory": 1,
        "category": "MENTORING",
        "host": "Coach Hùng",
        "location": "Discord Voice 1",
        "status": "active",
        "source_msg_id": "msg_9821",
        "source_channel": "lich-hoc-moi"
    },
    {
        "id": "SCH_002",
        "title": "Học Online Live - ReAct & Function Calling",
        "start_time": "2026-07-31T14:00:00",
        "end_time": "2026-07-31T16:30:00",
        "is_mandatory": 1,
        "category": "CLASS",
        "host": "Giảng viên Tín",
        "location": "Discord Online Live",
        "status": "active",
        "source_msg_id": "msg_9844",
        "source_channel": "thong-bao-chung"
    },
    {
        "id": "SCH_003",
        "title": "Hạn nộp Spec.md (CP4)",
        "start_time": "2026-07-30T23:59:00",
        "end_time": "2026-07-30T23:59:00",
        "is_mandatory": 1,
        "category": "DEADLINE",
        "host": "BTC Hackathon",
        "location": "#thong-bao-chung",
        "status": "active",
        "source_msg_id": "msg_9890",
        "source_channel": "thong-bao-chung"
    },
    {
        "id": "SCH_004",
        "title": "Kỹ năng Prompting Nâng Cao",
        "start_time": "2026-08-01T09:30:00",
        "end_time": "2026-08-01T11:30:00",
        "is_mandatory": 0,
        "category": "WORKSHOP",
        "host": "Coach Quân",
        "location": "#lich-hoc-moi",
        "status": "canceled",
        "source_msg_id": "msg_9950",
        "source_channel": "lich-hoc-moi"
    },
    {
        "id": "SCH_005",
        "title": "LỊCH CP5: Dry Run",
        "start_time": "2026-07-31T14:00:00",
        "end_time": "2026-07-31T16:00:00",
        "is_mandatory": 1,
        "category": "EVENT",
        "host": "Coach Quân",
        "location": "Voice 2",
        "status": "active",
        "source_msg_id": "msg_9905",
        "source_channel": "lich-hoc-moi"
    },
    {
        "id": "SCH_006",
        "title": "Khởi động Module 4 - Agentic RAG & GraphRAG & Lab 4",
        "start_time": "2026-08-03T09:00:00",
        "end_time": "2026-08-07T23:59:00",
        "is_mandatory": 1,
        "category": "ROADMAP",
        "host": "Giảng viên Tín",
        "location": "#thong-bao-chung",
        "status": "active",
        "source_msg_id": "msg_10010",
        "source_channel": "thong-bao-chung"
    },
    {
        "id": "SCH_007",
        "title": "Slot 1-on-1 Code Review & Fix bug với Coach",
        "start_time": "2026-08-05T15:00:00",
        "end_time": "2026-08-05T16:30:00",
        "is_mandatory": 0,
        "category": "MENTORING",
        "host": "Coach Hùng",
        "location": "Discord Voice 3",
        "status": "active",
        "source_msg_id": "msg_10025",
        "source_channel": "lich-hoc-moi"
    },
    {
        "id": "SCH_008",
        "title": "Hạn chốt nộp Đề xuất Đồ án Tốt nghiệp Capstone",
        "start_time": "2026-08-15T23:59:00",
        "end_time": "2026-08-15T23:59:00",
        "is_mandatory": 1,
        "category": "DEADLINE",
        "host": "Hội Đồng Chấm Capstone",
        "location": "#thong-bao-chung",
        "status": "active",
        "source_msg_id": "msg_10100",
        "source_channel": "thong-bao-chung"
    },
    {
        "id": "SCH_009",
        "title": "Session Định hướng Sự nghiệp & Review CV 1-1",
        "start_time": "2026-08-20T19:30:00",
        "end_time": "2026-08-20T21:30:00",
        "is_mandatory": 0,
        "category": "WORKSHOP",
        "host": "Mentor Doanh Nghiệp",
        "location": "Discord Stage",
        "status": "active",
        "source_msg_id": "msg_10150",
        "source_channel": "lich-hoc-moi"
    },
    {
        "id": "SCH_010",
        "title": "LỄ BẾ MẠC & DEMO DAY CAPSTONE",
        "start_time": "2026-08-28T18:00:00",
        "end_time": "2026-08-28T21:00:00",
        "is_mandatory": 1,
        "category": "EVENT",
        "host": "BTC Hackathon",
        "location": "Discord Stage & Offline",
        "status": "active",
        "source_msg_id": "msg_10200",
        "source_channel": "thong-bao-chung"
    }
]

def seed_deterministic_data():
    db.init_db()
    with db.get_conn() as conn:
        for m in SEED_MESSAGES:
            role = SENDER_ROLE.get(m["sender"], "student")
            db.upsert_message(
                msg_id=m["msg_id"], channel=m["channel"], sender=m["sender"],
                sender_role=role, content=m["content"], created_at=m["created_at"]
            )
        
        for s in PRESET_SCHEDULES:
            conn.execute(
                """INSERT OR REPLACE INTO official_schedules
                   (id, title, start_time, end_time, is_mandatory, category, host, location,
                    status, source_msg_id, source_channel, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["id"], s["title"], s["start_time"], s["end_time"], s["is_mandatory"],
                 s["category"], s["host"], s["location"], s["status"], s["source_msg_id"],
                 s["source_channel"], db.now_iso(), db.now_iso())
            )

def run():
    seed_deterministic_data()
    print("Xong seed deterministic data. Xem lịch đã trích xuất trong DB:")
    for s in db.query_schedules(status=None):
        print(f"  [{s['id']}] {s['title']} | {s['start_time']} -> {s['end_time']} "
              f"| {s['category']} | status={s['status']} | mandatory={bool(s['is_mandatory'])} | source={s['source_msg_id']}")

if __name__ == "__main__":
    run()
