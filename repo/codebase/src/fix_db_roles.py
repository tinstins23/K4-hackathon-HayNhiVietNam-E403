"""
fix_db_roles.py — Script cập nhật / sửa chữa vai trò (sender_role) bị lưu sai trong CSDL SQLite schedules.db.

Nguyên nhân trước đây:
  Logic fallback resolve_sender_role() cũ chứa từ khoá "thắng" và "t034" làm sai vai trò
  của Nguyễn Mạnh Thắng (Học viên HV001 / T034) thành "coach".

Script này:
  1. Cập nhật tất cả tin nhắn từ Nguyễn Mạnh Thắng / T034 trong bảng messages về sender_role = 'student'.
  2. Rà soát và xoá các lịch chính thức (nếu có) bị trích xuất nhầm từ tin nhắn của học viên.
"""
import sqlite3
import sys
import os

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_SRC_DIR, "schedules.db")

def fix_roles():
    sys.stdout.reconfigure(encoding='utf-8')
    if not os.path.exists(DB_PATH):
        print(f"❌ Không tìm thấy database tại {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print(f"💾 Đang kết nối CSDL: {DB_PATH}")

    # 1. Tìm các tin nhắn bị lưu sai role của Nguyễn Mạnh Thắng / T034
    cur = conn.cursor()
    cur.execute("""
        SELECT msg_id, channel, sender, sender_role
        FROM messages
        WHERE (sender LIKE '%Thắng%' OR sender LIKE '%t034%' OR sender LIKE '%T034%')
          AND sender_role != 'student'
    """)
    wrong_rows = cur.fetchall()

    if not wrong_rows:
        print("✅ Không có tin nhắn nào của Nguyễn Mạnh Thắng / T034 bị lưu sai vai trò.")
    else:
        print(f"⚠️ Phát hiện {len(wrong_rows)} tin nhắn bị lưu sai role thành 'coach':")
        for r in wrong_rows:
            print(f"   - ID: {r['msg_id']} | Sender: '{r['sender']}' | Kênh: #{r['channel']} | Current Role: '{r['sender_role']}'")

        # Cập nhật về student
        cur.execute("""
            UPDATE messages
            SET sender_role = 'student'
            WHERE (sender LIKE '%Thắng%' OR sender LIKE '%t034%' OR sender LIKE '%T034%')
        """)
        updated_cnt = cur.rowcount
        conn.commit()
        print(f"✅ Đã sửa thành công {updated_cnt} dòng trong bảng messages -> sender_role = 'student'.")

    # 2. Rà soát lịch chính thức trích xuất từ các tin nhắn học viên (nếu có)
    cur.execute("""
        SELECT id, title, source_msg_id
        FROM official_schedules
        WHERE source_msg_id IN (
            SELECT msg_id FROM messages WHERE sender_role = 'student'
        )
    """)
    invalid_schedules = cur.fetchall()
    if invalid_schedules:
        print(f"⚠️ Phát hiện {len(invalid_schedules)} lịch trong official_schedules được tạo từ tin nhắn học viên:")
        for s in invalid_schedules:
            print(f"   - Schedule ID: {s['id']} | Title: '{s['title']}' | Source Msg: {s['source_msg_id']}")
        cur.execute("""
            DELETE FROM official_schedules
            WHERE source_msg_id IN (
                SELECT msg_id FROM messages WHERE sender_role = 'student'
            )
        """)
        conn.commit()
        print(f"✅ Đã dọn dẹp {len(invalid_schedules)} lịch không chính thức khỏi official_schedules.")

    conn.close()
    print("🎉 Hoàn tất kiểm tra và cập nhật CSDL.")

if __name__ == "__main__":
    fix_roles()
