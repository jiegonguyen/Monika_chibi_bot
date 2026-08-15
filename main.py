import os
import discord
from discord.ext import commands
import google.generativeai as genai
from flask import Flask
from threading import Thread

# ==========================================
# 1. WEB SERVER GIẢ LẬP (GIỮ BOT ONLINE TRÊN RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Monika Chibi Bot is fully operational and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

flask_thread = Thread(target=run_flask)
flask_thread.start()

# ==========================================
# 2. CẤU HÌNH DISCORD BOT
# ==========================================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Khởi tạo bot với prefix '!' và tắt lệnh help mặc định để tự làm lệnh help riêng
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ==========================================
# 3. CẤU HÌNH GOOGLE GEMINI AI
# ==========================================
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)

# Cấu hình model Gemini
generation_config = {
    "temperature": 0.7,
    "max_output_tokens": 1000,
}
model = genai.GenerativeModel('gemini-pro', generation_config=generation_config)

# ==========================================
# 4. SỰ KIỆN KHI BOT SẴN SÀNG
# ==========================================
@bot.event
async def on_ready():
    print(f'----------------------------------------')
    print(f'🤖 Đã đăng nhập thành công với tên: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'🌐 Trạng thái Web Server: Đang chạy trên cổng 8080')
    print(f'----------------------------------------')
    await bot.change_presence(activity=discord.Game(name="Gõ !help để xem hướng dẫn"))

# ==========================================
# 5. CÁC LỆNH CỦA BOT (COMMANDS)
# ==========================================

# Lệnh Help (Trợ giúp)
@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="✨ Hướng dẫn sử dụng Monika Chibi Bot",
        description="Danh sách các lệnh và tính năng có sẵn:",
        color=discord.Color.pink()
    )
    embed.add_field(name="💬 Trò chuyện AI", value="Gõ `!monika [nội dung]` hoặc `!monika_boi [nội dung]`, hoặc tag trực tiếp bot để chat với Gemini.", inline=False)
    embed.add_field(name="♟️ Chơi cờ vua", value="Gõ `!chess` để bắt đầu ván cờ vua.", inline=False)
    embed.add_field(name="🎲 Các lệnh vui khác", value="`!tungcoin`, `!Moantuti`, `!MyMood`, `!deptri`", inline=False)
    embed.set_footer(text="Được vận hành trên Render & Google Gemini AI")
    
    await ctx.send(embed=embed)

# Lệnh Chơi cờ vua
@bot.command(name='chess')
async def chess_command(ctx):
    await ctx.send("♟️ **Bàn cờ vua đã sẵn sàng!** Tính năng đấu cờ chi tiết đang được phát triển nhé.")

# Lệnh Chat với Gemini (Hỗ trợ cả !monika lẫn !monika_boi)
@bot.command(name='monika', aliases=['monika_boi'])
async def monika_chat(ctx, *, prompt: str = None):
    if not prompt:
        await ctx.send("⚠️ Bạn chưa nhập nội dung cần hỏi Monika ơi! Ví dụ: `!monika Xin chào`")
        return
    
    async with ctx.channel.typing():
        try:
            response = model.generate_content(prompt)
            await ctx.send(response.text)
        except Exception as e:
            await ctx.send(f"❌ Ôi không, đã có lỗi xảy ra khi kết nối với Gemini: `{e}`")

# ==========================================
# 6. XỬ LÝ SỰ KIỆN TIN NHẮN (ON_MESSAGE)
# ==========================================
@bot.event
async def on_message(message):
    # Không phản hồi tin nhắn của chính bot
    if message.author == bot.user:
        return

    # Nếu người dùng tag (@mention) bot trực tiếp mà không dùng dấu chấm than
    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if clean_content:
            async with message.channel.typing():
                try:
                    response = model.generate_content(clean_content)
                    await message.reply(response.text)
                except Exception as e:
                    await message.reply(f"❌ Đã xảy ra lỗi: `{e}`")
        else:
            await message.reply("👋 Chào cậu! Cậu gọi tớ có việc gì không? Gõ `!help` để xem hướng dẫn nhé!")
        return

    # Quan trọng: Bắt buộc để nhận diện các lệnh dạng !command
    await bot.process_commands(message)

# ==========================================
# 7. CHẠY ỨNG DỤNG
# ==========================================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ LỖI: Chưa thiết lập DISCORD_TOKEN trong biến môi trường!")
    else:
        bot.run(DISCORD_TOKEN)
