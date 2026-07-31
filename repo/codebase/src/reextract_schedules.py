"""
reextract_schedules.py — Trích xuất lại lịch từ tin nhắn đã có trong bảng messages
vào official_schedules (KHÔNG xoá DB, KHÔNG gọi Discord API).

Dùng khi bot từng chỉ upsert_message (lưu raw) mà chưa chạy Extraction Agent.

Chạy từ thư mục src/:
  python reextract_schedules.py
  python reextract_schedules.py --limit 50
  python reextract_schedules.py --dry-run
"""
import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import db
import ingestion

# Role đủ tin cậy để đưa vào Extraction Agent (khớp MIN_OFFICIAL_ROLE trong db.py)
OFFICIAL_ROLES = {
    role for role, prio in db.ROLE_PRIORITY.items()
    if prio >= db.ROLE_PRIORITY[db.MIN_OFFICIAL_ROLE]
}


def list_candidate_messages(limit: int = None):
    """Lấy tin nhắn có role chính thức, chưa chắc đã có dòng official_schedules."""
    q = f"""
        SELECT m.* FROM messages m
        WHERE m.sender_role IN ({",".join("?" * len(OFFICIAL_ROLES))})
        ORDER BY m.created_at ASC
    """
    params = list(OFFICIAL_ROLES)
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def already_has_schedule(msg_id: str) -> bool:
    cands = db.get_msg_id_candidates(msg_id)
    if not cands:
        return False
    placeholders = ",".join(["?"] * len(cands))
    with db.get_conn() as conn:
        row = conn.execute(
            f"SELECT 1 FROM official_schedules WHERE source_msg_id IN ({placeholders}) LIMIT 1",
            cands,
        ).fetchone()
        return row is not None


def reextract(limit: int = None, dry_run: bool = False, skip_existing: bool = True):
    db.init_db()
    candidates = list_candidate_messages(limit=limit)
    stats = {"total": len(candidates), "skipped_existing": 0, "skipped_role": 0,
             "extracted": 0, "no_action": 0, "errors": 0}

    print(f"DB: {db.DB_PATH}")
    print(f"Candidates (role in {sorted(OFFICIAL_ROLES)}): {len(candidates)}")
    if dry_run:
        print("(dry-run — khong goi LLM)\n")

    for msg in candidates:
        msg_id = msg["msg_id"]
        role = msg["sender_role"]
        channel = msg["channel"]

        if not db.is_official_source(role, channel_name=channel):
            stats["skipped_role"] += 1
            continue

        if skip_existing and already_has_schedule(msg_id):
            stats["skipped_existing"] += 1
            print(f"  skip {msg_id} — already has schedule")
            continue

        if dry_run:
            print(f"  [dry-run] would extract {msg_id} @{channel} ({role})")
            stats["extracted"] += 1
            continue

        try:
            # is_edited=False + khoa extract:{msg_id}: tin chua tung extract van chay;
            # tin da claim khoa truoc do se bi try_claim chan (tranh trung).
            result = ingestion.ingest_message(
                msg_id=msg_id,
                channel=channel,
                sender=msg["sender"],
                sender_role=role,
                content=msg["content"],
                created_at=msg.get("created_at"),
                is_edited=False,
                channel_id=None,  # DB chi luu ten kenh; loc theo role (da gate o tren)
            )
            extraction = result.get("extraction")
            if extraction:
                action = extraction.get("action")
                sched = result.get("schedule")
                sched_id = sched.get("id") if isinstance(sched, dict) else None
                print(f"  OK {msg_id} -> action={action}" + (f" ({sched_id})" if sched_id else ""))
                stats["extracted"] += 1
            else:
                print(f"  -- {msg_id} — no extract (maybe lock already claimed)")
                stats["no_action"] += 1
        except Exception as e:
            print(f"  ERR {msg_id}: {e}")
            stats["errors"] += 1

    print("\n--- Result ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Re-extract official_schedules từ messages đã có trong DB (không xoá DB)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số tin nhắn xử lý")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê, không gọi LLM")
    parser.add_argument(
        "--force-all",
        dest="skip_existing",
        action="store_false",
        default=True,
        help="Vẫn gọi ingest kể cả tin đã có lịch (vẫn bị try_claim chặn nếu đã extract)",
    )
    args = parser.parse_args()
    reextract(limit=args.limit, dry_run=args.dry_run, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
    sys.exit(0)
