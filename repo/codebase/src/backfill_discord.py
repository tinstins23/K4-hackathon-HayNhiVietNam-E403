"""
backfill_discord.py — nạp LỊCH SỬ tin nhắn Discord vào bảng messages.

Vì sao cần: `discord_bot.py::on_message` chỉ nghe được tin nhắn MỚI kể từ lúc bot chạy.
Không có bước này thì bảng `messages` rỗng và AI không retrieve được gì trong ngày đầu.

Chạy:
    cd repo/codebase/src
    python backfill_discord.py --limit 500
    python backfill_discord.py --stats
    python backfill_discord.py --keep --limit 500   # giữ DB cũ, chỉ bổ sung
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

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import db

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


def show_stats():
    db.init_db()
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        print(f"\nDB: {db.DB_PATH}")
        print(f"   Tong tin nhan: {total}")
        if total:
            print("\n   Theo kenh / vai tro:")
            rows = conn.execute(
                """SELECT channel, sender_role, COUNT(*) AS c FROM messages
                   GROUP BY channel, sender_role ORDER BY c DESC"""
            ).fetchall()
            for r in rows:
                official = "official" if db.is_official_source(r["sender_role"], channel_name=r["channel"]) else "context"
                print(f"     #{r['channel']:<24} {r['sender_role']:<12} {r['c']:>5}  {official}")
        print()


async def run_backfill(limit: int, clear_first: bool = True, channel_ids: set = None):
    import discord
    from discord_bot import WATCHED_CHANNEL_IDS, resolve_sender_role

    bot_token = os.getenv("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN
    if not bot_token:
        print("LOI: Chua tim thay DISCORD_BOT_TOKEN trong .env!")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    stats = {"saved": 0, "skipped": 0, "errors": 0}

    @client.event
    async def on_ready():
        print(f"Da ket noi Discord voi ten {client.user}")
        print(f"Ghi vao DB: {db.DB_PATH}")
        if clear_first:
            print("[Buoc 1/2] Xoa sach DB cu...")
            db.clear_db()
        else:
            db.init_db()

        print(f"[Buoc 2/2] Keo tin nhan raw (0 loi goi AI)...")
        target_ids = channel_ids or db.OFFICIAL_CHANNEL_IDS or set(WATCHED_CHANNEL_IDS)
        if target_ids:
            print(f"Loc Channel ID: {target_ids} · limit={limit}/kenh\n")
        else:
            print("CHUA cau hinh ANNOUNCEMENT_CHANNEL_IDS. Duyet tat ca ken...\n")

        for guild in client.guilds:
            print(f"Server: {guild.name}")
            for channel in guild.text_channels:
                if target_ids and channel.id not in target_ids:
                    continue
                try:
                    count = await backfill_channel(channel, limit, stats, resolve_sender_role)
                    print(f"   #{channel.name} (ID: {channel.id}) -> {count} tin")
                except discord.Forbidden:
                    print(f"   #{channel.name} (ID: {channel.id}) -> khong co quyen doc")
                except Exception as e:
                    print(f"   #{channel.name} (ID: {channel.id}) -> {e}")
                    stats["errors"] += 1

        print(f"\nHoan tat: saved={stats['saved']} skipped={stats['skipped']} errors={stats['errors']}")
        show_stats()
        await client.close()

    await client.start(bot_token)


async def backfill_channel(channel, limit, stats, resolve_sender_role):
    count = 0
    async for message in channel.history(limit=limit, oldest_first=True):
        if message.author.bot:
            continue

        content = message.content.strip()
        if not content:
            stats["skipped"] += 1
            continue

        member = channel.guild.get_member(message.author.id) if hasattr(channel, "guild") else None
        if not member and hasattr(channel, "guild") and hasattr(channel.guild, "fetch_member"):
            try:
                member = await channel.guild.fetch_member(message.author.id)
            except Exception:
                member = message.author

        sender_role = resolve_sender_role(member or message.author, guild=channel.guild)

        if sender_role not in ("coach", "admin", "btc", "instructor", "mentor"):
            stats["skipped"] += 1
            continue

        if not db.is_official_source(sender_role, channel_id=channel.id, channel_name=channel.name):
            stats["skipped"] += 1
            continue

        db.upsert_message(
            msg_id=f"msg_{message.id}",
            channel=channel.name,
            sender=message.author.display_name or message.author.name,
            sender_role=sender_role,
            content=content,
            created_at=message.created_at.isoformat(),
        )
        stats["saved"] += 1
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nap lich su tin nhan Discord vao bang messages")
    parser.add_argument("--limit", type=int, default=500, help="So tin toi da moi kenh")
    parser.add_argument("--channel-ids", type=str, default=None, help="Channel IDs (phay). Mac dinh tu .env")
    parser.add_argument("--clear", "--reset", action="store_true", default=True, help="Xoa DB truoc khi nap (mac dinh)")
    parser.add_argument("--keep", "--no-clear", dest="clear", action="store_false", help="Giu DB cu")
    parser.add_argument("--clear-only", action="store_true", help="Chi xoa DB roi thoat")
    parser.add_argument("--stats", action="store_true", help="Chi in thong ke DB")
    args = parser.parse_args()

    if args.clear_only:
        db.clear_db()
        print("Da xoa sach DB.")
        show_stats()
        sys.exit(0)

    if args.stats:
        show_stats()
        sys.exit(0)

    bot_token = os.getenv("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN
    if not bot_token:
        print("Chua tim thay DISCORD_BOT_TOKEN.")
        sys.exit(1)

    target_ids = (
        {int(c.strip()) for c in args.channel_ids.split(",") if c.strip().isdigit()}
        if args.channel_ids else None
    )

    asyncio.run(run_backfill(limit=args.limit, clear_first=args.clear, channel_ids=target_ids))
