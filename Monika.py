import os
import random
import discord
from discord.ext import commands
import google.generativeai as genai

# 1. Cấu hình Gemini API Key
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY"))

# 2. Khởi tạo model AI (dùng model mới để không bị lỗi API v1)
model = genai.GenerativeModel("gemini-2.5-flash")

# 3. Khởi tạo Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập thành công với tên: {bot.user}")

# 4. Tích hợp lệnh AI trả lời (cho Monika)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Nếu được tag hoặc chat trong kênh bot, gọi Gemini
    if bot.user.mentioned_in(message):
        prompt = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        if prompt:
            try:
                response = model.generate_content(prompt)
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"Lỗi từ Google API: {e}")

    await bot.process_commands(message)

# 5. Các lệnh hệ thống Văn học & Level (!hopqua, !gheptho)
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
async def gheptho(ctx):
    diem_nhan_duoc = random.randint(5, 30)
    embed = discord.Embed(
        title="📜 Sáng Tác & Ghép Thơ",
        description=f"Cậu vừa hoàn thành một bài thơ và nhận thêm **{diem_nhan_duoc} Điểm Văn Học**, tích lũy để thăng cấp Level nhé! ✨",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

@bot.command(name="hoso")
async def hoso(ctx):
    embed = discord.Embed(
        title="📊 Hồ Sơ Văn Học",
        description=f"Xin chào **{ctx.author.name}**, đây là bảng điểm và cấp độ hiện tại của cậu.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# Chạy bot (Thay thế token của bot Discord vào đây)
bot.run("YOUR_DISCORD_BOT_TOKEN")
