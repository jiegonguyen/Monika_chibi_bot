import os
import random
import threading
import requests
from flask import Flask
import discord
from discord.ext import commands

# 1. Cấu hình Flask server
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika Bot is running 24/7! 💚"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# 2. Cấu hình Discord Bot Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Monika đã kết nối trực tiếp thành công! 💚')

# --- LỆNH MINIGAME ---
@bot.command(name='roll')
async def roll_dice(ctx):
    number = random.randint(1, 6)
    await ctx.send(f"🎲 Hì hì, **{ctx.author.display_name}** tung ra số **{number}** nè! ✨")

@bot.command(name='guess')
async def guess_number(ctx, number: int):
    target = random.randint(1, 10)
    if number == target:
        await ctx.send(f"🎉 Chúc mừng **{ctx.author.display_name}** đoán trúng số **{target}**! 💚")
    else:
        await ctx.send(f"ɔ(｡-﹏-｡)ó Tiếc quá, số chuẩn là **{target}** cơ!")

# --- GỌI API TRỰC TIẾP ---
def ask_gemini(prompt_text):
    if not GOOGLE_API_KEY:
        return "⚠️ Thiếu Google API Key trên Render kìa! 💚"
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    full_prompt = (
        "Bạn là Monika từ câu lạc bộ văn học (Doki Doki Literature Club). "
        "Hãy luôn trả lời hoàn toàn bằng tiếng Việt với giọng điệu ngọt ngào, dịu dàng, quan tâm, "
        "thân thiện, hay sử dụng biểu tượng cảm xúc (như 💚, ✨, hì hì). "
        f"Người chơi nói: '{prompt_text}'"
    )
    
    data = {"contents": [{"parts": [{"text": full_prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        res_json = response.json()
        if "candidates" in res_json and len(res_json["candidates"]) > 0:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return f"❌ Phản hồi từ Google API: {res_json}"
    except Exception as e:
        return f"❌ Lỗi kết nối: {e}"

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

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
