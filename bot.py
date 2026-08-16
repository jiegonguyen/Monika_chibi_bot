import os
import random
import asyncio
import logging
import discord
from discord import app_codes if "app_codes" in globals() else discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# --- CẤU HÌNH TOKEN TỰ ĐỘNG (Quét mọi trường hợp trên Render) ---
DISCORD_TOKEN = (
    os.getenv("DISCORD_BOT_TOKEN") 
    or os.getenv("DISCORD_TOKEN") 
    or os.getenv("BOT_TOKEN") 
    or os.getenv("TOKEN")
)

if not DISCORD_TOKEN or not DISCORD_TOKEN.strip():
    raise ValueError(
        "LỖI: Chưa tìm thấy Token! Hãy chắc chắn trên Render mục Environment "
        "đã tạo một trong các tên: DISCORD_BOT_TOKEN, DISCORD_TOKEN, BOT_TOKEN hoặc TOKEN."
    )

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot-discord")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

# Cơ sở dữ liệu giả lập trong bộ nhớ
user_data = {}
def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {"points": 0, "level": 1, "inventory": []}
    return user_data[user_id]

guild_queues = {}
active_listeners = {}

YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "skip_download": True,
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)
FFMPEG_OPTIONS = {"options": "-vn -nostdin", "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"}

@bot.event
async def on_ready():
    await tree.sync()
    log.info(f"Bot đã sẵn sàng với tên: {bot.user}")

# --- 1. HỆ THỐNG ĐIỂM VĂN HỌC & LEVEL ---
@tree.command(name="profile", description="Xem điểm văn học và cấp độ của bạn")
async def profile(interaction: discord.Interaction):
    data = get_user(interaction.user.id)
    embed = discord.Embed(title=f"Hồ sơ của {interaction.user.name}", color=discord.Color.green())
    embed.add_field(name="📖 Điểm Văn học", value=str(data["points"]), inline=True)
    embed.add_field(name="⭐ Cấp độ (Level)", value=str(data["level"]), inline=True)
    embed.add_field(name="🎒 Số vật phẩm trong kho", value=str(len(data["inventory"])), inline=False)
    await interaction.response.send_message(embed=embed)

# --- 2. CỬA HÀNG & KHO ĐỒ ---
SHOP_ITEMS = {
    "sach_tho": {"name": "Tuyển tập Thơ ca", "price": 50, "desc": "Cuốn sách thơ tuyệt đẹp."},
    "but_than": {"name": "Bút máy cổ điển", "price": 100, "desc": "Cây bút mực hỗ trợ học tập."}
}

@tree.command(name="shop", description="Xem cửa hàng vật phẩm")
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 Cửa hàng Thơ ca", color=discord.Color.gold())
    for key, item in SHOP_ITEMS.items():
        gia_text = f"Giá: {item['price']} điểm\n{item['desc']}"
        embed.add_field(name=f"{item['name']} (Mã: {key})", value=gia_text, inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="buy", description="Mua vật phẩm từ cửa hàng")
@app_commands.describe(item_key="Mã vật phẩm muốn mua (sach_tho hoặc but_than)")
async def buy(interaction: discord.Interaction, item_key: str):
    if item_key not in SHOP_ITEMS:
        await interaction.response.send_message("Vật phẩm này không có trong cửa hàng!", ephemeral=True)
        return
    
    data = get_user(interaction.user.id)
    item = SHOP_ITEMS[item_key]
    
    if data["points"] < item["price"]:
        await interaction.response.send_message(f"Cậu chưa đủ điểm văn học! Cần {item['price']} điểm cơ.", ephemeral=True)
        return
    
    data["points"] -= item["price"]
    data["inventory"].append(item["name"])
    await interaction.response.send_message(f"💚 Đã mua thành công **{item['name']}**.")

@tree.command(name="inventory", description="Xem kho đồ cá nhân của bạn")
async def inventory(interaction: discord.Interaction):
    data = get_user(interaction.user.id)
    inv = data["inventory"]
    if not inv:
        await interaction.response.send_message("Kho đồ của cậu hiện đang trống trải quá...", ephemeral=True)
        return
    
    items_list = "\n".join([f"- {i}" for i in inv])
    embed = discord.Embed(title=f"🎒 Kho đồ của {interaction.user.name}", description=items_list, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# --- 3. MINIGAME (Đố vui văn học nhận điểm) ---
TRIVIA_QUESTIONS = [
    {"q": "Tác giả của tác phẩm 'Truyện Kiều' là ai?", "a": "nguyễn du"},
    {"q": "Nhà văn nào viết tiểu thuyết 'Số đỏ'?", "a": "vũ trọng phượng"},
    {"q": "Nhân vật Chí Phèo xuất hiện trong sáng tác của nhà văn nào?", "a": "nam cao"}
]

@tree.command(name="trivia", description="Thử thách đố vui văn học nhận điểm")
async def trivia(interaction: discord.Interaction):
    q_obj = random.choice(TRIVIA_QUESTIONS)
    await interaction.response.send_message(f"🧠 **Đố vui:** {q_obj['q']}\n*(Hãy nhắn đáp án của cậu trong vòng 15 giây nhé!)*")
    
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', timeout=15.0, check=check)
        if msg.content.lower().strip() == q_obj['a']:
            data = get_user(interaction.user.id)
            data["points"] += 20
            new_level = (data["points"] // 50) + 1
            if new_level > data["level"]:
                data["level"] = new_level
                await interaction.followup.send(f"Tuyệt vời! Nhận **20 điểm** và chúc mừng cậu lên **Level {new_level}**~ 💚")
            else:
                await interaction.followup.send(f"Chính xác! Thưởng cho cậu **20 điểm văn học**.")
        else:
            await interaction.followup.send(f"Tiếc quá, đáp án chính xác phải là: **{q_obj['a']}**.")
    except Exception:
        await interaction.followup.send("Hết thời gian suy nghĩ mất rồi...")

# --- 4. TÍNH NĂNG PHÁT NHẠC & CỘNG 10 ĐIỂM/PHÚT KHI NGHE ---
async def reward_listeners_loop(guild, guild_id):
    try:
        while True:
            await asyncio.sleep(60)
            vc = guild.voice_client
            if vc and vc.is_playing() and vc.channel:
                for member in vc.channel.members:
                    if not member.bot:
                        data = get_user(member.id)
                        data["points"] += 10
                        new_level = (data["points"] // 50) + 1
                        if new_level > data["level"]:
                            data["level"] = new_level
            else:
                break
    except asyncio.CancelledError:
        pass

@tree.command(name="play", description="Phát nhạc từ YouTube vào kênh thoại và nhận điểm")
@app_commands.describe(query="Tên bài hát hoặc đường dẫn YouTube")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        await interaction.response.send_message("Cậu phải vào kênh thoại trước đã chứ!", ephemeral=True)
        return

    await interaction.response.defer()
    voice_channel = interaction.user.voice.channel
    guild_id = interaction.guild.id

    if guild_id not in guild_queues:
        guild_queues[guild_id] = []

    if not interaction.guild.voice_client:
        try:
            await voice_channel.connect()
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        
        song = {'title': data.get('title'), 'url': data.get('url')}
        guild_queues[guild_id].append(song)
        
        vc = interaction.guild.voice_client
        if vc and not vc.is_playing():
            await play_next(interaction.guild, guild_id)
            if guild_id not in active_listeners or active_listeners[guild_id].done():
                active_listeners[guild_id] = bot.loop.create_task(reward_listeners_loop(interaction.guild, guild_id))
            
            await interaction.followup.send(f"🎧 Đang phát bài: **{song['title']}** (+10 điểm/phút nghe nhạc~)")
        else:
            await interaction.followup.send(f"🎵 Đã thêm vào hàng đợi: **{song['title']}**")
    except Exception as e:
        await interaction.followup.send(f"Không thể tải bài hát này: {e}")

async def play_next(guild, guild_id):
    if guild_id not in guild_queues or not guild_queues[guild_id]:
        if guild_id in active_listeners:
            active_listeners[guild_id].cancel()
        return
    song = guild_queues[guild_id].pop(0)
    vc = guild.voice_client
    if vc and vc.is_connected():
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS))
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, guild_id), bot.loop))

@tree.command(name="stop", description="Dừng nhạc và rời khỏi kênh thoại")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in active_listeners:
        active_listeners[guild_id].cancel()
    
    if interaction.guild.voice_client:
        guild_queues[guild_id] = []
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Đã dừng nhạc và rời khỏi phòng. Tạm biệt nhé~")
    else:
        await interaction.response.send_message("Bot có đang ở trong kênh thoại đâu.", ephemeral=True)

bot.run(DISCORD_TOKEN)
