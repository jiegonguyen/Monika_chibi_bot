import discord
from discord.ext import commands
import yt_dlp
import os
from flask import Flask
from threading import Thread
import asyncio
import chess
import io

# Khởi tạo Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': False,
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Quản lý danh sách nhạc và trạng thái cờ vua theo từng server (guild)
music_queues = {}
loop_status = {}
active_chess_games = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

# ================= PHẦN NHẠC (MUSIC) =================

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
    else:
        await ctx.send("Cậu vào kênh thoại trước đã nhé! 💚")

def play_next(ctx):
    guild_id = ctx.guild.id
    if guild_id in loop_status and loop_status[guild_id] and guild_id in music_queues and music_queues[guild_id]:
        pass
    elif guild_id in music_queues and music_queues[guild_id]:
        next_url = music_queues[guild_id].pop(0)
        asyncio.run_coroutine_threadsafe(play_url(ctx, next_url), bot.loop)

async def play_url(ctx, url):
    data = ytdl.extract_info(url, download=False)
    filename = data['url']
    title = data.get('title', 'Audio')
    
    player = discord.FFmpegPCMAudio(filename, executable="ffmpeg", options="-vn")
    
    def after_playing(error):
        play_next(ctx)

    ctx.voice_client.play(player, after=after_playing)
    await ctx.send(f"Đang phát: **{title}** 🎵")

@bot.command()
async def play(ctx, *, url):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("Cậu phải vào kênh thoại trước đã!")
            return

    guild_id = ctx.guild.id
    if guild_id not in music_queues:
        music_queues[guild_id] = []

    if ctx.voice_client.is_playing():
        music_queues[guild_id].append(url)
        await ctx.send("Đã thêm vào hàng đợi! 🎶")
    else:
        await play_url(ctx, url)

@bot.command()
async def loop(ctx):
    guild_id = ctx.guild.id
    if guild_id not in loop_status:
        loop_status[guild_id] = False
    
    loop_status[guild_id] = not loop_status[guild_id]
    status_text = "Bật 🔂" if loop_status[guild_id] else "Tắt ➡️"
    await ctx.send(f"Đã chuyển chế độ lặp lại: **{status_text}**")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Đã chuyển bài tiếp theo! ⏭️")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()


# ================= PHẦN CỜ VUA (CHESS) =================

@bot.command(name="chess")
async def start_chess(ctx):
    guild_id = ctx.guild.id
    # Khởi tạo ván cờ mới cho server
    active_chess_games[guild_id] = chess.Board()
    
    board_text = f"♟️ **Ván Cờ Vua Mới Đã Bắt Đầu!**\nLượt đi: **Trắng** ⚪\nCách đi: Dùng lệnh `!move e2e4`\n```\n{active_chess_games[guild_id]}\n```"
    await ctx.send(board_text)

@bot.command(name="move")
async def make_move(ctx, move_uci: str):
    guild_id = ctx.guild.id
    if guild_id not in active_chess_games:
        await ctx.send("Server chưa có ván cờ nào! Hãy gõ `!chess` để tạo ván mới nhé.")
        return

    board = active_chess_games[guild_id]
    
    try:
        # Chuyển đổi chuỗi nước đi (VD: e2e4) thành đối tượng cờ vua
        move = chess.Move.from_uci(move_uci)
        if move in board.legal_moves:
            board.push(move)
            
            # Kiểm tra trạng thái ván đấu
            status = ""
            if board.is_checkmate():
                status = "\n🏆 **CHIẾU HẾT! Trò chơi kết thúc!**"
            elif board.is_stalemate():
                status = "\n🤝 **HÒA CỜ (Stalemate)!**"
            elif board.is_check():
                status = "\n⚠️ **CHIẾU TƯỚNG!**"

            turn_name = "Trắng ⚪" if board.turn == chess.WHITE else "Đen ⚫"
            board_text = f"♟️ **Bàn Cờ Hiện Tại:**{status}\nLượt đi tiếp theo: **{turn_name}**\n```\n{board}\n```"
            await ctx.send(board_text)
        else:
            await ctx.send("❌ Nước đi không hợp lệ theo luật cờ vua hoặc ô đi không đúng!")
    except ValueError:
        await ctx.send("❌ Định dạng sai! Vui lòng nhập đúng chuẩn UCI (Ví dụ: `!move e2e4` hoặc `!move g1f3`).")


# ================= WEB SERVER (GIỮ RENDER ONLINE) =================

app = Flask('')

@app.route('/')
def home():
    return "Music & Chess Bot is active!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

Thread(target=run).start()

bot.run(os.environ['DISCORD_BOT_TOKEN'])
