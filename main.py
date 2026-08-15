import os
import discord
from discord.ext import commands
import google.generativeai as genai
from flask import Flask
from threading import Thread
import asyncio

# --- 1. Cấu hình Flask Web Server (BẮT BUỘC ĐỂ BOT ONLINE TRÊN RENDER) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika Chibi Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

flask_thread = Thread(target=run_flask)
flask_thread.start()

# --- 2. Cấu hình Discord Bot ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 3. Cấu hình Google Gemini AI ---
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# --- 4. Sự kiện: Khi bot khởi động xong ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

# --- 5. Lệnh Help tùy chỉnh (Giúp hiển thị các lệnh của bot) ---
@bot.command(name='help')
async def custom_help(ctx):
    help_text = (
        "✨ **Xin chào! Mình là Monika Chibi đây. Dưới đây là các lệnh bạn có thể dùng:**\n\n"
        "💬 **Trò chuyện với AI:** Nhắc tên bot (@Monika) hoặc dùng lệnh `!monika [nội dung]` để chat với Gemini.\n"
        "♟️ **Chơi cờ vua:** Gõ `!chess` để bắt đầu ván cờ.\n"
        "ℹ️ **Trợ giúp:** Gõ `!help` để xem bảng hướng dẫn này bất cứ lúc nào!"
    )
    await ctx.send(help_text)

# --- 6. Lệnh: Bot phản hồi tin nhắn ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Kiểm tra nếu được mention hoặc dùng tiền tố !monika
    if bot.user.mentioned_in(message) or message.content.startswith('!monika '):
        user_message = message.content.replace(f'<@{bot.user.id}>', '').replace('!monika ', '').strip()
        
        if user_message:
            try:
                response = model.generate_content(user_message)
                await message.channel.send(response.text)
            except Exception as e:
                await message.channel.send(f"Xin lỗi, đã có lỗi xảy ra: {e}")
    
    await bot.process_commands(message)

# --- 7. Lệnh chơi cờ vua ---
@bot.command()
async def chess(ctx):
    await ctx.send("Tớ sẵn sàng rồi! Hãy bắt đầu ván cờ vua nào! (Bạn có thể phát triển thêm logic cờ vua ở đây nhé!)")

# --- 8. Chạy Bot ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
