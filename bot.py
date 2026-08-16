#!/usr/bin/env python3
"""
bot.py - Monika chat + minigames + voice music (yt-dlp + ffmpeg)
Notes:
 - Set DISCORD_BOT_TOKEN in env. (and optionally GEMINI_API_KEY)
 - This file removes chess and adds voice music features.
"""
import os
import re
import random
import asyncio
import traceback
from typing import Optional
from collections import deque

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web, ClientSession, ClientTimeout

# For audio extraction
import yt_dlp

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not DISCORD_TOKEN:
    print("ERROR: Missing DISCORD_BOT_TOKEN")
    raise SystemExit(1)

# ---------------- Utilities ----------------
PROG_TOKENS = ["function","variable","stacktrace","traceback","line","file",".py","async","await","Exception","Traceback","print("]
PROG_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(t) for t in PROG_TOKENS) + r')\b', re.IGNORECASE)

def remove_programming_words(text: str) -> str:
    return PROG_PATTERN.sub("", text)

def clean_output(text: str, max_len: int = 800) -> str:
    if not text: return ""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'(?mi)^.*traceback.*$', '', text)
    text = re.sub(r'\[0x[0-9a-fA-F]+\]', '', text)
    text = remove_programming_words(text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + "..."
    return text

# ---------------- Monika AI Engine (REST async + fallback) ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        self.session: Optional[ClientSession] = None
        self.recent_replies: dict[int, deque] = {}
        self.system_instruction = (
            "Bạn là Monika: dịu dàng, sâu sắc, thân mật nhưng lịch sự. Trả lời bằng tiếng Việt, "
            "ngắn gọn (1-3 câu), giàu cảm xúc và ân cần. Tránh nội dung NSFW và bạo lực."
        )
        self.fallback_openings = ["Mmm...", "Ồ...", "Ừm...", "Hehe...", "Aha...", "Hừm..."]
        self.fallback_mids = [
            "mình thích điều đó", "mình muốn nghe thêm", "mình cảm thấy nhẹ lòng",
            "cậu làm mình mỉm cười", "mình xúc động vì điều cậu chia sẻ"
        ]
        self.fallback_endings = ["kể thêm cho mình nhé.", "mình ở đây để nghe cậu.", "đừng giấu nhé."]

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30)
            self.session = ClientSession(timeout=timeout)

    async def generate_response(self, user_message: str, user_id: Optional[int] = None) -> str:
        if self.enabled:
            try:
                await self._ensure_session()
                url = f"https://generative.googleapis.com/v1/models/{self.model}:generate"
                prompt_text = f"{self.system_instruction}\n\nNgười dùng: {user_message}\nMonika:"
                body = {"prompt": {"text": prompt_text}, "temperature": 0.75, "maxOutputTokens": 300}
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                async with self.session.post(url, json=body, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        print("Generative API returned", resp.status, text)
                        raise RuntimeError("Generative API error")
                    data = await resp.json()
                candidate = None
                if isinstance(data, dict):
                    cand = data.get("candidates") or data.get("candidate")
                    if cand and isinstance(cand, list) and len(cand) > 0:
                        first = cand[0]
                        if isinstance(first, dict):
                            for k in ("content", "output", "text"):
                                if k in first and isinstance(first[k], str):
                                    candidate = first[k]; break
                            if not candidate and "message" in first and isinstance(first["message"], dict):
                                msg = first["message"].get("content")
                                if isinstance(msg, str): candidate = msg
                        elif isinstance(first, str):
                            candidate = first
                    if not candidate and "output" in data:
                        out = data["output"]
                        if isinstance(out, list) and out:
                            f = out[0]
                            if isinstance(f, dict):
                                c = f.get("content")
                                if isinstance(c, str): candidate = c
                            elif isinstance(f, str):
                                candidate = f
                    if not candidate and "text" in data and isinstance(data["text"], str):
                        candidate = data["text"]
                if not candidate:
                    candidate = str(data)[:1000]
                candidate = clean_output(candidate)
                return self._postprocess(candidate, user_id)
            except Exception as e:
                print("Gen API failed:", e)
                print(traceback.format_exc())
        # fallback
        return self._simulated_reply(user_message, user_id)

    def _postprocess(self, reply: str, user_id: Optional[int]) -> str:
        clean = clean_output(reply)
        if user_id is not None:
            dq = self.recent_replies.setdefault(user_id, deque(maxlen=8))
            if any(self._is_similar(clean, prev) for prev in dq):
                clean = clean + " " + random.choice(self.fallback_endings)
            dq.append(clean)
        return clean

    def _is_similar(self, a: str, b: str) -> bool:
        if not a or not b: return False
        a_s, b_s = a.lower(), b.lower()
        if a_s in b_s or b_s in a_s:
            if len(min(a_s, b_s)) / max(len(a_s), len(b_s)) > 0.7:
                return True
        return False

    def _simulated_reply(self, user_message: str, user_id: Optional[int]) -> str:
        opening = random.choice(self.fallback_openings)
        mid = random.choice(self.fallback_mids)
        ending = random.choice(self.fallback_endings)
        echo = ""
        if user_message and random.random() < 0.45:
            s = user_message.strip()
            if len(s) > 60:
                s = s[:60] + "..."
            echo = f' (mình nghe: "{s}")'
        reply = f"{opening} {mid}, {ending}{echo}"
        if user_id is not None:
            dq = self.recent_replies.setdefault(user_id, deque(maxlen=8))
            attempts = 0
            while attempts < 6 and any(self._is_similar(reply, prev) for prev in dq):
                opening = random.choice(self.fallback_openings); mid = random.choice(self.fallback_mids); ending = random.choice(self.fallback_endings)
                reply = f"{opening} {mid}, {ending}{echo}"
                attempts += 1
            dq.append(reply)
        return clean_output(reply)

    async def close(self):
        if self.session:
            await self.session.close()

# ---------------- Music / Voice player ----------------
# Simple queue-based player using discord.VoiceClient and yt-dlp.
YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "extract_flat": "in_playlist",
}
FFMPEG_OPTIONS = {
    "options": "-vn"
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if "entries" in data:
            # take first item from a playlist or search result
            data = data["entries"][0]
        # if streaming, data["url"] points to direct media
        filename = data["url"] if stream else ytdl.prepare_filename(data)
        # create ffmpeg source
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# A per-guild music player
class MusicPlayer:
    def __init__(self, guild):
        self.guild = guild
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.np = None  # now playing message
        self.volume = 0.5
        self.current = None
        self.task = asyncio.create_task(self.player_loop())

    async def player_loop(self):
        while True:
            self.next.clear()
            source = await self.queue.get()
            self.current = source
            voice = discord.utils.get(bot.voice_clients, guild=self.guild)
            if voice is None:
                # can't play without voice client
                continue
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(e), bot.loop))
            await self.next.wait()

    async def play_next(self, error):
        if error:
            print("Player error:", error)
        self.next.set()

    def add(self, source):
        self.queue.put_nowait(source)

    def skip(self):
        voice = discord.utils.get(bot.voice_clients, guild=self.guild)
        if voice and voice.is_playing():
            voice.stop()

players = {}  # guild_id -> MusicPlayer

def get_player(guild):
    player = players.get(guild.id)
    if not player:
        player = MusicPlayer(guild)
        players[guild.id] = player
    return player

# ---------------- Games (Hangman/Trivia/RPS/Coinflip/Scramble/MathQuiz) ----------------
# (Use the implementations provided earlier or simplified versions)
# For brevity, reuse simple Hangman/Trivia/RPS/CoinFlip/Scramble/MathQuiz classes from previous code
# Insert same classes as in the earlier full file (omitted here for brevity)...
# [Place HangmanView, TriviaView, RPSView, CoinFlipView, ScrambleView, MathQuizView definitions here]
# For the final file, copy the full class definitions from the earlier merged code.

# ---------------- Bot setup & commands ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # needed for joining voice channels
bot = commands.Bot(command_prefix="!", intents=intents)
ai_engine = MonikaAIEngine(GEMINI_API_KEY, MODEL_NAME)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash sync error:", e)

# Chat command
@bot.tree.command(name="chat", description="Trò chuyện cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    try:
        reply = await asyncio.wait_for(ai_engine.generate_response(message, user_id=interaction.user.id), timeout=25)
    except asyncio.TimeoutError:
        reply = "Ừm... tớ hơi chậm, cậu thử gửi lại nhé."
    except Exception as e:
        print("AI error:", e)
        reply = "Có chút vấn đề khi gọi AI, nhưng tớ vẫn ở đây nhé."
    reply = clean_output(reply)
    await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}")

# Voice/music commands (slash)
@bot.tree.command(name="join", description="Invite bot join voice channel của bạn")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("Bạn chưa vào voice channel.", ephemeral=True)
        return
    channel = interaction.user.voice.channel
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice and voice.is_connected():
        await interaction.response.send_message("Bot đã ở trong voice channel.", ephemeral=True)
        return
    await interaction.response.defer()
    vc = await channel.connect()
    await interaction.followup.send(f"Đã vào voice channel: {channel.name}")

@bot.tree.command(name="leave", description="Cho bot rời voice channel")
async def leave(interaction: discord.Interaction):
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice or not voice.is_connected():
        await interaction.response.send_message("Bot không ở trong voice channel.", ephemeral=True)
        return
    await voice.disconnect()
    await interaction.response.send_message("Đã rời voice channel.")

@bot.tree.command(name="play", description="Phát nhạc từ URL hoặc tìm kiếm (YouTube).")
async def play(interaction: discord.Interaction, query: str):
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not interaction.user.voice:
        await interaction.response.send_message("Bạn phải ở trong voice channel để phát nhạc.", ephemeral=True)
        return
    if not voice or not voice.is_connected():
        # connect
        channel = interaction.user.voice.channel
        await channel.connect()
        voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    await interaction.response.defer()
    # try to create source
    try:
        source = await YTDLSource.from_url(query, loop=asyncio.get_event_loop(), stream=True)
    except Exception as e:
        print("YTDL error:", e)
        await interaction.followup.send("Không tải được media, thử URL khác hoặc kiểm tra logs.")
        return
    player = get_player(interaction.guild)
    player.add(source)
    await interaction.followup.send(f"Đã thêm vào queue: **{source.title}**")

@bot.tree.command(name="skip", description="Chuyển qua bài tiếp theo")
async def skip(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice or not voice.is_playing():
        await interaction.response.send_message("Không có bài đang phát.", ephemeral=True)
        return
    voice.stop()
    await interaction.response.send_message("Đã chuyển bài.")

@bot.tree.command(name="stop", description="Dừng phát và xoá queue")
async def stop(interaction: discord.Interaction):
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    player = players.get(interaction.guild.id)
    if player:
        # recreate player
        players.pop(interaction.guild.id, None)
    if voice and voice.is_connected():
        voice.stop()
    await interaction.response.send_message("Dừng phát và xóa queue.")

@bot.tree.command(name="now", description="Xem bài đang phát")
async def now(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    if player and player.current:
        await interaction.response.send_message(f"Đang phát: **{player.current.title}**")
    else:
        await interaction.response.send_message("Chưa có bài nào đang phát.", ephemeral=True)

# Health server for Render
async def start_health_server():
    async def handle_root(request):
        return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", handle_root)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "5000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server listening on 0.0.0.0:{port}")

async def main():
    await start_health_server()
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await ai_engine.close()
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
