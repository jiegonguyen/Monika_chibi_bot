import discord
from discord.ext import commands
import os
from flask import Flask
from threading import Thread
import chess
import google.generativeai as genai

# --- CẤU HÌNH ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Cấu hình AI Gemini
genai.configure(api_key=os.environ['GOOGLE_API_KEY'])
model_ai = genai.GenerativeModel('gemini-1.5-flash')

# Dữ liệu ván cờ
active_chess_games = {}

@bot.event
async def on_ready():
    print(f'Bot {bot.user.name} đã sẵn sàng!')

# --- TÍNH NĂNG AI (TRÒ CHUYỆN) ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Bot phản hồi khi được tag
    if bot.user.mentioned_in(message):
        response = model_ai.generate_content(message.content)
        await message.channel.send(response.text)
    
    await bot.process_commands(message)

# --- TÍNH NĂNG CỜ VUA ---
@bot.command()
async def chess(ctx):
    active_chess_games[ctx.guild.id] = chess.Board()
    await ctx.send(f"♟️ Ván cờ mới! Lệnh: `!move e2e4`\n```\n{active_chess_games[ctx.guild.id]}\n```")

@bot.command()
async def move(ctx, move_uci: str):
    board = active_chess_games.get(ctx.guild.id)
    if not board: return await ctx.send("Gõ `!chess` để bắt đầu trước nhé!")
    try:
        move = chess.Move.from_uci(move_uci)
        if move in board.legal_moves:
            board.push(move)
            await ctx.send(f"```\n{board}\n```")
        else: await ctx.send("Nước đi không hợp lệ!")
    except: await ctx.send("Lỗi định dạng! (VD: `!move e2e4`)")

# --- GIỮ ONLINE (WEB SERVER) ---
app = Flask('')
@app.route('/')
def home(): return "Monika AI & Chess Bot is online!"
Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

bot.run(os.environ['DISCORD_BOT_TOKEN'])
