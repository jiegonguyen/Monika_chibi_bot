import os
import time
import json
import random
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

DATA_FILE = "user_data.json"

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

async def process_user_action(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    now = time.time()
    if uid not in data: data[uid] = {"exp": 0, "points": 0, "last_use": 0, "inventory": []}
    
    user_info = data[uid]
    level = user_info["exp"] // 100
    cooldown_time = 180 if level >= 20 else 60
    
    if now - user_info.get("last_use", 0) < cooldown_time:
        remaining = int(cooldown_time - (now - user_info["last_use"]))
        await ctx.send(f"⚠️ Cậu đang chờ {remaining} giây nữa nhé! 🍵", delete_after=5)
        return False

    if user_info["points"] >= 500:
        await ctx.send("⚠️ Đã đạt giới hạn 500 điểm Văn học/ngày! 🍵")
        return False
    
    user_info["exp"] += (7 if level >= 20 else 10)
    user_info["points"] += 10
    user_info["last_use"] = now
    save_data(data)
    return True

@bot.command(name='homdoki')
async def homdoki_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    if uid not in data: data[uid] = {"exp": 0, "points": 0, "last_use": 0, "inventory": []}
    if data[uid]["points"] < 100:
        await ctx.send(f"⚠️ Cần 100 điểm để mở hòm! Hiện có {data[uid]['points']}.")
        return
    data[uid]["points"] -= 100
    char = random.choice(["Monika", "Sayori", "Yuri", "Natsuki"])
    outfit = random.choice(["Đồng phục", "Dạ hội", "Thể thao", "Gothic"])
    reward = f"{char} ({outfit})"
    data[uid]["inventory"].append(reward)
    save_data(data)
    await ctx.send(f"🎁 Mở hòm được: **{reward}**! (Còn {data[uid]['points']} điểm)")

@bot.command(name='danh')
async def danh_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    if not data.get(uid, {}).get("inventory"):
        await ctx.send("⚠️ Hãy dùng `!homdoki` lấy nhân vật trước đã!")
        return
    fighter = random.choice(data[uid]["inventory"])
    await ctx.send(f"⚔️ **{fighter}** đã xuất chiến và giành thắng lợi huy hoàng! ✨")

@bot.command(name='Mhelp')
async def monika_help(ctx):
    await ctx.send("✨ **LỆNH MONIKA** ✨\nMinigame: `!deptrai`, `!roll`, `!guess`, `!gheptho`\nHòm Doki: `!homdoki` (100đ), `!danh`\nHồ sơ: `!hoso`\nQuy định: Max 500đ/ngày, Cooldown 1-3p.")

@bot.command(name='hoso')
async def hoso_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    u = data.get(uid, {"exp":0, "points":0, "inventory":[]})
    await ctx.send(f"📊 Level: {u['exp']//100} | Điểm: {u['points']}/500\n🎒 Nhân vật: {', '.join(u['inventory'])}")

# CẬP NHẬT TOKEN VÀO ĐÂY:
bot.run(MTUzODA5ODA3NzUyNzk2NTcyNg.Gjh_eu.nL7OIX_SMYERML8RihsF_fB7nq6hE1-MMdpqLY)
