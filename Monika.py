import os
import asyncio
import json
import discord
from discord.ext import commands
import requests

# Cấu hình
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

DATA_FILE = "user_data.json"

# --- HÀM XỬ LÝ DỮ LIỆU ---
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)

def check_and_update_limit(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data: 
        data[uid] = {"exp": 0, "points": 0}
    
    # Giới hạn 500 điểm mỗi ngày
    if data[uid]["points"] >= 500: 
        return False, data[uid]["exp"] // 100
    
    level = data[uid]["exp"] // 100
    exp_gain = 7 if level >= 20 else 10  # Giảm 25% khi level >= 20
    
    data[uid]["exp"] += exp_gain
    data[uid]["points"] += 10
    save_data(data)
    return True, level

# --- LỆNH XỬ LÝ COOLDOWN THÔNG MINH ---
class DynamicCooldownCommand(commands.Command):
    async def invoke(self, ctx):
        data = load_data()
        level = data.get(str(ctx.author.id), {}).get("exp", 0) // 100
        # Cấp 20 trở lên cooldown là 180 giây (3 phút), dưới 20 là 60 giây (1 phút)
        cooldown_time = 180 if level >= 20 else 60
        
        self._buckets = commands.CooldownMapping(commands.Cooldown(1, cooldown_time, commands.BucketType.user))
        await super().invoke(ctx)

@bot.command(cls=DynamicCooldownCommand, name='deptrai')
async def deptrai_cmd(ctx):
    allowed, level = check_and_update_limit(ctx.author.id)
    if not allowed:
        await ctx.send("⚠️ Cậu đã đạt giới hạn tối đa **500 điểm** trong ngày rồi! Hãy nghỉ ngơi chút nhé. 🍵")
        return
    
    await ctx.send(f"💚 Tất nhiên rồi! (Cấp hiện tại: {level}) Người code ra tớ là đỉnh nhất! ✨")

# Xử lý khi dính Cooldown
@deptrai_cmd.error
async def deptrai_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        s = int(error.retry_after)
        minutes = s // 60
        seconds = s % 60
        time_text = f"{minutes} phút {seconds} giây" if minutes > 0 else f"{seconds} giây"
        await ctx.send(f"⚠️ Cậu đang trong thời gian chờ! Hãy bình tĩnh chờ thêm **{time_text}** nữa nhé. 🍵", delete_after=10)

# --- PHẦN HELP ĐÃ CẬP NHẬT ĐẦY ĐỦ COOLDOWN & LIMIT ---
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
