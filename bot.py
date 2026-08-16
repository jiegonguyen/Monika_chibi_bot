import os
import random
import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# --- CẤU HÌNH TOKEN AN TOÀN (TỰ ĐỘNG DỰ PHÒNG) ---
# 1. Thử lấy từ Environment Variables trên Render
DISCORD_TOKEN = (
    os.getenv("DISCORD_BOT_TOKEN") 
    or os.getenv("DISCORD_TOKEN") 
    or os.getenv("BOT_TOKEN") 
    or os.getenv("TOKEN")
)

# 2. [TẠM THỜI] Nếu trên Render chưa nhận, cậu có thể dán thẳng token vào trong dấu ngoặc kép bên dưới để test ngay:
FALLBACK_TOKEN = "" # Dán token của cậu vào đây nếu cần thiết, ví dụ: "MTM..."

# Ưu tiên lấy token từ Render, nếu không có thì lấy token dự phòng bên trên
ACTIVE_TOKEN = DISCORD_TOKEN if DISCORD_TOKEN and DISCORD_TOKEN.strip() else FALLBACK_TOKEN

if not ACTIVE_TOKEN or not ACTIVE_TOKEN.strip():
    raise ValueError("LỖI: Chưa có Token! Hãy cấu hình trên Render hoặc điền vào biến FALLBACK_TOKEN.")

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot-discord")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

# Database giả lập điểm số & level
user_data = {}
def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {"points": 0, "level": 1, "inventory": []}
    return user_data[user_id]

guild_queues = {}
active_listeners = {}

YTDL_OPTS = {"format": "bestaudio/best", "quiet": True, "no_warnings": True, "default_search": "auto", "skip_download": True}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)
FFMPEG_OPTIONS = {"options": "-vn -nostdin", "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"}

@bot.event
async def on_ready():
    await tree.sync()
    log.info(f"Bot đã khởi chạy thành công: {bot.user}")

# --- CÁC LỆNH CƠ BẢN ---
@tree.command(name="profile", description="Xem điểm văn học và cấp độ của bạn")
async def profile(interaction: discord.Interaction):
    data = get_user(interaction.user.id)
    embed = discord.Embed(title=f"Hồ sơ của {interaction.user.name}", color=discord.Color.green())
    embed.add_field(name="📖 Điểm Văn học", value=str(data["points"]), inline=True)
    embed.add_field(name="⭐ Cấp độ (Level)", value=str(data["level"]), inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="stop", description="Dừng nhạc và rời khỏi kênh thoại")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in active_listeners:
        active_listeners[guild_id].cancel()
    
    if interaction.guild.voice_client:
        guild_queues[guild_id] = []
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Đã dừng nhạc và rời khỏi phòng.")
    else:
        await interaction.response.send_message("Bot có đang ở trong kênh thoại đâu.", ephemeral=True)

# Khởi chạy bot bằng token đã chọn
bot.run(ACTIVE_TOKEN)
