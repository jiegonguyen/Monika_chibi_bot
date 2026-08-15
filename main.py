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

# 2. Cấu hình Discord Bot Intents (Tắt help mặc định để dùng bảng help tự chế trực quan hơn)
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Lấy API Key từ biến môi trường
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# 3. Hệ thống lưu trữ dữ liệu giả lập (Điểm văn học và Level riêng biệt)
user_profiles = {}

def get_user_profile(user_id):
    if user_id not in user_profiles:
        user_profiles[user_id] = {"literature_points": 0, "level": 1}
    return user_profiles[user_id]

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Monika đã sẵn sàng kết nối trực tiếp với thế giới của cậu rồi! 💚')

# --- BẢNG TRỢ GIÚP (HELP) RÕ RÀNG, TRỰC QUAN ---
@bot.command(name='help', help='Hiển thị danh sách các lệnh của Monika.')
async def custom_help(ctx):
    help_text = (
        "✨ **DANH SÁCH LỆNH CỦA MONIKA** ✨\n\n"
        "💬 **Trò chuyện với AI:**\n"
        f"• Nhắc tên tớ (`@{bot.user.name}`) kèm theo nội dung để trò chuyện trực tiếp cùng tớ nhé! 💚\n\n"
        "🎮 **Minigame & Giải trí:**\n"
        "• `!deptrai` - Kiểm tra độ đẹp trai ngẫu nhiên của cậu hôm nay 😎\n"
        "• `!roll` - Tung xúc xắc ngẫu nhiên từ 1 đến 6 🎲\n"
        "• `!guess [số]` - Chơi đoán số may mắn từ 1 đến 10 🎯\n"
        "• `!dominh` - Thử thách trò chơi dò mìn kích thích trí tuệ 💣\n"
        "• `!trieuhoi` - Triệu hồi ngẫu nhiên thành viên Câu lạc bộ Văn học 🌸\n"
        "• `!hopqua` - Mở hộp quà bí ẩn nhận phần thưởng bất ngờ 🎁\n\n"
        "📜 **Hệ thống Văn học & Level:**\n"
        "• `!gheptho` - Sáng tác/ghép thơ nhận Điểm Văn Học và thăng cấp Level ✨\n"
        "• `!hoso` - Kiểm tra Điểm Văn Học và Level hiện tại của cậu 📊\n\n"
        "📌 *Cậu cần giúp gì cứ gọi tớ nha!* 💚"
    )
    await ctx.send(help_text)

# --- CÁC LỆNH MINIGAME & VUI NHỘN ---
@bot.command(name='deptrai', help='Kiểm tra độ đẹp trai của cậu hôm nay.')
async def deptrai(ctx):
    percent = random.randint(50, 100)
    await ctx.send(f"😎 Hì hì, độ đẹp trai của **{ctx.author.display_name}** hôm nay đo được là **{percent}%** nè! Quá đỉnh luôn đúng không? ✨")

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

@bot.command(name='dominh', help='Chơi dò mìn thu nhỏ.')
async def dominh(ctx):
    grid = ["🟩", "🟩", "💣", "🟩", "💎"]
    random.shuffle(grid)
    result = "".join(grid)
    if "💎" in result and result.index("💎") < result.index("💣"):
        await ctx.send(f"💣 **{ctx.author.display_name}** dò mìn nè: {result}\n🎉 Chúc mừng cậu đã tìm thấy viên kim cương mà không vướng phải mìn! 💎✨")
    else:
        await ctx.send(f"💣 **{ctx.author.display_name}** dò mìn nè: {result}\n💥 Ối, dẫm phải mìn mất rồi! Cẩn thận hơn vào lần sau nhé cậu ơi! 🙈")

@bot.command(name='trieuhoi', help='Triệu hồi thành viên câu lạc bộ văn học.')
async def trieuhoi(ctx):
    members = [
        ("Sayori", "cô ấy chạy đến với chiếc nơ đỏ trên đầu và nở một nụ cười rạng rỡ buổi sáng! ☀️"),
        ("Natsuki", "đang cầm trên tay chiếc bánh quy hình miểng mèo và phồng má hờn dỗi! 🧁"),
        ("Yuri", "đang ôm một cuốn tiểu thuyết dày cộm, mỉm cười nhẹ nhàng và pha một tách trà nóng cho cậu. ☕"),
        ("Monika", "đang ngồi bên chiếc đàn piano trong phòng câu lạc bộ, quay đầu lại nhìn cậu và mỉm cười ngọt ngào! 💚🎹")
    ]
    name, desc = random.choice(members)
    await ctx.send(f"🌸 **{ctx.author.display_name}** vừa triệu hồi thành công **{name}**!\n-> {desc}")

@bot.command(name='hopqua', help='Mở hộp quà bí ẩn.')
async def hopqua(ctx):
    gifts = [
        "nhận được một chiếc bút máy cổ điển dùng để viết thơ cùng Monika! ✒️",
        "nhận được một hộp bánh cupcake dâu tây ngọt ngào từ Natsuki! 🧁",
        "nhận được một túi trà hoa oải hương thư giãn từ Yuri! 🫖",
        "nhận được một lời nhắn viết tay cực kỳ dễ thương từ Sayori! 💌",
        "nhận được quyền đặc biệt trò chuyện riêng với Monika trong không gian ảo! 💚✨"
    ]
    gift = random.choice(gifts)
    await ctx.send(f"🎁 **{ctx.author.display_name}** mở hộp quà bí ẩn và bất ngờ {gift}")

# --- HỆ THỐNG GHÉP THƠ, ĐIỂM VĂN HỌC & LEVEL (RIÊNG BIỆT) ---
@bot.command(name='gheptho', help='Ghép thơ để tích lũy điểm văn học và thăng cấp level.')
async def gheptho(ctx):
    user_id = ctx.author.id
    profile = get_user_profile(user_id)
    
    earned_points = random.randint(15, 35)
    profile["literature_points"] += earned_points
    
    calculated_level = (profile["literature_points"] // 100) + 1
    leveled_up = calculated_level > profile["level"]
    profile["level"] = calculated_level
    
    poems = [
        "Ánh nắng vàng xuyên qua khung cửa sổ...\nChiếc bút trên tay viết hộ bóng hình ai. ✨",
        "Phòng câu lạc bộ chiều nay lộng gió...\nCó một người luôn ngóng đợi cậu hoài. 💚",
        "Trang sách mở ra bao điều kỳ diệu...\nTựa như tình yêu dịu ngọt thủa ban đầu. 🌸",
        "Từng dòng code hay những vần thơ cũ...\nCũng chỉ vì muốn nhắn gửi đến cậu thôi. 💻"
    ]
    poem_chosen = random.choice(poems)
    
    msg = (
        f"📜 **SÁNG TÁC THƠ CÙNG MONIKA**\n"
        f"*{poem_chosen}*\n\n"
        f"🌟 **{ctx.author.display_name}** nhận được **{earned_points} Điểm Văn Học**!\n"
        f"📊 Tổng Điểm Văn Học: `{profile['literature_points']}` | Level hiện tại: `Level {profile['level']}`"
    )
    
    if leveled_up:
        msg += f"\n🎉 **Chúc mừng! Cậu đã thăng lên Level {profile['level']} nhờ sự chăm chỉ văn chương!** 🏆"
        
    await ctx.send(msg)

@bot.command(name='hoso', help='Xem điểm văn học và level của cậu.')
async def hoso(ctx):
    profile = get_user_profile(ctx.author.id)
    await ctx.send(
        f"📊 **HỒ SƠ VĂN HỌC CỦA {ctx.author.display_name.upper()}** 📊\n"
        f"• Điểm Văn Học: `{profile['literature_points']} điểm` 📜\n"
        f"• Level Hiện Tại: `Level {profile['level']}` 🏆\n"
        f"*(Mẹo: Dùng lệnh `!gheptho` thường xuyên để kiếm thêm điểm và thăng cấp nhé!)* 💚"
    )

# --- HÀM GỌI GEMINI HTTP ---
def ask_gemini(prompt_text):
    if not GOOGLE_API_KEY:
        return "⚠️ E hèm... Cậu chưa thiết lập Google API Key trên Render kìa! 💚"
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
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
