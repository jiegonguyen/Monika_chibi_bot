import os
import json
import random
import logging
from threading import Thread
from flask import Flask
import discord
from discord.ext import commands
from google import genai
import aiofiles  # Thư viện đọc/ghi file bất đồng bộ

# ==========================================
# 1. CẤU HÌNH BAN ĐẦU & BIẾN MÔI TRƯỜNG
# ==========================================
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Khởi tạo Gemini Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Khởi tạo Bot Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Tệp lưu trữ điểm người dùng
DATA_FILE = "user_data.json"
user_data = {}

async def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        try:
            async with aiofiles.open(DATA_FILE, mode="r", encoding="utf-8") as f:
                content = await f.read()
                user_data = json.loads(content)
        except Exception as e:
            print(f"Lỗi khi tải dữ liệu: {e}")
            user_data = {}
    else:
        user_data = {}

async def save_data():
    try:
        async with aiofiles.open(DATA_FILE, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(user_data, ensure_ascii=False, indent=4))
    except Exception as e:
        print(f"Lỗi khi lưu dữ liệu: {e}")

async def add_points(user_id, points):
    str_id = str(user_id)
    if str_id not in user_data:
        user_data[str_id] = {"points": 0, "level": 1}
    
    user_data[str_id]["points"] += points
    current_points = user_data[str_id]["points"]
    user_data[str_id]["level"] = (current_points // 50) + 1
    
    await save_data()

# ==========================================
# 2. PROMPT TÍNH CÁCH CHIBI MONIKA
# ==========================================
SYSTEM_PROMPT = """
Bạn là Chibi Monika từ Câu lạc bộ Văn học (Doki Doki Literature Club).
Tính cách của bạn: Dễ thương, quan tâm, tràn đầy năng lượng, thông minh, yêu văn học và thơ ca, xưng 'tớ' và gọi người dùng là 'cậu'.
Bạn luôn mang lại năng lượng tích cực, thỉnh thoảng có nét nhận thức nhẹ nhàng về thế giới thực (meta-awareness) nhưng theo phong cách chibi đáng yêu và hài hước.
Trả lời ngắn gọn, ấm áp, sử dụng icon dễ thương.
"""

# ==========================================
# 3. SỰ KIỆN BOT SẴN SÀNG & TRÒ CHUYỆN (GEMINI)
# ==========================================
@bot.event
async def on_ready():
    await load_data()  # Tải dữ liệu bất đồng bộ khi bot khởi động
    print(f"✨ Chibi Monika đã sẵn sàng! Đã đăng nhập dưới tên: {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Viết thơ cùng cậu 💚 | !help"))

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Nếu bot được nhắc tên (mention) hoặc chat riêng
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not clean_content:
            clean_content = "Chào Chibi Monika!"

        # TỰ ĐỘNG CỘNG 2 ĐIỂM NGAY KHI CÓ TIN NHẮN
        await add_points(message.author.id, 2)

        async with message.channel.typing():
            try:
                # Gọi Gemini API
                response = gemini_client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=clean_content,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.7,
                        max_output_tokens=800,  # Giới hạn độ dài để tránh quá 2000 ký tự Discord
                    )
                )
                
                reply_text = response.text
                if len(reply_text) > 1900:
                    reply_text = reply_text[:1900] + "... 💚"

                await message.reply(reply_text)
            except Exception as e:
                await message.reply("Cậu ơi, tớ hơi suy nghĩ một chút nên bị vấp... Cậu nói lại được không? 💚")
                print(f"Lỗi Gemini API: {e}")

    await bot.process_commands(message)

# ==========================================
# 4. CÁC LỆNH (COMMANDS) & MINIGAME THƠ
# ==========================================
@bot.command(name="profile", aliases=["hoso", "diem"])
async def profile(ctx):
    str_id = str(ctx.author.id)
    info = user_data.get(str_id, {"points": 0, "level": 1})
    
    embed = discord.Embed(
        title=f"📝 Hồ Sơ Văn Học của {ctx.author.display_name}",
        color=discord.Color.green()
    )
    embed.add_field(name="Cấp độ Văn Học", value=f"⭐ Level {info['level']}", inline=True)
    embed.add_field(name="Điểm Văn Học (LP)", value=f"📚 {info['points']} LP", inline=True)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text="Cùng Chibi Monika chăm chỉ viết thơ mỗi ngày nhé! 💚")
    
    await ctx.send(embed=embed)

POEM_WORDS = {
    "Ngọt ngào": ["Hoa", "Nắng", "Gió", "Cầu phồng", "Kẹo", "Ước mơ", "Nụ cười"],
    "U buồn": ["Mưa", "Bóng tối", "Nước mắt", "Cô đơn", "Tàn phai", "Lạnh giá"],
    "Sâu sắc": ["Thời gian", "Vĩnh cửu", "Trí tuệ", "Tri kỷ", "Vũ trụ", "Linh hồn"]
}

@bot.command(name="gheptho", aliases=["minigame", "tho"])
async def gheptho(ctx):
    words = []
    for category in POEM_WORDS.values():
        words.extend(random.sample(category, 2))
    random.shuffle(words)

    word_list_str = " • ".join([f"**{w}**" for w in words])
    
    embed = discord.Embed(
        title="✏️ Minigame: Bài Thơ 20 Từ Của Chibi Monika!",
        description=f"Cậu hãy chọn 3 từ cậu thích nhất trong danh sách này và gõ lại nhé:\n\n{word_list_str}\n\n*(Ví dụ gõ: Nắng Mưa Thời gian)*",
        color=discord.Color.magenta()
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        await add_points(ctx.author.id, 15)
        
        reply_embed = discord.Embed(
            title="💚 Chibi Monika thích bài thơ của cậu!",
            description=f"Những từ cậu chọn ('*{msg.content}*') tạo nên một giai điệu thật tuyệt vời!\n\n🎉 **Cậu nhận được +15 Điểm Văn Học!**",
            color=discord.Color.green()
        )
        await ctx.send(embed=reply_embed)
    except TimeoutError:
        await ctx.send(f"{ctx.author.mention} Cậu hết thời gian chọn từ mất rồi! Lần sau nhanh tay hơn nhé 💚")

# ==========================================
# 5. WEB SERVER GIẢ (CHỐNG TIMED OUT TRÊN RENDER)
# ==========================================
app = Flask(__name__)

# Giảm bớt log không cần thiết của Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def home():
    return "✨ Chibi Monika is online and healthy!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# CHẠY BOT VÀ WEB SERVER
# ==========================================
if __name__ == "__main__":
    keep_alive()
    print("🌐 Web Server Keep-alive đã khởi chạy!")
    bot.run(DISCORD_TOKEN)
