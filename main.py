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

active_chess_games = {}

@bot.event
async def on_ready():
    print(f'Bot {bot.user.name} đã kết nối thành công với Discord!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if bot.user.mentioned_in(message):
        try:
            response = model_ai.generate_content(message.content)
            await message.channel.send(response.text)
        except Exception as e:
            await message.channel.send(f"❌ Lỗi AI: {e}")
    
    await bot.process_commands(message)

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

# --- WEB SERVER GIỮ RENDER LIVE ---
app = Flask('')

@app.route('/')
def home():
    return "Monika Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# Chạy web server ở luồng riêng
Thread(target=run_web).start()

# Chạy bot Discord chính thức
bot.run(os.environ['DISCORD_BOT_TOKEN'])
