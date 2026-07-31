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
    load_dotenv()
except ImportError:
    pass

import db
import ingestion

# `discord` chỉ cần khi thật sự kết nối — import trong hàm để `--stats` vẫn chạy được
# trên máy chưa cài discord.py (đây là lệnh hay dùng nhất để kiểm tra dữ liệu đã vào chưa).

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


async def run_backfill(limit: int, extract: bool):
    import discord  # noqa: PLC0415 — xem ghi chú ở đầu file
    from discord_bot import WATCHED_CHANNEL_IDS, MIN_CONTENT_LENGTH, resolve_sender_role

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    stats = {"saved": 0, "skipped": 0, "extracted": 0, "errors": 0}

    @client.event
    async def on_ready():
        print(f"✅ Đã kết nối Discord với tên {client.user}")
        print(f"💾 Ghi vào: {db.DB_PATH}")
        print(f"⚙️  limit={limit}/kênh · extract={'BẬT (tốn LLM)' if extract else 'TẮT (chỉ lưu raw)'}\n")
        db.init_db()

        for guild in client.guilds:
            print(f"🏠 Server: {guild.name}")
            for channel in guild.text_channels:
                if WATCHED_CHANNEL_IDS and channel.id not in WATCHED_CHANNEL_IDS:
                    continue
                try:
                    count = await backfill_channel(channel, limit, extract, stats)
                    print(f"   #{channel.name:<28} nạp {count} tin nhắn")
                except discord.Forbidden:
                    print(f"   #{channel.name:<28} ⛔ bot không có quyền đọc, bỏ qua")
                except Exception as e:
                    print(f"   #{channel.name:<28} ⚠️  {e}")
                    stats["errors"] += 1

        print(f"\n✅ Xong. Đã lưu {stats['saved']} · bỏ qua {stats['skipped']} (quá ngắn) "
              f"· trích lịch {stats['extracted']} · lỗi {stats['errors']}")

        if stats.get("no_roles"):
            print(
                f"\n⚠️  CẢNH BÁO: {stats['no_roles']}/{stats['saved']} tin nhắn KHÔNG đọc được role Discord\n"
                "   -> tất cả bị gán 'student' -> không có nguồn chính thức -> KHÔNG trích được lịch.\n"
                "   Nguyên nhân: chưa bật SERVER MEMBERS INTENT.\n"
                "   Sửa: Discord Developer Portal -> Bot -> Privileged Gateway Intents\n"
                "        -> bật SERVER MEMBERS INTENT -> chạy lại backfill."
            )
        show_stats()
        await client.close()

    await client.start(DISCORD_BOT_TOKEN)


async def backfill_channel(channel, limit, extract, stats):
    from discord_bot import MIN_CONTENT_LENGTH, resolve_sender_role

    count = 0
    async for message in channel.history(limit=limit, oldest_first=True):
        if message.author.bot:
            continue
        if len(message.content.strip()) < MIN_CONTENT_LENGTH:
            stats["skipped"] += 1
            continue

        # Nếu chưa bật SERVER MEMBERS INTENT, history() trả về User (không có .roles)
        # -> mọi người đều bị gán 'student' -> KHÔNG có nguồn chính thức nào -> không
        # trích được lịch, mà cũng không có lỗi. Đếm lại để cảnh báo ở cuối.
        if not getattr(message.author, "roles", None):
            stats["no_roles"] = stats.get("no_roles", 0) + 1

        sender_role = resolve_sender_role(message.author)

        if extract:
            result = ingestion.ingest_message(
                msg_id=f"msg_{message.id}",
                channel=channel.name,
                sender=message.author.display_name or message.author.name,
                sender_role=sender_role,
                content=message.content,
                created_at=message.created_at.isoformat(),
            )
            if result.get("extraction"):
                stats["extracted"] += 1
        else:
            # Bỏ qua hoàn toàn Extraction Agent -> ghi thẳng vào bảng messages, 0 lời gọi LLM
            db.upsert_message(
                msg_id=f"msg_{message.id}",
                channel=channel.name,
                sender=message.author.display_name or message.author.name,
                sender_role=sender_role,
                content=message.content,
                created_at=message.created_at.isoformat(),
            )

        stats["saved"] += 1
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nạp lịch sử tin nhắn Discord vào DB")
    parser.add_argument("--limit", type=int, default=500, help="Số tin nhắn mỗi kênh (mặc định 500)")
    parser.add_argument("--no-extract", action="store_true",
                        help="Chỉ lưu raw, KHÔNG gọi Extraction Agent (khuyến nghị cho lần chạy đầu)")
    parser.add_argument("--stats", action="store_true", help="Chỉ in thống kê DB rồi thoát")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        sys.exit(0)

    if not DISCORD_BOT_TOKEN:
        print("❌ Chưa có DISCORD_BOT_TOKEN. Điền vào repo/codebase/.env rồi chạy lại.")
        sys.exit(1)

    asyncio.run(run_backfill(limit=args.limit, extract=not args.no_extract))
