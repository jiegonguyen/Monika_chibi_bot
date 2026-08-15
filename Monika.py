import os
import random
import discord
from discord.ext import commands
import google.generativeai as genai

# 1. Cấu hình Gemini API Key
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY"))

# 2. Khởi tạo model AI chuẩn tránh lỗi v1
model = genai.GenerativeModel("gemini-2.5-flash")

# 3. Khởi tạo Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Lưu trữ dữ liệu người dùng (Điểm, Level, Gacha Inventory, HP/Sức mạnh PvP)
user_data = {}

@bot.event
async def on_ready():
    print(f"Bot đã online thành công với tên: {bot.user}")

# 4. Tích hợp lệnh AI trả lời (chống sập bot)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message):
        prompt = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        if prompt:
            try:
                response = model.generate_content(prompt)
                await message.reply(response.text)
            except Exception as e:
                print(f"Lỗi gọi Gemini: {e}")
                await message.reply("Hệ thống AI đang bận chút xíu, cậu thử lại sau nha! 🌸")

    await bot.process_commands(message)

# 5. Lệnh !help cập nhật thêm Gacha & PvP
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="✨ DANH SÁCH LỆNH CỦA MONIKA ✨",
        color=discord.Color.pink()
    )
    embed.add_field(
        name="💬 Trò chuyện với AI:",
        value="• Nhắc tên tớ (`@Chibi_Monika_AI`) kèm theo nội dung để trò chuyện trực tiếp! 💚",
        inline=False
    )
    embed.add_field(
        name="🎮 Minigame, Gacha & PvP:",
        value=(
            "• `!hopqua` - Mở hộp quà bí ẩn nhận phần thưởng bất ngờ 🎁\n"
            "• `!gacha` - Quay thưởng nhân vật Câu lạc bộ Văn học (Tốn 50 điểm) 🌟\n"
            "• `!inventory` - Xem danh sách nhân vật đã quay được 🎒\n"
            "• `!pvp [@thành_viên]` - Thách đấu PvP đối kháng tính điểm với người chơi khác ⚔️"
        ),
        inline=False
    )
    embed.add_field(
        name="📜 Hệ thống Văn học & Level:",
        value=(
            "• `!gheptho` - Sáng tác/ghép thơ nhận Điểm Văn Học và thăng cấp Level ✨\n"
            "• `!hoso` - Kiểm tra Điểm Văn Học và Level hiện tại 📊\n"
            "_Lưu ý: Giới hạn 500 điểm/ngày. Từ Level 20 trở lên giảm 25% EXP và cool down 3 phút._"
        ),
        inline=False
    )
    await ctx.send(embed=embed)

# Khởi tạo dữ liệu người dùng mặc định
def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "diem": 100, # Tặng sẵn 100 điểm để test gacha
            "level": 1,
            "ngay": "",
            "diem_ngay": 0,
            "inventory": []
        }
    return user_data[user_id]

# 6. Hệ thống Gacha (Quay thưởng nhân vật)
NHAN_VAT_GACHA = [
    {"ten": "Monika (Hàng Hiếm)", "rate": "⭐⭐⭐⭐⭐", "color": discord.Color.gold()},
    {"ten": "Yuri (Sách & Dao)", "rate": "⭐⭐⭐⭐", "color": discord.Color.purple()},
    {"ten": "Natsuki (Bánh Cupcake)", "rate": "⭐⭐⭐⭐", "color": discord.Color.orange()},
    {"ten": "Sayori (Áo Ấm & Nụ Cười)", "rate": "⭐⭐⭐", "color": discord.Color.blue()},
]

@bot.command(name="gacha")
@commands.cooldown(1, 10, commands.BucketType.user)
async def gacha(ctx):
    user = get_user(ctx.author.id)
    
    # Kiểm tra đủ điểm quay không (Mỗi lần 50 điểm)
    if user["diem"] < 50:
        await ctx.send(f"⚠️ Cậu không đủ điểm! Cần ít nhất **50 điểm** để quay Gacha (Điểm hiện tại: {user['diem']}).")
        return

    user["diem"] -= 50
    
    # Tỉ lệ quay ngẫu nhiên
    roll_rate = random.choices(
        NHAN_VAT_GACHA, 
        weights=[5, 20, 20, 55], # Trọng số tỉ lệ ra đồ
        k=1
    )[0]
    
    user["inventory"].append(roll_rate["ten"])

    embed = discord.Embed(
        title="🌟 KẾT QUẢ QUAY GACHA 🌟",
        description=f"**{ctx.author.name}** đã chi 50 điểm và nhận được:\n\n✨ **{roll_rate['ten']}** ({roll_rate['rate']})",
        color=roll_rate["color"]
    )
    await ctx.send(embed=embed)

@bot.command(name="inventory")
async def inventory(ctx):
    user = get_user(ctx.author.id)
    kho_do = user["inventory"]
    
    if not kho_do:
        await ctx.send(f"🎒 Kho đồ của **{ctx.author.name}** đang trống trơn! Hãy dùng lệnh `!gacha` để quay nhân vật nhé.")
        return

    # Đếm số lượng từng nhân vật
    from collections import Counter
    do_dem = Counter(kho_do)
    mo_ta = "\n".join([f"• {ten}: **x{soluong}**" for ten, soluong in do_dem.items()])

    embed = discord.Embed(
        title=f"🎒 Kho Đồ Gacha của {ctx.author.name}",
        description=mo_ta,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# 7. Hệ thống PvP (Đấu trường đối kháng)
@bot.command(name="pvp")
@commands.cooldown(1, 30, commands.BucketType.user) # Hồi chiêu 30 giây giữa các trận PvP
async def pvp(ctx, member: discord.Member = None):
    if member is None:
        await ctx.send("⚠️ Vui lòng tag một thành viên khác để thách đấu! Ví dụ: `!pvp @TênĐốiThủ`")
        return

    if member == ctx.author:
        await ctx.send("❌ Cậu không thể tự đánh chính mình được đâu ngốc ạ! 😄")
        return

    if member.bot:
        await ctx.send("🤖 Cậu không thể đấu PvP với Bot được!")
        return

    nguoi_1 = ctx.author
    nguoi_2 = member

    user1_data = get_user(nguoi_1.id)
    user2_data = get_user(nguoi_2.id)

    # Sức mạnh dựa vào Level và số lượng nhân vật gacha trong kho
    suc_manh_1 = user1_data["level"] * 10 + len(user1_data["inventory"]) * 5 + random.randint(1, 50)
    suc_manh_2 = user2_data["level"] * 10 + len(user2_data["inventory"]) * 5 + random.randint(1, 50)

    if suc_manh_1 > suc_manh_2:
        nguoi_thang = nguoi_1
        nguoi_thua = nguoi_2
        thuong = 30
        user1_data["diem"] += thuong
        ket_qua_str = f"🏆 **{nguoi_1.name}** đã tung đòn chí mạng và giành chiến thắng áp đảo, nhận thưởng **+30 điểm**!"
    elif suc_manh_1 < suc_manh_2:
        nguoi_thang = nguoi_2
        nguoi_thua = nguoi_1
        thuong = 30
        user2_data["diem"] += thuong
        ket_qua_str = f"🏆 **{nguoi_2.name}** đã phòng thủ phản công xuất sắc và giành chiến thắng, nhận thưởng **+30 điểm**!"
    else:
        ket_qua_str = "🤝 Trận đấu bất phân thắng bại! Cả hai hòa nhau trong gang tấc."

    embed = discord.Embed(
        title="⚔️ ĐẤU TRƯỜNG PVP VĂN HỌC ⚔️",
        description=f"Màn so tài giữa **{nguoi_1.name}** (Sức mạnh: {suc_manh_1}) và **{nguoi_2.name}** (Sức mạnh: {suc_manh_2})!\n\n{ket_qua_str}",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

@pvp.error
async def pvp_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Cậu vừa tham gia đấu trường xong! Hãy nghỉ ngơi **{int(error.retry_after)} giây** nữa mới được PvP tiếp nhé.")

# 8. Hệ thống Văn học & Level cũ
@bot.command(name="hopqua")
async def hopqua(ctx):
    diem_thuong = random.randint(10, 100)
    embed = discord.Embed(
        title="🎁 Hộp Quà Bí Ẩn",
        description=f"Cậu đã mở hộp quà và nhận được **{diem_thuong} Điểm Văn Học** bất ngờ! 🎉",
        color=discord.Color.pink()
    )
    await ctx.send(embed=embed)

@bot.command(name="gheptho")
@commands.cooldown(1, 180, commands.BucketType.user)
async def gheptho(ctx):
    user_id = ctx.author.id
    today = str(discord.utils.utcnow().date())
    user = get_user(user_id)
    
    if user["ngay"] != today:
        user["ngay"] = today
        user["diem_ngay"] = 0

    if user["diem_ngay"] >= 500:
        await ctx.send(f"⚠️ **{ctx.author.name}** đã đạt giới hạn tối đa 500 điểm trong ngày hôm nay rồi!")
        return

    diem_nhan_duoc = random.randint(15, 40)
    if user["level"] >= 20:
        diem_nhan_duoc = int(diem_nhan_duoc * 0.75)

    if user["diem_ngay"] + diem_nhan_duoc > 500:
        diem_nhan_duoc = 500 - user["diem_ngay"]

    user["diem"] += diem_nhan_duoc
    user["diem_ngay"] += diem_nhan_duoc

    new_level = (user["diem"] // 100) + 1
    if new_level > user["level"]:
        user["level"] = new_level
        await ctx.send(f"🎉 Chúc mừng **{ctx.author.name}** đã thăng cấp lên **Level {user['level']}**! ✨")

    embed = discord.Embed(
        title="📜 Sáng Tác & Ghép Thơ",
        description=f"Cậu nhận thêm **{diem_nhan_duoc} Điểm Văn Học**! (Hôm nay: {user['diem_ngay']}/500 điểm)",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

@gheptho.error
async def gheptho_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        consec_time = int(error.retry_after)
        await ctx.send(f"⏳ Cậu đang trong thời gian hồi chiêu! Vui lòng đợi thêm **{consec_time // 60} phút {consec_time % 60} giây** nữa.")

@bot.command(name="hoso")
async def hoso(ctx):
    user = get_user(ctx.author.id)
    embed = discord.Embed(
        title=f"📊 Hồ Sơ Văn Học của {ctx.author.name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="⭐ Cấp độ", value=f"Level {user['level']}", inline=True)
    embed.add_field(name="📚 Điểm Văn Học", value=f"{user['diem']} điểm", inline=True)
    embed.add_field(name="🔥 Đã nhận hôm nay", value=f"{user['diem_ngay']}/500 điểm", inline=False)
    embed.add_field(name="🎒 Số nhân vật Gacha", value=f"{len(user['inventory'])} nhân vật", inline=False)
    await ctx.send(embed=embed)

# Chạy bot
bot.run("YOUR_DISCORD_BOT_TOKEN")
