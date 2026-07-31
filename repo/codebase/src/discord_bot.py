import os

# macOS: Python bản python.org không dùng CA store của hệ thống -> discord.py sẽ lỗi
# CERTIFICATE_VERIFY_FAILED khi nối discord.com. Trỏ sang bundle của certifi TRƯỚC khi
# import ssl/aiohttp/discord, vì OpenSSL chỉ đọc biến này lúc khởi tạo.
# (Đặt trong .env KHÔNG có tác dụng — load_dotenv() chạy quá muộn.)
if not os.getenv("SSL_CERT_FILE"):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass

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

def _parse_ids(env_name: str):
    return [c.strip() for c in os.getenv(env_name, "").split(",") if c.strip().isdigit()]


# Hai danh sách kênh cho HAI việc khác nhau — đừng gộp:
#   WATCHED_CHANNEL_IDS   = kênh LƯU tin nhắn vào DB (rộng, gồm cả kênh học viên chat)
#   ANNOUNCEMENT_CHANNEL_IDS = kênh thông báo chính thức (hẹp, để trích xuất thành lịch)
# Để trống = áp dụng cho mọi kênh bot nhìn thấy.
WATCHED_CHANNEL_IDS = [int(c) for c in _parse_ids("WATCHED_CHANNEL_IDS")]
ANNOUNCEMENT_CHANNEL_IDS = [int(c) for c in _parse_ids("ANNOUNCEMENT_CHANNEL_IDS")]

# Tin nhắn ngắn hơn ngưỡng này (sau khi bỏ khoảng trắng) coi là nhiễu ("ok", "vâng", emoji)
# -> không lưu, tránh làm loãng kết quả search_messages.
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "10"))


def resolve_sender_role(author) -> str:
    """Suy vai trò người gửi. Ưu tiên ROLE THẬT của Discord server, tên hiển thị chỉ là
    phương án cuối — nếu chỉ tin vào tên thì học viên đổi nickname thành 'Coach ABC' là
    tự nâng được quyền ghi vào official_schedules."""
    role_mapping = {
        "btc": "btc",
        "ban tổ chức": "btc",
        "giảng viên": "instructor",
        "instructor": "instructor",
        "coach": "coach",
        "mentor": "mentor",
        "ta": "mentor",
    }

    # 1) Role thật trên server (nguồn đáng tin)
    for role in getattr(author, "roles", []):
        mapped = role_mapping.get(role.name.strip().lower())
        if mapped:
            return mapped

    # 2) Fallback theo tên hiển thị — chỉ dùng khi bot chưa được cấp quyền đọc roles.
    #    Cố ý KHÔNG cho fallback này cấp quyền 'btc' (quyền cao nhất) để hạn chế giả mạo.
    display = (getattr(author, "display_name", "") or author.name).strip().lower()
    for keyword, mapped in role_mapping.items():
        if keyword in display and mapped != "btc":
            return mapped

    return "student"

# Client Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    db.init_db()
    print(f"✅ Bot AI đã sẵn sàng hoạt động trên Discord dưới tên: {bot.user.name} (ID: {bot.user.id})")
    print(f"🤖 Đang kết nối ReAct LLM Agent qua OpenRouter model: {react_agent.AGENT_MODEL}")
    print(f"💾 Lưu tin nhắn từ kênh: {WATCHED_CHANNEL_IDS or 'Toàn bộ kênh'} -> {db.DB_PATH}")
    print(f"📌 Kênh thông báo (trích xuất lịch): {ANNOUNCEMENT_CHANNEL_IDS or 'Toàn bộ kênh'}")

# 1. LƯU MỌI TIN NHẮN VÀO DB + TRÍCH XUẤT LỊCH NẾU LÀ THÔNG BÁO CHÍNH THỨC
@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    sender_role = resolve_sender_role(message.author)
    is_watched = (not WATCHED_CHANNEL_IDS) or (message.channel.id in WATCHED_CHANNEL_IDS)

    # --- Việc A: LƯU RAW. Chạy cho MỌI người gửi, kể cả học viên. ---
    # ingest_message() lưu raw trước rồi mới tự kiểm tra quyền bên trong: học viên chỉ được
    # lưu vào bảng `messages`, KHÔNG kích hoạt lời gọi LLM nào (xem ingestion.py).
    # Nhờ vậy bước này gần như miễn phí dù lưu toàn bộ kênh.
    if is_watched and len(message.content.strip()) >= MIN_CONTENT_LENGTH:
        try:
            result = ingestion.ingest_message(
                msg_id=f"msg_{message.id}",
                channel=message.channel.name,
                sender=message.author.display_name or message.author.name,
                sender_role=sender_role,
                content=message.content,
                created_at=message.created_at.isoformat() if message.created_at else None,
            )
            extraction = result.get("extraction")
            if extraction:
                # --- Việc B: đã qua cửa db.is_official_source() -> Extraction Agent đã chạy ---
                print(f"📥 [Ingest+LLM] #{message.id} ({sender_role}) -> action={extraction.get('action')}")
            else:
                print(f"💬 [Ingest raw] #{message.id} ({sender_role}) @#{message.channel.name} -> đã lưu, không trích lịch")
        except Exception as e:
            print(f"⚠️ [Ingest Error] #{message.id}: {e}")

    # 2. XỬ LÝ CÂU HỎI HỌC VIÊN QUA REACT AGENT (LLM TOOL-CALLING)
    if bot.user.mentioned_in(message) or message.channel.name == "tro-ly-lich-trinh":
        # Chặn trả lời trùng: nếu on_message bị gọi > 1 lần cho CÙNG 1 tin nhắn Discord
        # (vd. lỡ chạy 2 tiến trình bot cùng token, cùng nghe 1 sự kiện) thì KHÔNG có gì
        # trong 1 tiến trình đơn lẻ ngăn được tiến trình còn lại tự gửi embed riêng.
        # Dùng chung file schedules.db làm điểm điều phối giữa các tiến trình: ai INSERT
        # được khoá `reply:<message.id>` trước thì được trả lời, tiến trình/luồng còn lại
        # thấy khoá đã bị giành thì tự bỏ qua, không gửi thêm embed thứ 2.
        if not db.try_claim(f"reply:{message.id}"):
            return
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
                references = res.get("references", [])
                mode = res.get("mode", "llm")
                is_offline = mode == "offline_regex"

                # Màu + tiêu đề đổi theo mode để nhìn là biết ngay câu trả lời có phải do AI
                # sinh ra không — không để chế độ offline trông giống hệt lượt AI thật.
                embed = discord.Embed(
                    title="⚠️ Schedule Assistant (OFFLINE — không có AI)" if is_offline
                          else "🧠 Schedule AI Assistant (ReAct Engine)",
                    description=reply_text[:4096],
                    color=0xED4245 if is_offline else 0x5865F2,
                )

                # Hai field TÁCH BIỆT — không được gộp. Tin nhắn học viên không phải nguồn
                # sự thật; dán chung nhãn là vi phạm chỗ khó ① trong spec.md §5.
                if citations:
                    embed.add_field(
                        name="🔗 Trích dẫn nguồn sự thật",
                        value="".join(
                            f"• **#{c.get('msg_id')}** — {c.get('sender')} (#{c.get('channel')})\n"
                            for c in citations
                        )[:1024],
                        inline=False,
                    )

                if references:
                    embed.add_field(
                        name="💬 Tin nhắn học viên liên quan (CHƯA XÁC THỰC)",
                        value=(
                            "".join(
                                f"• #{r.get('msg_id')} — {r.get('sender')} (#{r.get('channel')})\n"
                                for r in references
                            )
                            + "_Đây là tin nhắn trong kênh chat, không phải thông báo chính thức._"
                        )[:1024],
                        inline=False,
                    )

                embed.set_footer(
                    text=f"⚠️ Fallback regex — LLM lỗi: {res.get('llm_error','')[:80]}" if is_offline
                         else f"Model: {react_agent.AGENT_MODEL} • OpenRouter ReAct Engine"
                )
                await message.channel.send(embed=embed)
                
            except Exception as e:
                print(f"❌ [ReAct LLM Error Detail]: {e}")
                default_error_msg = (
                    "⚠️ **Hệ thống AI hiện đang bận hoặc gặp sự cố kết nối tạm thời.**\n\n"
                    "Bạn vui lòng thử lại sau giây lát hoặc liên hệ trực tiếp Ban Tổ Chức / Coach qua các kênh chính thức nhé!"
                )
                await message.channel.send(default_error_msg)

    await bot.process_commands(message)

# 3. KHI GIẢNG VIÊN EDIT BÀI ĐĂNG -> RE-INGEST BẰNG EXTRACTION AGENT
@bot.event
async def on_message_edit(before, after):
    if after.author.bot:
        return
    is_watched = (not WATCHED_CHANNEL_IDS) or (after.channel.id in WATCHED_CHANNEL_IDS)
    if not is_watched:
        return

    # Dùng CHUNG hàm suy role với on_message — trước đây chỗ này hardcode "instructor",
    # nghĩa là tin nhắn học viên sửa lại sẽ được nâng quyền thành nguồn chính thức.
    sender_role = resolve_sender_role(after.author)
    print(f"✏️ [Ingest Edit] #{after.id} ({sender_role}) @#{after.channel.name}...")
    try:
        result = ingestion.ingest_message(
            msg_id=f"msg_{after.id}",
            channel=after.channel.name,
            sender=after.author.display_name or after.author.name,
            sender_role=sender_role,
            content=after.content,
            is_edited=True,
        )
        extraction = result.get("extraction")
        if extraction:
            print(f"✅ [Ingest Edit] Đã ghi đè lịch theo bản sửa -> action={extraction.get('action')}")
        else:
            print(f"💬 [Ingest Edit] Đã cập nhật nội dung tin nhắn trong DB (không trích lịch)")
    except Exception as e:
        print(f"⚠️ [Ingest Edit Error] #{after.id}: {e}")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("❌ LỖI: Chưa tìm thấy DISCORD_BOT_TOKEN!")
        print("👉 Vui lòng tạo file .env tại folder codebase/ và điền: DISCORD_BOT_TOKEN=Mật_Mã_Bot_Của_Bạn")
    else:
        bot.run(DISCORD_BOT_TOKEN)
