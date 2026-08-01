"""
fix_db_roles.py — Sửa sender_role bị lưu sai trong bảng messages.
"""
import sqlite3
import sys
import os

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_SRC_DIR, "schedules.db")


def fix_roles():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(DB_PATH):
        print(f"Khong tim thay database tai {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT msg_id, channel, sender, sender_role
        FROM messages
        WHERE (sender LIKE '%Thắng%' OR sender LIKE '%t034%' OR sender LIKE '%T034%')
          AND sender_role != 'student'
    """)
    wrong_rows = cur.fetchall()

    if not wrong_rows:
        print("Khong co tin nhan nao bi luu sai vai tro.")
    else:
        print(f"Phat hien {len(wrong_rows)} tin bi luu sai role:")
        for r in wrong_rows:
            print(f"   - {r['msg_id']} | {r['sender']} | #{r['channel']} | {r['sender_role']}")
        cur.execute("""
            UPDATE messages
            SET sender_role = 'student'
            WHERE (sender LIKE '%Thắng%' OR sender LIKE '%t034%' OR sender LIKE '%T034%')
        """)
        conn.commit()
        print(f"Da sua {cur.rowcount} dong -> sender_role = student.")

    conn.close()
    print("Xong.")


if __name__ == "__main__":
    fix_roles()
