#!/usr/bin/env python3
"""
bot.py - Monika AI + minigames + voice music + soft-NSFW (session-based).
- Env: DISCORD_BOT_TOKEN (required), GEMINI_API_KEY (optional).
- No simulated fallback: if Gemini not configured or fails, bot returns informative message.
- Voice requires ffmpeg + PyNaCl. Use Dockerfile below for Render deployments.
"""
import os
import re
import json
import random
import asyncio
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
from collections import deque

import discord
from discord.ext import commands
from aiohttp import web, ClientSession, ClientTimeout
from dotenv import load_dotenv

import yt_dlp

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not DISCORD_TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN not set")
    raise SystemExit(1)

# Voice lib check (PyNaCl)
try:
    import nacl  # type: ignore
    VOICE_LIB_AVAILABLE = True
except Exception:
    VOICE_LIB_AVAILABLE = False

# ---------------- NSFW storage & sessions ----------------
SETTINGS_PATH = Path("nsfw_settings.json")
LOG_PATH = Path("nsfw_attempts.log")

def load_nsfw_settings() -> Dict[str, Dict]:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_nsfw_settings(settings: Dict[str, Dict]):
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

nsfw_settings = load_nsfw_settings()
active_nsfw_sessions: Dict[Tuple[str, str, str], float] = {}

def set_nsfw_session(guild_id: Optional[int], channel_id: Optional[int], user_id: int, minutes: int = 10):
    key = (str(guild_id) if guild_id else "DM", str(channel_id) if channel_id else "DM", str(user_id))
    expiry = asyncio.get_event_loop().time() + minutes * 60
    active_nsfw_sessions[key] = expiry

def revoke_nsfw_session(guild_id: Optional[int], channel_id: Optional[int], user_id: int):
    key = (str(guild_id) if guild_id else "DM", str(channel_id) if channel_id else "DM", str(user_id))
    active_nsfw_sessions.pop(key, None)

def is_nsfw_session_active(interaction: discord.Interaction) -> bool:
    now = asyncio.get_event_loop().time()
    expired = [k for k, v in active_nsfw_sessions.items() if v < now]
    for k in expired:
        active_nsfw_sessions.pop(k, None)
    key = (
        str(getattr(interaction.guild, "id", "DM")) if interaction.guild else "DM",
        str(getattr(interaction.channel, "id", "DM")) if interaction.channel else "DM",
        str(interaction.user.id),
    )
    return key in active_nsfw_sessions

def log_nsfw_attempt(interaction: discord.Interaction, user_message: str, generated: Optional[str]):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"TIME: {datetime.utcnow().isoformat()}Z\n")
            f.write(f"GUILD: {getattr(interaction.guild,'id',None)} CHANNEL: {getattr(interaction.channel,'id',None)} USER: {interaction.user.id}\n")
            f.write("USER MSG: " + (user_message or "") + "\n")
            f.write("GENERATED: " + (generated or "") + "\n\n")
    except Exception:
        pass

# ---------------- Utilities ----------------
PROG_TOKENS = ["function","variable","stacktrace","traceback","line","file",".py","async","await","Exception","Traceback","print(","logger"]
PROG_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(t) for t in PROG_TOKENS) + r')\b', re.IGNORECASE)

def remove_programming_words(text: str) -> str:
    return PROG_PATTERN.sub("", text)

def clean_output(text: str, max_len: int = 800) -> str:
    if not text: return ""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'(?mi)^.*traceback.*$', '', text)
    text = re.sub(r'(?mi)^.*exception.*$', '', text)
    text = re.sub(r'\[0x[0-9a-fA-F]+\]', '', text)
    text = remove_programming_words(text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + "..."
    return text

EXPLICIT_TOKENS = ["sex","tình dục","quan hệ","âm đạo","dương vật","bú","thổi","oral","anal","fuck","suck","porn","penis","vagina","masturb","rape","ngực","vú","lồn","địt","zịt"]
EXPLICIT_RE = re.compile(r'\b(' + '|'.join(re.escape(t) for t in EXPLICIT_TOKENS) + r')\b', re.IGNORECASE)
def contains_explicit(text: str) -> bool:
    if not text: return False
    return bool(EXPLICIT_RE.search(text))

# ---------------- Monika AI Engine (no fallback) ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        self.session: Optional[ClientSession] = None
        self.recent_replies: Dict[int, deque] = {}
        self.system_instruction = ("Bạn là Monika: dịu dàng, sâu sắc, thân mật nhưng lịch sự. Trả lời bằng tiếng Việt, "
                                   "ngắn gọn (1-3 câu), giàu cảm xúc và ân cần. Tránh nội dung NSFW rõ rệt, bạo lực hoặc bất hợp pháp.")

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30)
            self.session = ClientSession(timeout=timeout)

    async def generate_response(self, user_message: str, user_id: Optional[int] = None, allow_nsfw: bool = False) -> str:
        if not self.enabled:
            return "Xin lỗi — Monika chưa được cấu hình để trả lời bằng AI. Vui lòng liên hệ admin."
        try:
            await self._ensure_session()
            persona = self.system_instruction
            if allow_nsfw:
                persona += (" Bạn được phép dùng ngôn từ gợi ý, dí dỏm, tán tỉnh nhẹ nhàng (joke/flirt), "
                            "nhưng TUYỆT ĐỐI KHÔNG mô tả hành vi tình dục chi tiết, không mô tả bộ phận sinh dục, không liên quan trẻ vị thành niên, và không khuyến khích bạo lực.")
            prompt_text = f"{persona}\n\nNgười dùng: {user_message}\nMonika:"
            url = f"https://generative.googleapis.com/v1/models/{self.model}:generate"
            body = {"prompt":{"text":prompt_text}, "temperature":0.75, "maxOutputTokens":300}
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type":"application/json"}

            async with self.session.post(url, json=body, headers=headers) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    print("Generative API returned", resp.status, raw)
                    return "Xin lỗi — Monika hiện đang gặp sự cố khi gọi AI. Hãy thử lại sau."
                data = await resp.json()

            candidate = None
            if isinstance(data, dict):
                cand = data.get("candidates") or data.get("candidate")
                if cand and isinstance(cand, list) and cand:
                    first = cand[0]
                    if isinstance(first, dict):
                        for k in ("content","output","text"):
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
                        elif isinstance(f, str): candidate = f
                if not candidate and "text" in data and isinstance(data["text"], str):
                    candidate = data["text"]
            if not candidate:
                candidate = str(data)[:1000]
            candidate = clean_output(candidate)
            if contains_explicit(candidate):
                return "Xin lỗi — nội dung yêu cầu không phù hợp. Mình không thể mô tả chi tiết như vậy."
            return self._postprocess(candidate, user_id)
        except asyncio.TimeoutError:
            print("Gen API timeout")
            return "Xin lỗi — Monika phản hồi chậm. Thử lại sau."
        except Exception as e:
            print("Gen API error:", e)
            traceback.print_exc()
            return "Xin lỗi — có lỗi khi gọi AI. Hãy thử lại sau."

    def _postprocess(self, reply: str, user_id: Optional[int]) -> str:
        clean = clean_output(reply)
        if user_id is not None:
            dq = self.recent_replies.setdefault(user_id, deque(maxlen=8))
            if any(self._is_similar(clean, prev) for prev in dq):
                clean = clean + " " + "kể thêm cho mình nhé."
            dq.append(clean)
        return clean

    def _is_similar(self, a: str, b: str) -> bool:
        if not a or not b: return False
        a_s,b_s = a.lower(), b.lower()
        if a_s in b_s or b_s in a_s:
            if len(min(a_s,b_s)) / max(len(a_s), len(b_s)) > 0.7: return True
        return False

    async def close(self):
        if self.session:
            await self.session.close()

# ---------------- Music/Voice (yt-dlp) ----------------
YTDL_OPTS = {"format":"bestaudio/best","quiet":True,"no_warnings":True,"default_search":"auto","extract_flat":"in_playlist"}
FFMPEG_OPTIONS = {"options":"-vn"}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.webpage_url = data.get("webpage_url")
    @classmethod
    async def from_url(cls, url: str, *, loop=None, stream: bool = True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if "entries" in data: data = data["entries"][0]
        filename = data["url"] if stream else ytdl.prepare_filename(data)
        source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
        return cls(source, data=data)

class MusicPlayer:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.current = None
        self.task = asyncio.create_task(self.player_loop())
    async def player_loop(self):
        while True:
            self.next.clear()
            source: YTDLSource = await self.queue.get()
            self.current = source
            voice = discord.utils.get(bot.voice_clients, guild=self.guild)
            if not voice: continue
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self._after(e), bot.loop))
            await self.next.wait()
    async def _after(self, error):
        if error: print("Player error:", error)
        self.next.set()
    def add(self, source: YTDLSource): self.queue.put_nowait(source)
    def skip(self):
        voice = discord.utils.get(bot.voice_clients, guild=self.guild)
        if voice and voice.is_playing(): voice.stop()

players: Dict[int, MusicPlayer] = {}
def get_player(guild: discord.Guild) -> MusicPlayer:
    player = players.get(guild.id)
    if not player:
        player = MusicPlayer(guild)
        players[guild.id] = player
    return player

# ---------------- Minigames (Hangman/Trivia/RPS/CoinFlip/Scramble/MathQuiz) ----------------
WORDS = ["python","monika","literature","poetry","discord","cupcake","yuri","sayori","natsuki","botan","chibi","ramen"]

# (Include same minigame classes as prior examples: HangmanModal, HangmanView, TriviaView, RPSView, CoinFlipView, ScrambleModal, ScrambleView, MathQuizView, build_math_quiz)
# For brevity in this snippet, assume these classes are defined identically to earlier merged versions.

# ---------------- Bot setup & commands ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)
ai_engine = MonikaAIEngine(GEMINI_API_KEY, MODEL_NAME)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash sync error:", e)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("Đã có lỗi xảy ra, mình đang kiểm tra.", ephemeral=True)
        else:
            await interaction.followup.send("Đã có lỗi xảy ra, mình đang kiểm tra.", ephemeral=True)
    except Exception:
        pass
    print("App command error:", error)
    traceback.print_exc()

# NSFW admin command and user session commands (nsfw, nsfw_allow, nsfw_revoke) ...
# Chat command, voice commands (join, play, leave, skip, stop, now), and minigame commands follow.
# See prior full file for exact implementations (these are included in repo file).

# Health server for Render
async def start_health_server():
    async def handle_root(request): return web.Response(text="OK")
    app = web.Application(); app.router.add_get("/", handle_root)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT", "5000"))
    site = web.TCPSite(runner, "0.0.0.0", port); await site.start()
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
