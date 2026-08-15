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

# --- HÀM KIỂM TRA COOLDOWN & GIỚI HẠN CHUNG ---
async def process_user_action(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    now = time.time()
    
    if uid not in data:
        data[uid] = {"exp": 0, "points": 0, "last_use": 0, "inventory": []}
    
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
    
    exp_gain = 7 if level >= 20 else 10
    
    user_info["exp"] += exp_gain
    user_info["points"] += 10
    user_info["last_use"] = now
    save_data(data)
    return True

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

# --- CÁC LỆNH MINIGAME & GIẢI TRÍ ---
@bot.command(name='deptrai')
async def deptrai_cmd(ctx):
    if not await process_user_action(ctx): return
    data = load_data()
    level = data[str(ctx.author.id)]["exp"] // 100
    await ctx.send(f"💚 Tất nhiên rồi! (Cấp hiện tại: {level}) Người code ra tớ là đỉnh nhất! ✨")

@bot.command(name='roll')
async def roll_cmd(ctx):
    if not await process_user_action(ctx): return
    await ctx.send(f"🎲 Cậu tung xúc xắc ra mặt số: **{random.randint(1, 6)}**! ✨")

@bot.command(name='guess')
async def guess_cmd(ctx, number: int = 1):
    if not await process_user_action(ctx): return
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
    user_info = data.get(uid, {"exp": 0, "points": 0, "inventory": []})
    level = user_info["exp"] // 100
    inv = ", ".join(user_info["inventory"]) if user_info["inventory"] else "Chưa có nhân vật nào trong hòm!"
    await ctx.send(f"📊 **Hồ sơ Văn học của cậu:**\n• Cấp độ (Level): **{level}**\n• Điểm Văn học hôm nay: **{user_info['points']}/500** 🌸\n• **Nhân vật sở hữu:** {inv}")

# --- TÍNH NĂNG HÒM DOKI & CHIẾN ĐẤU ---
@bot.command(name='homdoki')
async def homdoki_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    if uid not in data:
        data[uid] = {"exp": 0, "points": 0, "last_use": 0, "inventory": []}
    
    user_info = data[uid]
    
    if user_info["points"] < 100:
        await ctx.send(f"⚠️ Cậu cần ít nhất **100 Điểm Văn học** để mở Hòm Doki! Hiện tại cậu chỉ có **{user_info['points']} điểm** thôi. Hãy chăm chỉ dùng lệnh minigame nhé! 🍵")
        return
    
    user_info["points"] -= 100
    
    characters = [
        ("Monika", ["Đồng phục CLB", "Váy dạ hội xanh", "Đồ thể thao", "Áo khoác định mệnh"]),
        ("Sayori", ["Đồng phục CLB", "Pyjama đáng yêu", "Đồ mùa đông ấm áp", "Nơ hồng chiến thần"]),
        ("Yuri", ["Đồng phục CLB", "Áo len tím cổ lọ", "Đầm Gothic bí ẩn", "Áo choàng trinh thám"]),
        ("Natsuki", ["Đồng phục CLB", "Tạp dề làm bánh", "Đồ thủy thủ dễ thương", "Đồ hóa trang mèo con"])
    ]
    
    char_name, outfits = random.choice(characters)
    outfit = random.choice(outfits)
    reward_card = f"{char_name} ({outfit})"
    
    user_info["inventory"].append(reward_card)
    save_data(data)
    
    await ctx.send(f"🎁 **MỞ HÒM DOKI THÀNH CÔNG!** (-100 Điểm)\n✨ Cậu nhận được: **{reward_card}**!\n📊 Điểm Văn học còn lại: **{user_info['points']}/500** 🌸")

@bot.command(name='danh')
async def danh_cmd(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    user_info = data.get(uid, {"inventory": []})
    
    if not user_info["inventory"]:
        await ctx.send("⚠️ Cậu chưa có nhân vật nào trong bộ sưu tập! Hãy dùng `!homdoki` để mở nhân vật ra chiến đấu nhé. 🍵")
        return
    
    fighter = random.choice(user_info["inventory"])
    enemy = random.choice(["Glitched Monika", "Yandere NPC", "Anti-Poetry Boss", "Bug Hệ Thống"])
    result = random.choice(["chiến thắng vẻ vang", "giành phần thắng sát nút", "căng sức hạ gục đối thủ"])
    
    await ctx.send(f"⚔️ **TRẬN CHIẾN VĂN HỌC!**\n🛡️ Nhân vật xuất trận: **{fighter}**\n💥 Đối đầu với: **{enemy}**\n🏆 Kết quả: Nhân vật của cậu đã **{result}** và mang về vinh quang cho CLB! ✨")

# --- BẢNG HELP CẬP NHẬT CHI TIẾT HÒM DOKI ---
@bot.command(name='Mhelp')
async def monika_help(ctx):
    help_text = (
        "✨ **DANH SÁCH LỆNH CỦA MONIKA** ✨\n\n"
        "🎮 **Minigame & Kiếm Điểm:**\n"
        "• `!deptrai`, `!roll`, `!guess`, `!dominh`, `!trieuhoi`, `!hopqua`, `!gheptho` - Nhận EXP & Điểm Văn học 📜\n"
        "• `!hoso` - Kiểm tra Level, Điểm Văn học và nhân vật sở hữu 📊\n\n"
        "🎁 **Hệ thống Hòm Doki & Chiến Đấu:**\n"
        "• `!homdoki` - Mở hòm ngẫu nhiên nhận nhân vật CLB Văn học với các trang phục độc đáo (**Tốn 100 Điểm Văn học**) 📦\n"
        "• `!danh` - Đưa nhân vật trong hòm ra chiến đấu với các đối thủ để giành vinh quang ⚔️\n\n"
        "⏳ **QUY ĐỊNH COOLDOWN & GIỚI HẠN:**\n"
        "• **Giới hạn điểm:** Tối đa **500 Điểm Văn học / ngày**.\n"
        "• **Thời gian chờ (Cooldown):**\n"
        "  - Dưới Level 20: Chờ **1 phút** giữa các lệnh cày điểm.\n"
        "  - Từ Level 20 trở lên: Tăng lên **3 phút** và EXP nhận được giảm 25%.\n\n"
        "📌 *Cậu cần giúp gì cứ gọi tớ nha!* 💚"
    )
    await ctx.send(help_text)

if __name__ == "__main__":
    bot.run(os.environ.get("DISCORD_TOKEN"))
