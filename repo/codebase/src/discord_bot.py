import os
import discord
from discord.ext import commands
from datetime import datetime, timezone

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import db
import ingestion
import agent as react_agent

# --- CONFIGURATION FROM ENV ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

raw_channel_ids = os.getenv("ANNOUNCEMENT_CHANNEL_IDS", "")
ANNOUNCEMENT_CHANNEL_IDS = [
    int(cid.strip()) for cid in raw_channel_ids.split(",") if cid.strip().isdigit()
]

# Client Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    db.init_db()
    print(f"✅ Bot AI đã sẵn sàng hoạt động trên Discord dưới tên: {bot.user.name} (ID: {bot.user.id})")
    print(f"🤖 Đang kết nối ReAct LLM Agent qua OpenRouter model: {react_agent.AGENT_MODEL}")
    print(f"📌 Kênh thông báo theo dõi: {ANNOUNCEMENT_CHANNEL_IDS or 'Toàn bộ kênh'}")

# 1. TỰ ĐỘNG GỌI EXTRACTION AGENT (LLM) KHI CÓ THÔNG BÁO MỚI TỪ GIẢNG VIÊN
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Xác định vai trò người gửi
    role_mapping = {
        "BTC": "btc",
        "Giảng viên": "instructor",
        "Coach": "coach",
        "Mentor": "mentor",
    }
    sender_role = "student"
    for keyword, role in role_mapping.items():
        if keyword.lower() in message.author.name.lower() or any(role.name.lower() == keyword.lower() for role in getattr(message.author, "roles", [])):
            sender_role = role
            break

    is_announcement = (not ANNOUNCEMENT_CHANNEL_IDS) or (message.channel.id in ANNOUNCEMENT_CHANNEL_IDS)
    
    # Nếu là tin nhắn thông báo ở kênh giảng viên -> Chạy LLM Extraction Agent
    if is_announcement and not message.author.bot and sender_role != "student":
        print(f"📥 [LLM Ingestion] Bắt đầu trích xuất bài đăng #{message.id} từ {message.author.name}...")
        try:
            result = ingestion.ingest_message(
                msg_id=f"msg_{message.id}",
                channel=message.channel.name,
                sender=message.author.name,
                sender_role=sender_role,
                content=message.content,
                created_at=message.created_at.isoformat() if message.created_at else None,
            )
            action = (result.get("extraction") or {}).get("action", "unknown")
            print(f"✅ [LLM Ingestion Successful] Trích xuất hoàn tất! Hành động DB: {action}")
        except Exception as e:
            print(f"⚠️ [LLM Ingestion Error] Lỗi trích xuất thông báo: {e}")

    # 2. XỬ LÝ CÂU HỎI HỌC VIÊN QUA REACT AGENT (LLM TOOL-CALLING)
    if bot.user.mentioned_in(message) or message.channel.name == "tro-ly-lich-trinh":
        async with message.channel.typing():
            user_query = message.content.replace(f'<@{bot.user.id}>', '').strip()
            print(f"❓ [ReAct LLM Agent] Nhận câu hỏi học viên: \"{user_query}\"")
            
            ref_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            try:
                # Gọi ReAct LLM Agent
                res = react_agent.ask(
                    user_query=user_query,
                    reference_date=ref_date,
                    user_label=message.author.name
                )
                
                reply_text = res.get("reply", "Không thể xử lý yêu cầu.")
                citations = res.get("citations", [])

                # Tạo Embed chuyên nghiệp phản hồi Discord
                embed = discord.Embed(
                    title="🧠 Schedule AI Assistant (ReAct Engine)",
                    description=reply_text,
                    color=0x5865F2
                )
                
                if citations:
                    citation_text = ""
                    for c in citations:
                        citation_text += f"• **Source #{c.get('msg_id')}** ({c.get('sender')} - #{c.get('channel')})\n"
                    embed.add_field(name="🔗 Trích dẫn nguồn sự thật", value=citation_text, inline=False)
                    
                embed.set_footer(text=f"Model: {react_agent.AGENT_MODEL} • OpenRouter ReAct Engine")
                await message.channel.send(embed=embed)
                
            except Exception as e:
                print(f"❌ [ReAct LLM Error] Lỗi xử lý AI: {e}")
                await message.channel.send(f"⚠️ Không thể kết nối với LLM Model qua OpenRouter: {e}")

    await bot.process_commands(message)

# 3. KHI GIẢNG VIÊN EDIT BÀI ĐĂNG -> RE-INGEST BẰNG EXTRACTION AGENT
@bot.event
async def on_message_edit(before, after):
    is_announcement = (not ANNOUNCEMENT_CHANNEL_IDS) or (after.channel.id in ANNOUNCEMENT_CHANNEL_IDS)
    if is_announcement and not after.author.bot:
        print(f"✏️ [LLM Ingestion Edit] Cập nhật bài đăng #{after.id} từ {after.author.name}...")
        try:
            ingestion.ingest_message(
                msg_id=f"msg_{after.id}",
                channel=after.channel.name,
                sender=after.author.name,
                sender_role="instructor",
                content=after.content,
                is_edited=True,
            )
            print(f"✅ [LLM Ingestion Edit Successful] Đã ghi đè lịch bị edit trong DB!")
        except Exception as e:
            print(f"⚠️ [LLM Ingestion Edit Error]: {e}")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("❌ LỖI: Chưa tìm thấy DISCORD_BOT_TOKEN!")
        print("👉 Vui lòng tạo file .env tại folder codebase/ và điền: DISCORD_BOT_TOKEN=Mật_Mã_Bot_Của_Bạn")
    else:
        bot.run(DISCORD_BOT_TOKEN)
