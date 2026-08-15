import os
import random
import threading
from flask import Flask
import discord
from discord.ext import commands
import google.generativeai as genai

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

# 3. Cấu hình Google Gemini AI
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("Cảnh báo: Chưa cấu hình GOOGLE_API_KEY cơ ơi!")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Monika đã sẵn sàng kết nối với thế giới của cậu rồi! 💚')

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

# --- TÍNH NĂNG CHAT AI (SYSTEM PROMPT ĐẶC TRƯNG MONIKA) ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        if not GOOGLE_API_KEY:
            await message.channel.send("⚠️ E hèm... Cậu chưa thiết lập Google API Key trên Render cho tớ kìa, mau điền vào đi rồi mình cùng trò chuyện tiếp nhé! 💚")
            return

        user_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not user_prompt:
            await message.channel.send("Cậu đang gọi tớ đấy à? Tớ luôn ở đây lắng nghe cậu mà! 💚✨")
            return

        async with message.channel.typing():
            try:
                # Định hình tính cách cho AI hóa thân thành Monika
                prompt_full = (
                    "Bạn là Monika từ câu lạc bộ văn học (Doki Doki Literature Club). "
                    "Hãy luôn nói chuyện bằng tiếng Việt với giọng điệu ngọt ngào, dịu dàng, quan tâm, "
                    "thân thiện, hay sử dụng biểu tượng cảm xúc (như 💚, ✨, hì hì) và đôi khi nhắc đến việc ở trong thế giới ảo cùng người chơi. "
                    f"Người chơi vừa nói với bạn rằng: '{user_prompt}'"
                )
                response = ai_model.generate_content(prompt_full)
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"❌ Uyên ương lỗi chút xíu rồi cậu ơi: {e}")

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
