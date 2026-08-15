import os
import time
import json
import discord
from discord.ext import commands
import requests

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

DATA_FILE = "user_data.json"

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

# --- HÀM KIỂM TRA COOLDOWN & GIỚI HẠN CHUNG ---
async def process_user_action(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    now = time.time()
    
    if uid not in data:
        data[uid] = {"exp": 0, "points": 0, "last_use": 0}
    
    user_info = data[uid]
    level = user_info["exp"] // 100
    
    # Cooldown: Dưới 20 là 60s (1 phút), Từ 20 trở lên là 180s (3 phút)
    cooldown_time = 180 if level >= 20 else 60
    time_passed = now - user_info.get("last_use", 0)
    
    if time_passed < cooldown_time:
        remaining = int(cooldown_time - time_passed)
        minutes = remaining // 60
        seconds = remaining % 60
        time_text = f"{minutes} phút {seconds} giây" if minutes > 0 else f"{seconds} giây"
        await ctx.send(f"⚠️ Cậu đang trong thời gian chờ! Hãy chờ thêm **{time_text}** nữa nhé. 🍵", delete_after=10)
        return False

    # Giới hạn tối đa 500 điểm Văn học mỗi ngày
    if user_info["points"] >= 500:
        await ctx.send("⚠️ Cậu đã đạt giới hạn tối đa **500 điểm Văn học** trong ngày rồi! Hãy nghỉ ngơi chút nhé. 🍵")
        return False
    
    # Cố định +10 điểm và +10 EXP (Level >= 20 giảm 25% EXP xuống còn 7)
    exp_gain = 7 if level >= 20 else 10
    
    user_info["exp"] += exp_gain
    user_info["points"] += 10
    user_info["last_use"] = now
    save_data(data)
    return True

# --- CÁC LỆNH ---
@bot.command(name='deptrai')
async def deptrai_cmd(ctx):
    if not await process_user_action(ctx): return
    data = load_data()
    level = data[str(ctx.author.id)]["exp"] // 100
    await ctx.send(f"💚 Tất nhiên rồi! (Cấp hiện tại: {level}) Người code ra tớ là đỉnh nhất! ✨")

@bot.command(name='roll')
async def roll_cmd(ctx):
    if not await process_user_action(ctx): return
    import random
    result = random.randint(1, 6)
    await ctx.send(f"🎲 Cậu tung xúc xắc ra mặt số: **{result}**! ✨")

@bot.command(name='guess')
async def guess_cmd(ctx, number: int = 1):
    if not await process_user_action(ctx): return
    import random
    secret = random.randint(1, 10)
    if number == secret:
        await ctx.send(f"🎯 Chính xác! Con số bí mật là **{secret}**. Siêu thật đấy! 💚")
    else:
        await ctx.send(f"🎯 Tiếc quá, số bí mật là **{secret}**. Lần sau thử lại nha! 🍵")

@bot.command(name='dominh')
async def dominh_cmd(ctx):
    if not await process_user_action(ctx): return
    await ctx.send("💣 Cậu đã dò mìn an toàn và nhận điểm Văn học! 🌸")

@bot.command(name='trieuhoi')
async def trieuhoi_cmd(ctx):
    if not await process_user_action(ctx): return
    await ctx.send("🌸 Triệu hồi thành công thành viên Câu lạc bộ Văn học! ✨")

@bot.command(name='hopqua')
async def hopqua_cmd(ctx):
    if not await process_user_action(ctx): return
    await ctx.send("🎁 Cậu mở hộp quà và nhận được cảm hứng văn học! 💖")

@bot.command(name='gheptho')
async def gheptho_cmd(ctx):
    if not await process_user_action(ctx): return
    data = load_data()
    user_info = data[str(ctx.author.id)]
    level = user_info["exp"] // 100
    await ctx.send(f"📜 **SÁNG TÁC THƠ CÙNG MONIKA**\n*Từng dòng code hay những vần thơ cũ...* ✨\n⭐ Nhận được **10 Điểm Văn học**! | 📊 Tổng: **{user_info['points']}/500** | Level: **{level}** 🌸")

@bot.command(name='hoso')
async def hoso_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    user_info = data.get(uid, {"exp": 0, "points": 0})
    level = user_info["exp"] // 100
    await ctx.send(f"📊 **Hồ sơ Văn học của cậu:**\n• Cấp độ (Level): **{level}**\n• Điểm Văn học hôm nay: **{user_info['points']}/500** 🌸")

@bot.command(name='Mhelp')
async def monika_help(ctx):
    help_text = (
        "💚 **Bảng lệnh & Hướng dẫn của Monika:**\n"
        "• `@Monika [chat]` - Trò chuyện cùng Monika (Không giới hạn, không cooldown)\n"
        "• `!deptrai`, `!roll`, `!guess`, `!dominh`, `!trieuhoi`, `!hopqua`, `!gheptho`, `!hoso` - Các lệnh minigame & văn học 📜\n\n"
        "📈 **Luật chơi, Giới hạn & Cooldown chung:**\n"
        "• **Giới hạn điểm:** Tối đa **500 điểm/ngày**.\n"
        "• **Thời gian chờ (Cooldown):**\n"
        "  - Dưới Level 20: Chờ **1 phút** giữa mỗi lần dùng lệnh.\n"
        "  - Từ Level 20 trở lên: Tăng lên **3 phút** và EXP giảm 25%."
    )
    await ctx.send(help_text)

if __name__ == "__main__":
    bot.run("YOUR_MONIKA_DISCORD_TOKEN")
