import os
import random
import threading
from flask import Flask
import discord
from discord.ext import commands
import google.generativeai as genai

# 1. Cấu hình Flask server để giữ bot sống 24/7 trên Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika Bot is running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# 2. Cấu hình Discord Bot Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 3. Cấu hình Google Gemini AI chuẩn chỉnh
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    ai_model = genai.GenerativeModel(model_name="gemini-1.5-flash")
else:
    print("Cảnh báo: Chưa cấu hình GOOGLE_API_KEY!")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Bot đã sẵn sàng kết nối và hoạt động!')

# --- CÁC LỆNH MINIGAME ---
@bot.command(name='roll', help='Tung một con xúc xắc ngẫu nhiên từ 1 đến 6.')
async def roll_dice(ctx):
    number = random.randint(1, 6)
    await ctx.send(f"🎲 Kết quả tung xúc xắc của **{ctx.author.display_name}** ra số: **{number}**!")

@bot.command(name='guess', help='Chơi đoán số từ 1 đến 10. (Ví dụ: !guess 5)')
async def guess_number(ctx, number: int):
    target = random.randint(1, 10)
    if number == target:
        await ctx.send(f"🎉 Chúc mừng **{ctx.author.display_name}**! Cậu đã đoán trúng số chính xác là **{target}**!")
    else:
        await ctx.send(f" tiếc quá **{ctx.author.display_name}** ơi, số may mắn là **{target}** cơ, cơ hội lần sau nhé!")

# --- TÍNH NĂNG CHAT VỚI AI GEMINI ---
@bot.event
async def on_message(message):
    # Tránh việc bot tự trả lời chính mình
    if message.author == bot.user:
        return

    # Xử lý các lệnh prefix (như !roll, !guess, !help)
    await bot.process_commands(message)

    # Nếu được tag tên, AI sẽ trả lời
    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        if not GOOGLE_API_KEY:
            await message.channel.send("⚠️ Chưa thiết lập Google API Key trên Render nên AI chưa thể trả lời.")
            return

        user_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not user_prompt:
            await message.channel.send("Cậu đang gọi tớ đấy à? Tớ nghe đây! 💚")
            return

        async with message.channel.typing():
            try:
                response = ai_model.generate_content(user_prompt)
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"❌ Đã xảy ra lỗi AI: {e}")

# 4. Khởi chạy Flask song song với Discord Bot
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Lỗi: Thiếu biến môi trường DISCORD_BOT_TOKEN trên Render!")
