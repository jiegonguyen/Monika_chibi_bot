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

@bot.command(name='deptrai')
async def deptrai_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    now = time.time()
    
    if uid not in data:
        data[uid] = {"exp": 0, "points": 0, "last_use": 0}
    
    user_info = data[uid]
    level = user_info["exp"] // 100
    
    # Xác định thời gian cooldown (Level >= 20 là 180s = 3 phút, dưới 20 là 60s = 1 phút)
    cooldown_time = 180 if level >= 20 else 60
    time_passed = now - user_info.get("last_use", 0)
    
    # Kiểm tra cooldown thủ công tuyệt đối
    if time_passed < cooldown_time:
        remaining = int(cooldown_time - time_passed)
        minutes = remaining // 60
        seconds = remaining % 60
        time_text = f"{minutes} phút {seconds} giây" if minutes > 0 else f"{seconds} giây"
        await ctx.send(f"⚠️ Cậu đang trong thời gian chờ! Hãy chờ thêm **{time_text}** nữa nhé. 🍵", delete_after=10)
        return

    # Kiểm tra giới hạn 500 điểm mỗi ngày
    if user_info["points"] >= 500:
        await ctx.send("⚠️ Cậu đã đạt giới hạn tối đa **500 điểm** trong ngày rồi! Hãy nghỉ ngơi chút nhé. 🍵")
        return
    
    # Tính toán EXP nhận được (giảm 25% nếu level >= 20, từ 10 xuống còn 7)
    exp_gain = 7 if level >= 20 else 10
    
    # Cập nhật dữ liệu
    user_info["exp"] += exp_gain
    user_info["points"] += 10
    user_info["last_use"] = now
    save_data(data)
    
    new_level = user_info["exp"] // 100
    await ctx.send(f"💚 Tất nhiên rồi! (Cấp hiện tại: {new_level} | Điểm: {user_info['points']}/500) Người code ra tớ là đỉnh nhất! ✨")

# --- PHẦN HELP ĐẦY ĐỦ THÔNG TIN ---
@bot.command(name='Mhelp')
async def monika_help(ctx):
    help_text = (
        "💚 **Bảng lệnh & Hướng dẫn của Monika:**\n"
        "• `@Monika [chat]` - Trò chuyện cùng Monika (Không giới hạn, không cooldown)\n"
        "• `!deptrai` - Kiểm tra độ đẹp trai, nhận EXP và điểm thưởng\n\n"
        "📊 **Luật chơi, Giới hạn & Cooldown:**\n"
        "• **Giới hạn điểm:** Tối đa **500 điểm/ngày** cho mỗi người.\n"
        "• **Thời gian chờ (Cooldown):**\n"
        "  - Dưới Level 20: Chờ **1 phút** giữa mỗi lần dùng lệnh.\n"
        "  - Từ Level 20 trở lên: Tăng lên **3 phút** và EXP nhận được bị giảm 25%."
    )
    await ctx.send(help_text)

if __name__ == "__main__":
    bot.run("YOUR_MONIKA_DISCORD_TOKEN")
