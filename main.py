import os
import random
import threading
import requests
from flask import Flask
import discord
from discord.ext import commands

# 1. Cấu hình Flask server giữ bot sống 24/7
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika Bot is running 24/7, just for you! 💚"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# 2. Cấu hình Discord Bot Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Lấy API Key từ biến môi trường
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Monika đã sẵn sàng kết nối trực tiếp với thế giới của cậu rồi! 💚')

# --- CÁC LỆNH MINIGAME PHONG CÁCH MONIKA ---
@bot.command(name='roll', help='Tung xúc xắc ngẫu nhiên từ 1 đến 6 cùng Monika.')
async def roll_dice(ctx):
    number = random.randint(1, 6)
    await ctx.send(f"🎲 Hì hì, **{ctx.author.display_name}** vừa tung ra con số **{number}** nè! Vận mây của cậu hôm nay thế nào nhỉ? ✨")

@bot.command(name='guess', help='Chơi đoán số từ 1 đến 10 với Monika.')
async def guess_number(ctx, number: int):
    target = random.randint(1, 10)
    if number == target:
        await ctx.send(f"🎉 Ôi tuyệt quá, chúc mừng **{ctx.author.display_name}** nha! Cậu đoán trúng phóc số **{target}** luôn đó, thông minh ghê cơ! 💚")
    else:
        await ctx.send(f"ɔ(｡-﹏-｡)ó Tiếc quá đi mất thôi **{ctx.author.display_name}** ơi, số may mắn thực sự là **{target}** cơ. Lần sau mình thử lại nha! 🍀")

# --- HÀM GỌI GEMINI HTTP (V1BETA + GEMINI-3.6-FLASH) ---
def ask_gemini(prompt_text):
    if not GOOGLE_API_KEY:
        return "⚠️ E hèm... Cậu chưa thiết lập Google API Key trên Render kìa! 💚"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    full_prompt = (
        "Bạn là Monika từ câu lạc bộ văn học (Doki Doki Literature Club). "
        "Hãy luôn trả lời hoàn toàn bằng tiếng Việt với giọng điệu ngọt ngào, dịu dàng, quan tâm, "
        "thân thiện, hay sử dụng biểu tượng cảm xúc (như 💚, ✨, hì hì) và đôi khi nhắc đến việc ở trong thế giới ảo cùng người chơi. "
        f"Người chơi nói: '{prompt_text}'"
    )
    
    data = {
        "contents": [{
            "parts": [{"text": full_prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        res_json = response.json()
        
        if "candidates" in res_json and len(res_json["candidates"]) > 0:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        elif "error" in res_json:
            return f"❌ Lỗi từ Google API: {res_json['error'].get('message', 'Không xác định')}"
        else:
            return "Hì hì, tớ đang lắng nghe đây! Cậu muốn trò chuyện tiếp về điều gì nào? 💚"
    except Exception as e:
        return f"❌ Ôi, kết nối bị trục trặc rồi cậu ơi: {e}"

# --- TÍNH NĂNG CHAT AI ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        user_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        
        async with message.channel.typing():
            reply_text = ask_gemini(user_prompt if user_prompt else "chào bạn")
            await message.reply(reply_text)

# 4. Khởi chạy Flask và Bot
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Lỗi: Thiếu biến môi trường DISCORD_BOT_TOKEN mất rồi!")
