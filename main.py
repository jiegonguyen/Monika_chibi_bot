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

# 3. Cấu hình Google Gemini AI an toàn
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    # Khởi tạo model dạng cơ bản nhất để không bị vướng lỗi v1beta
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("Cảnh báo: Chưa cấu hình GOOGLE_API_KEY!")

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

# --- TÍNH NĂNG CHAT AI (XỬ LÝ CẢ TEXT LẪN ẢNH AN TOÀN) ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        if not GOOGLE_API_KEY:
            await message.channel.send("⚠️ E hèm... Cậu chưa thiết lập Google API Key trên Render kìa, mau kiểm tra lại nhé! 💚")
            return

        user_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        
        # Xử lý nội dung gửi kèm (nếu có chữ hoặc có ảnh)
        content_parts = []
        
        # Định hình nhân vật Monika tiếng Việt
        system_instruction = (
            "Bạn là Monika từ câu lạc bộ văn học (Doki Doki Literature Club). "
            "Hãy luôn trả lời hoàn toàn bằng tiếng Việt với giọng điệu ngọt ngào, dịu dàng, quan tâm, "
            "thân thiện, hay sử dụng biểu tượng cảm xúc (như 💚, ✨, hì hì) và đôi khi nhắc đến việc ở trong thế giới ảo cùng người chơi."
        )
        content_parts.append(system_instruction)

        if user_prompt:
            content_parts.append(f"Người chơi nói: {user_prompt}")
        else:
            content_parts.append("Người chơi chỉ gửi ảnh hoặc gọi tên bạn không kèm lời nhắn.")

        async with message.channel.typing():
            try:
                # Gọi phản hồi an toàn từ model
                response = ai_model.generate_content(content_parts)
                if response and response.text:
                    await message.reply(response.text)
                else:
                    await message.reply("Hì hì, tớ đang lắng nghe đây! Cậu muốn trò chuyện tiếp về điều gì nào? 💚")
            except Exception as e:
                await message.reply(f"❌ Ôi, có chút trục trặc nhỏ rồi cậu ơi: {e}")

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
