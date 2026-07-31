import os
import asyncio

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


def _jump_url(guild, channel_name: str, msg_id: str):
    """Link nhảy thẳng tới đúng tin nhắn gốc trên Discord (bấm vào trích dẫn là nhảy tới
    #channel + đúng tin nhắn đó), dùng định dạng chuẩn của Discord:
    https://discord.com/channels/<guild_id>/<channel_id>/<message_id>

    Chỉ trả về link khi `msg_id` là ID Discord THẬT (số nguyên) — msg_id lưu trong DB có dạng
    "msg_<snowflake>". Data cũ/mẫu (vd. "msg_9801" từ seed_data.py) không phải snowflake thật,
    cố tạo link cho loại đó sẽ ra link chết -> trả None, chỗ gọi tự fallback về text thường.
    """
    if not guild or not msg_id:
        return None
    raw_id = msg_id.split("_", 1)[-1] if "_" in msg_id else msg_id
    if not raw_id.isdigit():
        return None
    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if not channel:
        return None
    return f"https://discord.com/channels/{guild.id}/{channel.id}/{raw_id}"


def _format_citation_line(guild, item: dict) -> str:
    """1 dòng trích dẫn trong embed — link hoá được thì link, không thì fallback text thường."""
    msg_id = item.get("msg_id", "")
    url = _jump_url(guild, item.get("channel"), msg_id)
    raw_id = str(msg_id).split("_", 1)[-1] if "_" in str(msg_id) else str(msg_id).lstrip("#")
    display_id = raw_id if raw_id.isdigit() else msg_id.lstrip("#")
    label = f"[#{display_id}]({url})" if url else f"**#{display_id}**"
    return f"• {label} — {item.get('sender')} (#{item.get('channel')})\n"


def _join_citation_lines(lines: list, limit: int = 1024) -> str:
    """Ghép các dòng trích dẫn lại, đảm bảo không rỗng và không quá 1024 ký tự."""
    if not lines:
        return "• _(Không có thông tin trích dẫn)_"
        
    out, used = [], 0
    for i, line in enumerate(lines):
        if used + len(line) > limit - 50:
            remaining = len(lines) - i
            out.append(f"\n_... và {remaining} nguồn khác_")
            break
        out.append(line)
        used += len(line)
        
    res = "".join(out).strip()
    if not res:
        res = "• _(Trích dẫn nguồn)_"
    return res[:1024]


def resolve_sender_role(author, guild=None) -> str:
    """Suy vai trò người gửi.
    - Mặc định là 'student'.
    - Nếu người dùng có Role trên Discord (khác @everyone), lấy vai trò theo tên Role đó trên Discord.
    """
    member = author
    if guild and hasattr(guild, "get_member") and not getattr(author, "roles", None):
        found = guild.get_member(author.id)
        if found:
            member = found

    roles = [r for r in getattr(member, "roles", []) if not getattr(r, "is_default", lambda: False)() and r.name != "@everyone"]
    if not roles:
        return "student"

    # Lấy theo tên Role thực tế trên Discord
    role_name = roles[0].name.strip().lower()
    if any(k in role_name for k in ("admin", "btc", "ban tổ chức", "quản trị", "host")):
        return "admin"
    if any(k in role_name for k in ("coach", "giảng viên", "instructor", "mentor", "ta", "trợ giảng")):
        return "coach"
    
    return role_name

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

# 1. TỰ ĐỘNG NẠP TIN NHẮN MỚI TỪ COACH/ADMIN VÀO DB REAL-TIME
@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    sender_role = resolve_sender_role(message.author, guild=message.guild)

    # Nếu là tin nhắn mới ở kênh thông báo chính thức và gửi bởi Coach/Admin -> Tự động lưu vào DB
    if db.is_official_source(sender_role, channel_id=message.channel.id, channel_name=message.channel.name):
        content = message.content.strip()
        if content:
            try:
                db.upsert_message(
                    msg_id=f"msg_{message.id}",
                    channel=message.channel.name,
                    sender=message.author.display_name or message.author.name,
                    sender_role=sender_role,
                    content=content,
                    created_at=message.created_at.isoformat() if message.created_at else db.now_iso(),
                )
                print(f"📥 [Realtime Ingest DB] Đã tự động thêm tin nhắn #{message.id} từ {sender_role.upper()} ({message.author.display_name}) ở #{message.channel.name} vào DB")
            except Exception as e:
                print(f"⚠️ [Realtime Ingest Error] #{message.id}: {e}")

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
            
            # Dùng giờ VN (UTC+7), KHÔNG dùng UTC trực tiếp: nếu để UTC, khung 17:00-23:59 UTC
            # (= 00:00-06:59 sáng hôm sau giờ VN) sẽ khiến "hôm nay" bị lùi mất 1 ngày so với
            # thực tế người dùng đang sống — vd. 00:30 giờ VN ngày 01/08 lại bị tính là 31/07.
            ref_date = db.vn_now().strftime("%Y-%m-%dT%H:%M:%S")
            try:
                # Gọi ReAct LLM Agent — cũng phải to_thread() vì lý do y hệt ở trên (blocking
                # HTTP call trong coroutine sẽ treo heartbeat Discord). Vòng ReAct này có thể
                # gọi OpenRouter NHIỀU lần (tối đa MAX_TURNS lượt tool-calling), càng dễ block
                # lâu hơn khối ingest ở trên -> càng bắt buộc phải chạy trong thread riêng.
                res = await asyncio.to_thread(
                    react_agent.ask,
                    user_query=user_query,
                    reference_date=ref_date,
                    user_label=message.author.name
                )
                
                reply_text = res.get("reply", "Không thể xử lý yêu cầu.")
                citations = res.get("citations", [])
                references = res.get("references", [])
                mode = res.get("mode", "llm")
                is_offline = mode == "offline_regex"

                # Log tool_trace ra console — không hiện cho học viên, chỉ để dev chẩn đoán khi
                # câu trả lời có vẻ sai (vd. agent quên gọi query_schedules mà chỉ dựa vào
                # search_messages). Không có log này thì rất khó biết agent đã "nghĩ" gì.
                trace = res.get("tool_trace", [])
                print(f"🔍 [Tool Trace] #{message.id} mode={mode} calls={len(trace)}")
                for t in trace:
                    print(f"    - {t.get('tool')}({t.get('args')}) -> {t.get('result_count')} kết quả")

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
                # Link hoá trích dẫn khi có thể — bấm vào #msg_id là nhảy thẳng tới tin nhắn gốc
                # trên Discord (xem _jump_url/_format_citation_line ở đầu file).
                if citations:
                    embed.add_field(
                        name="🔗 Trích dẫn nguồn sự thật",
                        value=_join_citation_lines(
                            [_format_citation_line(message.guild, c) for c in citations]
                        ),
                        inline=False,
                    )

                if references:
                    ref_lines = [_format_citation_line(message.guild, r) for r in references]
                    ref_lines.append("_Đây là tin nhắn trong kênh chat, không phải thông báo chính thức._")
                    embed.add_field(
                        name="💬 Tin nhắn học viên liên quan (CHƯA XÁC THỰC)",
                        value=_join_citation_lines(ref_lines),
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
        # to_thread(): xem ghi chú trong on_message() — tránh block event loop/heartbeat.
        result = await asyncio.to_thread(
            ingestion.ingest_message,
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

# 4. KHI GIẢNG VIÊN/COACH XÓA BÀI ĐĂNG -> TỰ ĐỘNG XÓA TIN NHẮN TRONG DB VÀ HỦY LỊCH LIÊN QUAN
@bot.event
async def on_raw_message_delete(payload):
    msg_id = f"msg_{payload.message_id}"
    print(f"🗑️ [Message Delete] Đã phát hiện tin nhắn #{payload.message_id} bị xóa trên Discord...")
    try:
        res = await asyncio.to_thread(db.delete_message, msg_id)
        deleted_count = res.get("deleted_count", 0)
        canceled_ids = res.get("canceled_schedules", [])
        if canceled_ids:
            print(f"✅ [Message Delete] Đã xóa tin nhắn #{payload.message_id} khỏi DB ({deleted_count} tin) và tự động hủy {len(canceled_ids)} lịch: {canceled_ids}")
        elif deleted_count > 0:
            print(f"✅ [Message Delete] Đã xóa tin nhắn #{payload.message_id} khỏi CSDL bảng messages (không có lịch active).")
        else:
            print(f"ℹ️ [Message Delete] Tin nhắn #{payload.message_id} không tìm thấy trong DB.")
    except Exception as e:
        print(f"⚠️ [Message Delete Error] #{payload.message_id}: {e}")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("❌ LỖI: Chưa tìm thấy DISCORD_BOT_TOKEN!")
        print("👉 Vui lòng tạo file .env tại folder codebase/ và điền: DISCORD_BOT_TOKEN=Mật_Mã_Bot_Của_Bạn")
    else:
        bot.run(DISCORD_BOT_TOKEN)
