"""
seed_data.py — Nạp lại đúng bộ tin nhắn đang hiển thị trong codebase/mock_ui/index.html
(biến `channelsData`) vào DB thật, đi qua Extraction Agent thật (không hardcode
official_schedules như db.py bản cũ) -> đảm bảo demo UI và backend khớp nhau.

Chạy:  cd codebase/src && python seed_data.py
(cần OPENROUTER_API_KEY trong .env vì script này gọi Extraction Agent thật)
"""
import os
from dotenv import load_dotenv
load_dotenv()

import db
import ingestion

db.init_db()

# role mapping theo người gửi xuất hiện trong mock_ui/index.html
SENDER_ROLE = {
    "BTC Hackathon": "btc",
    "Giảng viên Tín": "instructor",
    "Hội Đồng Chấm Capstone": "instructor",
    "Coach Hùng": "coach",
    "Coach Quân": "coach",
    "Mentor Doanh Nghiệp": "mentor",
}

# Copy nguyên văn message text từ mock_ui/index.html (channelsData), gắn thêm
# created_at cụ thể (mock UI chỉ có label tương đối "Hôm nay", "Hôm qua"...).
# Quy ước: "hôm nay" trong data demo = 2026-07-30 (đúng ngày Changelog trong spec.md).
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
         content="LỊCH WEEK 2: Thứ 2 tới (2026-08-03, 09:00 - 11:30) khởi động Module 4 - Agentic RAG & GraphRAG. "
                 "Hạn nộp Bài Lab 4 vào 23:59 Thứ 6 (2026-08-07)."),
    dict(msg_id="msg_10100", channel="thong-bao-chung", sender="Hội Đồng Chấm Capstone",
         created_at="2026-07-25T10:00:00",
         content="Hạn chốt nộp Đề xuất Đồ án Tốt nghiệp Capstone là 23:59 ngày 2026-08-15."),
    dict(msg_id="msg_10200", channel="thong-bao-chung", sender="BTC Hackathon",
         created_at="2026-07-20T15:00:00",
         content="LỄ BẾ MẠC & DEMO DAY CAPSTONE: Diễn ra vào 18:00 - 21:00 ngày 2026-08-28 tại Discord Stage & Offline."),

    # --- #lich-hoc-moi ---
    # msg_9810 là thông báo gốc về Mentoring Chấm CP2 (ban đầu lúc 15:00)
    # -> msg_9821 sẽ "update" đổi sang 17:00, đúng luồng "thay đổi lịch"
    dict(msg_id="msg_9810", channel="lich-hoc-moi", sender="Coach Hùng",
         created_at="2026-07-29T14:00:00",
         content="LỊCH MENTORING: Buổi Mentoring Chấm CP2 sẽ diễn ra lúc 15:00 - 16:30 hôm nay (2026-07-30) "
                 "tại Discord Voice 1."),
    # (msg_9700 là seed tổng hợp thêm — bản gốc mock_ui chỉ có tin HỦY, không có tin
    #  công bố ban đầu; thêm vào để demo được đúng luồng "hủy" chỗ khó ① trong spec.md)
    dict(msg_id="msg_9700", channel="lich-hoc-moi", sender="Coach Quân",
         created_at="2026-07-27T10:00:00",
         content="WORKSHOP TỰ CHỌN: 'Kỹ năng Prompting Nâng Cao' diễn ra sáng Thứ 7 (2026-08-01, 09:30 - 11:30)."),
    dict(msg_id="msg_9821", channel="lich-hoc-moi", sender="Coach Hùng",
         created_at="2026-07-30T09:30:00",
         content="THAY ĐỔI LỊCH MENTORING: Buổi Mentoring Chấm CP2 chiều nay diễn ra lúc 17:00 - 18:00 "
                 "tại Discord Voice 1 (2026-07-30)."),
    dict(msg_id="msg_9905", channel="lich-hoc-moi", sender="Coach Quân",
         created_at="2026-07-30T13:00:00",
         content="LỊCH CP5: Chiều Thứ 5 (2026-07-31, 14:00 - 16:00) tiến hành Dry Run tại Voice 2."),
    dict(msg_id="msg_9950", channel="lich-hoc-moi", sender="BTC Hackathon",
         created_at="2026-07-30T14:15:00",
         content="THÔNG BÁO HỦY LỊCH: Do server Discord bảo trì định kỳ, buổi Workshop tự chọn "
                 "'Kỹ năng Prompting Nâng Cao' sáng Thứ 7 (2026-08-01, 09:30 - 11:30) ĐÃ BỊ HỦY."),
    dict(msg_id="msg_10025", channel="lich-hoc-moi", sender="Coach Hùng",
         created_at="2026-07-29T16:00:00",
         content="LỊCH TUẦN 2: Mở thêm slot 1-on-1 Code Review & Fix bug với Coach vào 15:00 - 16:30 "
                 "Thứ 4 (2026-08-05) tại Discord Voice 3."),
    dict(msg_id="msg_10150", channel="lich-hoc-moi", sender="Mentor Doanh Nghiệp",
         created_at="2026-07-26T11:00:00",
         content="WORKSHOP THÁNG 8: Session Định hướng Sự nghiệp & Review CV 1-1 với Mentor diễn ra "
                 "vào 19:30 - 21:30 ngày 2026-08-20 trên Discord Stage."),
]


def run():
    for m in SEED_MESSAGES:
        role = SENDER_ROLE.get(m["sender"], "student")
        print(f"Ingest {m['msg_id']} ({m['sender']}, role={role})...", end=" ")
        result = ingestion.ingest_message(
            msg_id=m["msg_id"], channel=m["channel"], sender=m["sender"],
            sender_role=role, content=m["content"], created_at=m["created_at"],
        )
        ext = result.get("extraction") or {}
        print(f"-> action={ext.get('action')}")

    print("\nXong. Xem lịch đã trích xuất:")
    for s in db.query_schedules(status="active"):
        print(f"  [{s['id']}] {s['title']} | {s['start_time']} -> {s['end_time']} "
              f"| {s['category']} | mandatory={bool(s['is_mandatory'])} | source={s['source_msg_id']}")


if __name__ == "__main__":
    run()
