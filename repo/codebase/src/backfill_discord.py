"""
backfill_discord.py — nạp LỊCH SỬ tin nhắn Discord vào DB.

Vì sao cần: `discord_bot.py::on_message` chỉ nghe được tin nhắn MỚI kể từ lúc bot chạy.
Không có bước này thì bảng `messages` rỗng và AI không retrieve được gì trong ngày đầu.

Chạy:
    cd repo/codebase/src

    # Lần đầu — CHỈ lưu raw, KHÔNG gọi LLM (khuyến nghị, xem cảnh báo bên dưới)
    python backfill_discord.py --limit 500 --no-extract

    # Xem đã nạp được gì
    python backfill_discord.py --stats

    # Sau khi đã xem qua dữ liệu, mới bật trích xuất lịch
    python backfill_discord.py --limit 500

Cảnh báo về --extract (mặc định BẬT nếu không truyền --no-extract):
    Mỗi thông báo cũ của BTC/Giảng viên sẽ tốn 1 lời gọi LLM, và Extraction Agent có thể
    tạo ra lịch của các sự kiện ĐÃ QUA hoặc trùng với lịch hiện có. Với vài trăm tin nhắn
    thì vừa tốn tiền vừa làm bẩn bảng official_schedules.
    -> Lần chạy đầu nên dùng --no-extract.
"""
import os
import sys
import argparse
import asyncio

try:
    from dotenv import load_dotenv
    _src_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_dir = os.path.abspath(os.path.join(_src_dir, ".."))
    load_dotenv(os.path.join(_repo_dir, ".env"))
    load_dotenv(os.path.join(_src_dir, ".env"))
    load_dotenv()
except ImportError:
    pass

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import db
import ingestion

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


def show_stats():
    """In thống kê những gì đang có trong DB — không cần kết nối Discord."""
    db.init_db()
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        print(f"\n📊 DB: {db.DB_PATH}")
        print(f"   Tổng tin nhắn: {total}")
        if total:
            print("\n   Theo kênh / vai trò:")
            rows = conn.execute(
                """SELECT channel, sender_role, COUNT(*) AS c FROM messages
                   GROUP BY channel, sender_role ORDER BY c DESC"""
            ).fetchall()
            for r in rows:
                official = "✅ chính thức" if db.is_official_source(r["sender_role"], r["channel"]) else "💬 ngữ cảnh"
                print(f"     #{r['channel']:<24} {r['sender_role']:<12} {r['c']:>5}  {official}")
        sched = conn.execute("SELECT COUNT(*) FROM official_schedules WHERE status='active'").fetchone()[0]
        print(f"\n   Lịch active: {sched}\n")


async def run_backfill(limit: int, clear_first: bool = True, extract: bool = False, channel_ids: set = None):
    import discord  # noqa: PLC0415 — xem ghi chú ở đầu file
    from discord_bot import WATCHED_CHANNEL_IDS, resolve_sender_role

    bot_token = os.getenv("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN
    if not bot_token:
        print("❌ LỖI: Chưa tìm thấy DISCORD_BOT_TOKEN trong file .env!")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    stats = {"saved": 0, "skipped": 0, "extracted": 0, "errors": 0}

    @client.event
    async def on_ready():
        print(f"✅ Đã kết nối Discord với tên {client.user}")
        print(f"💾 Ghi vào DB: {db.DB_PATH}")
        if clear_first:
            print("🧹 [Bước 1/2] Đang thực hiện xoá sạch 100% dữ liệu DB cũ (clear_db)...")
            db.clear_db()
        else:
            db.init_db()

        print(f"📥 [Bước 2/2] Đang kéo dữ liệu thô mới từ các kênh Discord (0 lời gọi AI, extract={extract})...")
        target_ids = channel_ids or db.OFFICIAL_CHANNEL_IDS or set(WATCHED_CHANNEL_IDS)
        if target_ids:
            print(f"⚙️  Lọc BẮT BUỘC theo Channel ID từ .env: {target_ids} · limit={limit}/kênh\n")
        else:
            print("⚠️  CHƯA CẤU HÌNH ANNOUNCEMENT_CHANNEL_IDS trong .env. Đang duyệt tất cả các kênh...")

        for guild in client.guilds:
            print(f"🏠 Server: {guild.name}")
            for channel in guild.text_channels:
                if target_ids and channel.id not in target_ids:
                    continue
                try:
                    count = await backfill_channel(channel, limit, stats, extract=extract)
                    print(f"   #{channel.name} (ID: {channel.id}) -> nạp thành công {count} tin nhắn")
                except discord.Forbidden:
                    print(f"   #{channel.name} (ID: {channel.id}) -> ⛔ bot không có quyền đọc, bỏ qua")
                except Exception as e:
                    print(f"   #{channel.name} (ID: {channel.id}) -> ⚠️ {e}")
                    stats["errors"] += 1

        print(f"\n✅ Hoàn tất đồng bộ Discord (Không dùng AI)!")
        print(f"   • Đã nạp: {stats['saved']} tin nhắn raw từ Coach/Admin")
        if extract:
            print(f"   • Đã trích xuất: {stats.get('extracted', 0)} sự kiện lịch")
        print(f"   • Bỏ qua: {stats['skipped']} tin | Lỗi: {stats['errors']}")
        show_stats()
        await client.close()

    await client.start(bot_token)


async def backfill_channel(channel, limit, stats, extract: bool = False):
    from discord_bot import resolve_sender_role

    count = 0
    async for message in channel.history(limit=limit, oldest_first=True):
        if message.author.bot:
            continue
        
        content = message.content.strip()
        if not content:
            stats["skipped"] += 1
            continue

        # Lấy Member với đầy đủ vai trò trên Discord Server
        member = channel.guild.get_member(message.author.id) if hasattr(channel, "guild") else None
        if not member and hasattr(channel, "guild") and hasattr(channel.guild, "fetch_member"):
            try:
                member = await channel.guild.fetch_member(message.author.id)
            except Exception:
                member = message.author

        sender_role = resolve_sender_role(member or message.author, guild=channel.guild)

        if sender_role not in ("coach", "admin"):
            stats["skipped"] += 1
            continue

        msg_id_str = f"msg_{message.id}"
        created_iso = message.created_at.isoformat()
        sender_name = message.author.display_name or message.author.name

        if extract:
            try:
                res = await asyncio.to_thread(
                    ingestion.ingest_message,
                    msg_id=msg_id_str,
                    channel=channel.name,
                    sender=sender_name,
                    sender_role=sender_role,
                    content=content,
                    created_at=created_iso,
                )
                if res and res.get("extraction"):
                    stats["extracted"] = stats.get("extracted", 0) + 1
            except Exception as e:
                print(f"      ⚠️ [Trích xuất AI lỗi ở #{message.id}]: {e}")
                db.upsert_message(
                    msg_id=msg_id_str,
                    channel=channel.name,
                    sender=sender_name,
                    sender_role=sender_role,
                    content=content,
                    created_at=created_iso,
                )
        else:
            # Lưu thẳng tin nhắn raw từ Coach/Admin vào SQLite DB — 0 lời gọi AI
            db.upsert_message(
                msg_id=msg_id_str,
                channel=channel.name,
                sender=sender_name,
                sender_role=sender_role,
                content=content,
                created_at=created_iso,
            )

        stats["saved"] += 1
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nạp lịch sử tin nhắn Discord vào DB (KHÔNG DÙNG AI, tự động XÓA SẠCH DB cũ và KÉO MỚI từ Discord)")
    parser.add_argument("--limit", type=int, default=500, help="Số tin nhắn tối đa mỗi kênh (mặc định 500)")
    parser.add_argument("--channel-ids", type=str, default=None,
                        help="Danh sách Channel IDs (phân cách dấu phẩy). Mặc định lấy từ .env")
    parser.add_argument("--clear", "--reset", action="store_true", default=True, help="Xoá sạch DB cũ trước khi nạp lại toàn bộ (MẶC ĐỊNH: BẬT)")
    parser.add_argument("--keep", "--no-clear", dest="clear", action="store_false", help="Giữ lại dữ liệu DB cũ (không xoá DB trước khi nạp)")
    parser.add_argument("--extract", dest="extract", action="store_true", default=False, help="Bật AI trích xuất lịch (MẶC ĐỊNH: TẮT — KHÔNG dùng AI)")
    parser.add_argument("--no-extract", dest="extract", action="store_false", help="CHỈ lưu tin nhắn thô, KHÔNG gọi AI trích xuất lịch (MẶC ĐỊNH)")
    parser.add_argument("--clear-only", action="store_true", help="Chỉ xoá sạch DB về 0 rồi thoát")
    parser.add_argument("--stats", action="store_true", help="Chỉ in thống kê DB rồi thoát")
    args = parser.parse_args()

    if args.clear_only:
        db.clear_db()
        print("🧹 Đã xoá sạch 100% dữ liệu trong DB (messages = 0, schedules = 0).")
        show_stats()
        sys.exit(0)

    if args.stats:
        show_stats()
        sys.exit(0)

    bot_token = os.getenv("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN
    if not bot_token:
        print("❌ Chưa tìm thấy DISCORD_BOT_TOKEN. Vui lòng kiểm tra lại file .env")
        sys.exit(1)

    target_ids = {int(c.strip()) for c in args.channel_ids.split(",") if c.strip().isdigit()} if args.channel_ids else None

    asyncio.run(run_backfill(
        limit=args.limit,
        clear_first=args.clear,
        extract=args.extract,
        channel_ids=target_ids
    ))



