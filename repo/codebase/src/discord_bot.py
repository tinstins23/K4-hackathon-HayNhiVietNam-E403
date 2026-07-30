import os
import sqlite3
import json
import discord
from discord.ext import commands

# Tải biến môi trường từ file .env nếu có python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db, query_schedules
from scheduler_agent import ScheduleAgent

# --- CONFIGURATION FROM ENV ---
# Lấy DISCORD_BOT_TOKEN từ biến môi trường OS hoặc file .env
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Lấy danh sách ID kênh thông báo từ env (ví dụ: ANNOUNCEMENT_CHANNEL_IDS=123456789,987654321)
raw_channel_ids = os.getenv("ANNOUNCEMENT_CHANNEL_IDS", "")
ANNOUNCEMENT_CHANNEL_IDS = [
    int(cid.strip()) for cid in raw_channel_ids.split(",") if cid.strip().isdigit()
]

# Client setup với Intents
intents = discord.Intents.default()
intents.message_content = True  # Bắt buộc bật trên Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)
agent = ScheduleAgent()

@bot.event
async def on_ready():
    init_db()
    print(f"✅ Bot AI đã kết nối thành công với Discord dưới tên: {bot.user.name} (ID: {bot.user.id})")
    print(f"🤖 Kênh thông báo được theo dõi: {ANNOUNCEMENT_CHANNEL_IDS or 'Chưa cấu hình ID (lắng nghe toàn bộ kênh)'}")

# 1. TỰ ĐỘNG ĐỒNG BỘ THÔNG BÁO MỚI TỪ GIẢNG VIÊN VÀO SQLITE DB
@bot.event
async def on_message(message):
    # Tránh bot tự đọc tin nhắn của chính mình
    if message.author == bot.user:
        return

    # Nếu giảng viên đăng thông báo ở kênh được cấu hình (hoặc tất cả kênh nếu chưa lọc)
    is_announcement = (not ANNOUNCEMENT_CHANNEL_IDS) or (message.channel.id in ANNOUNCEMENT_CHANNEL_IDS)
    
    if is_announcement and not message.author.bot:
        print(f"📥 Phát hiện thông báo từ {message.author.name} tại #{message.channel.name}")
        conn = sqlite3.connect("schedules.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO official_schedules (id, title, start_time, end_time, is_mandatory, category, host, location, source_msg_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"msg_{message.id}",
            message.content[:60] + "...",
            "2026-08-01T09:00:00",
            "2026-08-01T11:00:00",
            1,
            "ANNOUNCEMENT",
            message.author.name,
            f"#{message.channel.name}",
            str(message.id),
            str(message.created_at)
        ))
        conn.commit()
        conn.close()

    # 2. XỬ LÝ CÂU HỎI KHI HỌC VIÊN MENTION @BOT HOẶC CHAT TRONG KÊNH AI
    if bot.user.mentioned_in(message) or message.channel.name == "tro-ly-lich-trinh":
        async with message.channel.typing():
            user_query = message.content.replace(f'<@{bot.user.id}>', '').strip()
            print(f"❓ Học viên hỏi: {user_query}")
            
            # Gọi ReAct Agent xử lý
            res = agent.process_request(user_query)
            
            # Trả lời lại học viên trên Discord
            embed = discord.Embed(
                title="🗓️ Trợ Lý AI Lập Kế Hoạch Lịch Trình",
                description=f"Trả lời cho câu hỏi: *\"{user_query}\"*\n\n{res.get('message')}",
                color=0x5865F2
            )
            embed.set_footer(text="Trích xuất tự động từ DB Discord")
            await message.channel.send(embed=embed)

    await bot.process_commands(message)

# 3. LẮNG NGHE KHI GIẢNG VIÊN EDIT TIN NHẮN ĐỂ CẬP NHẬT DB
@bot.event
async def on_message_edit(before, after):
    is_announcement = (not ANNOUNCEMENT_CHANNEL_IDS) or (after.channel.id in ANNOUNCEMENT_CHANNEL_IDS)
    if is_announcement and not after.author.bot:
        print(f"✏️ Giảng viên vừa chỉnh sửa bài đăng #{after.id} tại #{after.channel.name}")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("❌ LỖI: Chưa tìm thấy DISCORD_BOT_TOKEN!")
        print("👉 Vui lòng tạo file .env tại folder codebase/ và điền: DISCORD_BOT_TOKEN=Mật_Mã_Bot_Của_Bạn")
    else:
        bot.run(DISCORD_BOT_TOKEN)
