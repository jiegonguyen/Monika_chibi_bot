import os
import random
import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# Cấu hình log
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("monika-bot")

# Lấy token an toàn từ biến môi trường của Render (Không đưa token cứng lên GitHub để tránh bị khóa)
ACTIVE_TOKEN = os.getenv("DISCORD_TOKEN")

if not ACTIVE_TOKEN:
    raise ValueError("LỖI: Chưa cấu hình DISCORD_TOKEN trong mục Environment trên Render!")

# --- BẢN VÁ INTENTS (Giúp bot sáng đèn online và hoạt động ở mọi server) ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.presences = True  # Bắt buộc để hiện trạng thái online
intents.members = True    # Nhận diện thành viên toàn server

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

# Database giả lập điểm văn học và level
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
    log.info(f"Monika đã khởi chạy thành công: {bot.user}")
    log.info(f"Đang hoạt động trên {len(bot.guilds)} máy chủ.")

# --- CÁC LỆNH TÍNH NĂNG ---

@tree.command(name="profile", description="Xem hồ sơ điểm văn học và cấp độ của bạn")
async def profile(interaction: discord.Interaction):
    data = get_user(interaction.user.id)
    embed = discord.Embed(title=f"Hồ sơ của {interaction.user.name}", color=discord.Color.magenta())
    embed.add_field(name="📖 Điểm Văn học", value=str(data["points"]), inline=True)
    embed.add_field(name="⭐ Cấp độ (Level)", value=str(data["level"]), inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="join", description="Monika tham gia kênh thoại của bạn")
async def join(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        await interaction.response.send_message(f"Monika đã vào kênh thoại: {channel.name} ~")
    else:
        await interaction.response.send_message("Cậu phải vào kênh thoại trước đã nhé!", ephemeral=True)

@tree.command(name="stop", description="Dừng nhạc và rời khỏi kênh thoại")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in active_listeners:
        active_listeners[guild_id].cancel()
    
    if interaction.guild.voice_client:
        guild_queues[guild_id] = []
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Monika đã dừng nhạc và rời phòng.")
    else:
        await interaction.response.send_message("Tớ có đang ở trong kênh thoại đâu.", ephemeral=True)

# Khởi chạy bot an toàn
bot.run(ACTIVE_TOKEN)
