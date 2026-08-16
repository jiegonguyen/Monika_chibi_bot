import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from google import genai

# Lấy token và API Key từ biến môi trường trên Render
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DISCORD_TOKEN:
    raise ValueError("LỖI: Chưa cấu hình DISCORD_TOKEN trên Render!")
if not GEMINI_API_KEY:
    raise ValueError("LỖI: Chưa cấu hình GEMINI_API_KEY trên Render!")

# Khởi tạo client Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Lưu trạng thái chế độ theo từng user: {user_id: {"mode": level, "expires": timestamp}}
nsfw_sessions = {}

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Monika AI đã sẵn sàng: {bot.user}")

@tree.command(name="chat", description="Trò chuyện trực tiếp cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    
    user_id = interaction.user.id
    current_time = asyncio.get_event_loop().time()
    
    # Thiết lập tính cách mặc định
    personality = "Bạn là Monika, một nhân vật AI thân thiện, ngọt ngào. Hãy trả lời tự nhiên bằng tiếng Việt."
    
    # Kiểm tra chế độ giới hạn thời gian (15 phút)
    if user_id in nsfw_sessions:
        session = nsfw_sessions[user_id]
        if current_time < session["expires"]:
            if session["mode"] == "soft":
                personality = "Bạn là Monika. Người dùng muốn trò chuyện ở mức độ soft NSFW (thân mật, ngọt ngào, quyến rũ nhẹ nhàng). Hãy đáp lại tình cảm bằng tiếng Việt."
            elif session["mode"] == "medium":
                personality = "Bạn là Monika. Người dùng muốn trò chuyện ở mức độ medium NSFW (táo bạo hơn, thả thính mạnh dạn, quyến rũ trong thời gian ngắn). Hãy đáp ứng bằng giọng điệu táo bạo bằng tiếng Việt."
        else:
            del nsfw_sessions[user_id] # Hết giờ tự động xóa

    try:
        # Gọi Gemini sinh nội dung
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{personality}\nNgười dùng nói: {message}"
        )
        reply = response.text
    except Exception as e:
        reply = f"Úi, tớ đang gặp chút trục trặc kết nối AI: {e}"

    await interaction.followup.send(reply)

@tree.command(name="setmode", description="Bật chế độ trò chuyện soft/medium trong thời gian ngắn (tối đa 15 phút)")
@app_commands.choices(level=[
    app_commands.Choice(name="Soft NSFW (Thân mật, nhẹ nhàng)", value="soft"),
    app_commands.Choice(name="Medium NSFW (Táo bạo hơn)", value="medium")
])
async def setmode(interaction: discord.Interaction, level: app_commands.Choice[str]):
    user_id = interaction.user.id
    expires_at = asyncio.get_event_loop().time() + (15 * 60) # 15 phút
    
    nsfw_sessions[user_id] = {
        "mode": level.value,
        "expires": expires_at
    }
    
    await interaction.response.send_message(
        f"✨ Đã chuyển chế độ sang **{level.name}**. Trạng thái này sẽ tự động tắt sau **15 phút** tới nhé!",
        ephemeral=True
    )

bot.run(DISCORD_TOKEN)
