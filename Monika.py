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

# Lưu trữ kho đồ Gacha của người dùng
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

# 5. Lệnh !help cập nhật mới
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
            "• `!deptrai` - Kiểm tra độ đẹp trai ngẫu nhiên 😎\n"
            "• `!roll` - Tung xúc xắc ngẫu nhiên từ 1 đến 6 🎲\n"
            "• `!guess [số]` - Chơi đoán số may mắn từ 1 đến 10 🎯\n"
            "• `!dominh` - Thử thách trò chơi dò mìn 💣\n"
            "• `!trieuhoi` - Triệu hồi ngẫu nhiên thành viên CLB 🌸\n"
            "• `!hopqua` - Mở hộp quà bí ẩn nhận phần thưởng bất ngờ 🎁\n"
            "• `!gacha` - Quay thưởng nhân vật Câu lạc bộ Văn học 🌟\n"
            "• `!inventory` - Xem danh sách nhân vật đã quay được 🎒\n"
            "• `!pvp [@thành_viên]` - Thách đấu PvP đối kháng với người chơi khác ⚔️"
        ),
        inline=False
    )
    await ctx.send(embed=embed)

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "inventory": []
        }
    return user_data[user_id]

# 6. Các lệnh Minigame giải trí
@bot.command(name="deptrai")
async def deptrai(ctx):
    phantram = random.randint(50, 100)
    await ctx.send(f"😎 Độ đẹp trai hôm nay của **{ctx.author.name}** là: **{phantram}%**!")

@bot.command(name="roll")
async def roll(ctx):
    ketqua = random.randint(1, 6)
    await ctx.send(f"🎲 Kết quả tung xúc xắc của **{ctx.author.name}** là: **{ketqua}** 🎲")

@bot.command(name="guess")
async def guess(ctx, so: int):
    sothang = random.randint(1, 10)
    if so == sothang:
        await ctx.send(f"🎯 Chúc mừng **{ctx.author.name}** đã đoán trúng con số may mắn **{sothang}**!")
    else:
        await ctx.send(f"❌ Tiếc quá, con số may mắn là **{sothang}**, cậu đoán sai mất rồi.")

@bot.command(name="dominh")
async def dominh(ctx):
    await ctx.send(f"💣 **{ctx.author.name}** đã kích hoạt bàn chơi dò mìn!")

@bot.command(name="trieuhoi")
async def trieuhoi(ctx):
    thanhvien = ["Monika", "Sayori", "Natsuki", "Yuri"]
    chon = random.choice(thanhvien)
    await ctx.send(f"🌸 **{ctx.author.name}** đã triệu hồi thành công thành viên **{chon}** vào câu lạc bộ văn học!")

@bot.command(name="hopqua")
async def hopqua(ctx):
    qua = ["Một bức thư tình dễ thương 💌", "Một chiếc bánh cupcake ngọt ngào 🧁", "Một tập thơ hay 📖", "Trà chiều thơm ngát 🍵"]
    chon_qua = random.choice(qua)
    embed = discord.Embed(
        title="🎁 Hộp Quà Bí Ẩn",
        description=f"Cậu đã mở hộp quà và nhận được: **{chon_qua}** 🎉",
        color=discord.Color.pink()
    )
    await ctx.send(embed=embed)

# 7. Hệ thống Gacha
NHAN_VAT_GACHA = [
    {"ten": "Monika (Hàng Hiếm)", "rate": "⭐⭐⭐⭐⭐", "color": discord.Color.gold()},
    {"ten": "Yuri (Sách & Dao)", "rate": "⭐⭐⭐⭐", "color": discord.Color.purple()},
    {"ten": "Natsuki (Bánh Cupcake)", "rate": "⭐⭐⭐⭐", "color": discord.Color.orange()},
    {"ten": "Sayori (Áo Ấm & Nụ Cười)", "rate": "⭐⭐⭐", "color": discord.Color.blue()},
]

@bot.command(name="gacha")
@commands.cooldown(1, 5, commands.BucketType.user)
async def gacha(ctx):
    user = get_user(ctx.author.id)
    roll_rate = random.choices(NHAN_VAT_GACHA, weights=[5, 20, 20, 55], k=1)[0]
    user["inventory"].append(roll_rate["ten"])

    embed = discord.Embed(
        title="🌟 KẾT QUẢ QUAY GACHA 🌟",
        description=f"**{ctx.author.name}** đã quay và nhận được:\n\n✨ **{roll_rate['ten']}** ({roll_rate['rate']})",
        color=roll_rate["color"]
    )
    await ctx.send(embed=embed)

@bot.command(name="inventory")
async def inventory(ctx):
    user = get_user(ctx.author.id)
    kho_do = user["inventory"]
    
    if not kho_do:
        await ctx.send(f"🎒 Kho đồ của **{ctx.author.name}** đang trống! Hãy dùng lệnh `!gacha` để quay nhân vật nhé.")
        return

    from collections import Counter
    do_dem = Counter(kho_do)
    mo_ta = "\n".join([f"• {ten}: **x{soluong}**" for ten, soluong in do_dem.items()])

    embed = discord.Embed(
        title=f"🎒 Kho Đồ Gacha của {ctx.author.name}",
        description=mo_ta,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# 8. Hệ thống PvP
@bot.command(name="pvp")
@commands.cooldown(1, 15, commands.BucketType.user)
async def pvp(ctx, member: discord.Member = None):
    if member is None:
        await ctx.send("⚠️ Vui lòng tag một thành viên khác để thách đấu! Ví dụ: `!pvp @TênĐốiThủ`")
        return
    if member == ctx.author or member.bot:
        await ctx.send("❌ Không thể đấu với chính mình hoặc với Bot!")
        return

    user1 = get_user(ctx.author.id)
    user2 = get_user(member.id)

    suc_manh_1 = len(user1["inventory"]) * 10 + random.randint(1, 50)
    suc_manh_2 = len(user2["inventory"]) * 10 + random.randint(1, 50)

    if suc_manh_1 > suc_manh_2:
        ket_qua_str = f"🏆 **{ctx.author.name}** đã giành chiến thắng áp đảo trước **{member.name}**!"
    elif suc_manh_1 < suc_manh_2:
        ket_qua_str = f"🏆 **{member.name}** đã phòng thủ phản công và giành chiến thắng trước **{ctx.author.name}**!"
    else:
        ket_qua_str = "🤝 Trận đấu bất phân thắng bại giữa hai người!"

    embed = discord.Embed(
        title="⚔️ ĐẤU TRƯỜNG PVP ⚔️",
        description=f"So tài giữa **{ctx.author.name}** ({suc_manh_1} điểm lực chiến) và **{member.name}** ({suc_manh_2} điểm lực chiến)!\n\n{ket_qua_str}",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

# Chạy bot
bot.run("YOUR_DISCORD_BOT_TOKEN")
