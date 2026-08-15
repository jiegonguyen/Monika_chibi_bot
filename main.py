import os
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands
import google.generativeai as genai
import chess

# 1. Cấu hình Flask server để giữ bot sống 24/7 trên Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika Bot is running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# 2. Cấu hình Discord Bot Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 3. Cấu hình Google Gemini AI (Dùng gemini-pro để tương thích tốt nhất)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    ai_model = genai.GenerativeModel('gemini-pro')
else:
    print("Cảnh báo: Chưa cấu hình GOOGLE_API_KEY!")

# Lưu trữ trạng thái bàn cờ vua cho từng kênh
chess_games = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('Bot đã sẵn sàng kết nối và hoạt động!')

# --- TÍNH NĂNG CỜ VUA ---
@bot.command(name='chess')
async def start_chess(ctx):
    chess_games[ctx.channel.id] = chess.Board()
    board = chess_games[ctx.channel.id]
    await ctx.send(f"🎲 **Ván cờ vua mới đã bắt đầu!**\nLượt đi: Trắng\nCách đi: Dùng lệnh `!move <nước đi>` (Ví dụ: `!move e2e4`)\n```\n{board}\n```")

@bot.command(name='move')
async def make_move(ctx, move_str: str):
    if ctx.channel.id not in chess_games:
        await ctx.send("⚠️ Kênh này chưa có ván cờ nào! Gõ `!chess` để tạo ván mới.")
        return
    
    board = chess_games[ctx.channel.id]
    try:
        move = chess.Move.from_uci(move_str)
        if move in board.legal_moves:
            board.push(move)
            await ctx.send(f"✅ Nước đi hợp lệ: `{move_str}`\n```\n{board}\n```")
            if board.is_game_over():
                await ctx.send("🏁 **Ván đấu kết thúc!** Kết quả: " + board.result())
                del chess_games[ctx.channel.id]
        else:
            await ctx.send("❌ Nước đi không hợp lệ trong luật cờ vua! Thử lại nước khác xem.")
    except Exception:
        await ctx.send("⚠️ Định dạng nước đi không đúng chuẩn UCI (Ví dụ: `e2e4`).")

# --- TÍNH NĂNG CHAT VỚI AI GEMINI ---
@bot.event
async def on_message(message):
    # Tránh việc bot tự trả lời chính mình
    if message.author == bot.user:
        return

    # Xử lý các lệnh prefix trước (như !chess, !move, !help)
    await bot.process_commands(message)

    # Nếu được tag tên, AI sẽ trả lời
    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        if not GOOGLE_API_KEY:
            await message.channel.send("⚠️ Chưa thiết lập Google API Key trên Render nên AI chưa thể trả lời.")
            return

        user_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if not user_prompt:
            await message.channel.send("Cậu đang gọi tớ đấy à? Tớ nghe đây! 💚")
            return

        async with message.channel.typing():
            try:
                response = ai_model.generate_content(user_prompt)
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"❌ Đã xảy ra lỗi AI: {e}")

# 4. Khởi chạy Flask song song với Discord Bot
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Lỗi: Thiếu biến môi trường DISCORD_BOT_TOKEN trên Render!")
