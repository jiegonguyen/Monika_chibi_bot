#!/usr/bin/env python3
"""
bot.py - Monika AI (Gemini REST) + minigames + voice music + soft-NSFW (session-based)
Environment variables:
 - DISCORD_BOT_TOKEN (required)
 - GEMINI_API_KEY (optional)
 - GEMINI_MODEL (optional, default gemini-2.5-flash)

Files:
 - nsfw_settings.json  (per-guild enabled/disabled)
 - nsfw_attempts.log   (append-only logs of NSFW attempts)

Notes:
 - No fallback/simulated replies. If Gemini not configured or API fails, Monika returns a polite error message.
 - For voice/music, ensure ffmpeg and PyNaCl available (use provided Dockerfile for Render).
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

# audio extraction
import yt_dlp

# Load env (local dev)
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not DISCORD_TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN not set")
    raise SystemExit(1)

# Check voice library availability (PyNaCl)
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

# active sessions: key = (guild_id_or_DM, channel_id_or_DM, user_id) -> expiry (loop time)
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

# ---------------- Utilities: clean & safety ----------------
PROG_TOKENS = [
    "function","variable","stacktrace","traceback","line","file",".py",
    "async","await","Exception","Traceback","print(","logger","<class>"
]
PROG_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(t) for t in PROG_TOKENS) + r')\b', re.IGNORECASE)

def remove_programming_words(text: str) -> str:
    return PROG_PATTERN.sub("", text)

def clean_output(text: str, max_len: int = 800) -> str:
    if not text:
        return ""
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

EXPLICIT_TOKENS = [
    "sex","tình dục","quan hệ","âm đạo","dương vật","bú","thổi","oral","anal",
    "fuck","suck","porn","pussy","penis","vagina","masturb","rape","ngực",
    "vú","lồn","địt","zịt"
]
EXPLICIT_RE = re.compile(r'\b(' + '|'.join(re.escape(t) for t in EXPLICIT_TOKENS) + r')\b', re.IGNORECASE)

def contains_explicit(text: str) -> bool:
    if not text:
        return False
    return bool(EXPLICIT_RE.search(text))

# ---------------- Monika AI Engine (NO fallback) ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        self.session: Optional[ClientSession] = None
        self.recent_replies: Dict[int, deque] = {}

        self.system_instruction = (
            "Bạn là Monika: dịu dàng, sâu sắc, thân mật nhưng lịch sự. Trả lời bằng tiếng Việt, "
            "ngắn gọn (1-3 câu), giàu cảm xúc và ân cần. Tránh nội dung NSFW rõ rệt, bạo lực hoặc bất hợp pháp."
        )

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30)
            self.session = ClientSession(timeout=timeout)

    async def generate_response(self, user_message: str, user_id: Optional[int] = None, allow_nsfw: bool = False) -> str:
        """
        Use Gemini REST to generate response. No simulated fallback.
        If API is not configured or call fails, return a polite standard error message.
        """
        if not self.enabled:
            return "Xin lỗi — Monika chưa được cấu hình để trả lời bằng AI. Vui lòng liên hệ admin."

        try:
            await self._ensure_session()
            persona = self.system_instruction
            if allow_nsfw:
                persona += (
                    " Bạn được phép dùng ngôn từ gợi ý, dí dỏm, tán tỉnh nhẹ nhàng (joke/flirt), "
                    "nhưng TUYỆT ĐỐI KHÔNG mô tả hành vi tình dục chi tiết, không mô tả bộ phận sinh dục, không liên quan trẻ vị thành niên, và không khuyến khích bạo lực hay phi pháp."
                )
            prompt_text = f"{persona}\n\nNgười dùng: {user_message}\nMonika:"
            url = f"https://generative.googleapis.com/v1/models/{self.model}:generate"
            body = {"prompt": {"text": prompt_text}, "temperature": 0.75, "maxOutputTokens": 300}
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

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
                            if isinstance(msg, str):
                                candidate = msg
                    elif isinstance(first, str):
                        candidate = first
                if not candidate and "output" in data:
                    out = data["output"]
                    if isinstance(out, list) and out:
                        f = out[0]
                        if isinstance(f, dict):
                            c = f.get("content")
                            if isinstance(c, str):
                                candidate = c
                        elif isinstance(f, str):
                            candidate = f
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
                # add a short variant
                clean = clean + " " + "kể thêm cho mình nhé."
            dq.append(clean)
        return clean

    def _is_similar(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        a_s, b_s = a.lower(), b.lower()
        if a_s in b_s or b_s in a_s:
            if len(min(a_s, b_s)) / max(len(a_s), len(b_s)) > 0.7:
                return True
        return False

    async def close(self):
        if self.session:
            await self.session.close()

# ---------------- Music/Voice (yt-dlp + ffmpeg) ----------------
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
        if "entries" in data:
            data = data["entries"][0]
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
            if not voice:
                continue
            voice.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self._after(e), bot.loop))
            await self.next.wait()
    async def _after(self, error):
        if error:
            print("Player error:", error)
        self.next.set()
    def add(self, source: YTDLSource):
        self.queue.put_nowait(source)
    def skip(self):
        voice = discord.utils.get(bot.voice_clients, guild=self.guild)
        if voice and voice.is_playing():
            voice.stop()

players: Dict[int, MusicPlayer] = {}
def get_player(guild: discord.Guild) -> MusicPlayer:
    player = players.get(guild.id)
    if not player:
        player = MusicPlayer(guild)
        players[guild.id] = player
    return player

# ---------------- Minigames (Hangman/Trivia/RPS/CoinFlip/Scramble/MathQuiz) ----------------
WORDS = ["python","monika","literature","poetry","discord","cupcake","yuri","sayori","natsuki","botan","chibi","ramen"]

class HangmanModal(discord.ui.Modal, title="Nhập chữ cái bạn muốn đoán"):
    letter_input = discord.ui.TextInput(label="Chữ cái (a-z)", placeholder="Nhập 1 ký tự...", max_length=1, min_length=1)
    def __init__(self, game_view):
        super().__init__()
        self.game_view = game_view
    async def on_submit(self, interaction: discord.Interaction):
        char = self.letter_input.value.lower()
        if char in self.game_view.guessed_letters:
            await interaction.response.send_message("Cậu đã đoán chữ này rồi!", ephemeral=True)
            return
        self.game_view.guessed_letters.add(char)
        if char in self.game_view.secret_word:
            for idx, letter in enumerate(self.game_view.secret_word):
                if letter == char:
                    self.game_view.current_display[idx] = char
            if "_" not in self.game_view.current_display:
                embed = self.game_view.get_embed()
                embed.title = "🎉 Tuyệt vời! Cậu đã đoán đúng rồi!"
                for child in self.game_view.children:
                    child.disabled = True
                await interaction.response.edit_message(embed=embed, view=self.game_view)
                return
            await interaction.response.edit_message(embed=self.game_view.get_embed(), view=self.game_view)
        else:
            self.game_view.remaining_attempts -= 1
            if self.game_view.remaining_attempts <= 0:
                embed = self.game_view.get_embed()
                embed.title = f"😢 Hết lượt! Từ đúng là: **{self.game_view.secret_word}**"
                for child in self.game_view.children:
                    child.disabled = True
                await interaction.response.edit_message(embed=embed, view=self.game_view)
                return
            await interaction.response.edit_message(embed=self.game_view.get_embed(), view=self.game_view)

class HangmanView(discord.ui.View):
    def __init__(self, secret_word: str):
        super().__init__(timeout=180)
        self.secret_word = secret_word.lower()
        self.guessed_letters = set()
        self.remaining_attempts = 6
        self.current_display = ["_" for _ in self.secret_word]
    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🌿 Hangman cùng Monika", description=f"`{' '.join(self.current_display)}`", color=0xff69b4)
        embed.add_field(name="Lượt sai còn lại", value=str(self.remaining_attempts), inline=True)
        embed.add_field(name="Chữ đã đoán", value=", ".join(sorted(self.guessed_letters)) or "Chưa có", inline=True)
        return embed
    @discord.ui.button(label="Đoán chữ cái", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HangmanModal(self))

QUESTIONS = [
    {"question":"Trong Doki Doki Literature Club, ai là chủ tịch câu lạc bộ văn học?", "options":["Sayori","Natsuki","Monika","Yuri"], "answer":2},
    {"question":"Tốc độ ánh sáng xấp xỉ bao nhiêu km/s?", "options":["300,000","150,000","1,000,000","450,000"], "answer":0},
    {"question":"Nguyên tố có ký hiệu 'Mg' là?", "options":["Mangan","Magie","Mercury","Molybdenum"], "answer":1},
]
class TriviaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.q_data = random.choice(QUESTIONS)
        for idx, option in enumerate(self.q_data["options"]):
            btn = discord.ui.Button(label=f"{chr(65+idx)}. {option}", style=discord.ButtonStyle.secondary)
            btn.callback = self.create_callback(idx)
            self.add_item(btn)
    def create_callback(self, index:int):
        async def cb(interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
            if index == self.q_data["answer"]:
                await interaction.response.edit_message(content="✅ **Chính xác!**", view=self)
            else:
                correct = self.q_data["options"][self.q_data["answer"]]
                await interaction.response.edit_message(content=f"❌ **Sai!** Đáp án đúng: **{correct}**", view=self)
            self.stop()
        return cb
    def get_embed(self):
        return discord.Embed(title="📚 Đố vui cùng Monika", description=self.q_data["question"], color=0xff1493)

class RPSView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="✊ Búa", style=discord.ButtonStyle.primary)
    async def rock(self, interaction, button):
        await self._play(interaction, "Búa")
    @discord.ui.button(label="✋ Bao", style=discord.ButtonStyle.primary)
    async def paper(self, interaction, button):
        await self._play(interaction, "Bao")
    @discord.ui.button(label="✌️ Kéo", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction, button):
        await self._play(interaction, "Kéo")
    async def _play(self, interaction, user_choice):
        for c in self.children:
            c.disabled = True
        choices = ["Búa","Bao","Kéo"]
        monika_choice = random.choice(choices)
        if user_choice == monika_choice:
            result = "Hòa rồi — thật đặc biệt khi hiểu nhau đến vậy."
        elif (user_choice=="Búa" and monika_choice=="Kéo") or (user_choice=="Bao" and monika_choice=="Búa") or (user_choice=="Kéo" and monika_choice=="Bao"):
            result = "🎉 Cậu thắng! Mình thích nhìn nụ cười của cậu."
        else:
            result = "🤭 Lần sau tớ nhường nhé."
        embed = discord.Embed(title="✂️ Oẳn Tù Tì", description=f"Cậu: **{user_choice}**\nMonika: **{monika_choice}**\n\n{result}", color=0x9932cc)
        await interaction.response.edit_message(embed=embed, view=self)

class CoinFlipView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="🪙 Ngửa", style=discord.ButtonStyle.success)
    async def heads(self, interaction, button):
        await self._flip(interaction, "Ngửa")
    @discord.ui.button(label="🪙 Sấp", style=discord.ButtonStyle.danger)
    async def tails(self, interaction, button):
        await self._flip(interaction, "Sấp")
    async def _flip(self, interaction, guess):
        for c in self.children:
            c.disabled = True
        result = random.choice(["Ngửa","Sấp"])
        msg = f"✨ Kết quả: **{result}**. " + ("Bạn đoán đúng!" if guess==result else "Thua rồi, thử lại nhé.")
        embed = discord.Embed(title="🪙 Tung Đồng Xu", description=msg, color=0xffd700)
        await interaction.response.edit_message(embed=embed, view=self)

class ScrambleModal(discord.ui.Modal, title="Đoán từ"):
    guess = discord.ui.TextInput(label="Đoán từ", placeholder="Nhập đáp án", min_length=1, max_length=50)
    def __init__(self, view):
        super().__init__()
        self.view_ref = view
    async def on_submit(self, interaction):
        text = self.guess.value.strip().lower()
        if text == self.view_ref.secret_word:
            embed = self.view_ref.get_embed()
            embed.title = "🎉 Đúng rồi!"
            for c in self.view_ref.children:
                c.disabled = True
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        else:
            self.view_ref.attempts -= 1
            if self.view_ref.attempts <= 0:
                embed = self.view_ref.get_embed()
                embed.title = f"😢 Hết lượt! Từ đúng: **{self.view_ref.secret_word}**"
                for c in self.view_ref.children:
                    c.disabled = True
                await interaction.response.edit_message(embed=embed, view=self.view_ref)
            else:
                await interaction.response.edit_message(embed=self.view_ref.get_embed(), view=self.view_ref)

class ScrambleView(discord.ui.View):
    def __init__(self, secret_word):
        super().__init__(timeout=180)
        self.secret_word = secret_word.lower()
        chars = list(self.secret_word)
        if len(set(chars)) == 1:
            scrambled = "".join(chars)
        else:
            scrambled = self._scramble_once(chars)
        self.scrambled = scrambled
        self.attempts = max(3, len(secret_word)//2)
    def _scramble_once(self, chars):
        for _ in range(30):
            s = chars[:]; random.shuffle(s); cand = "".join(s)
            if cand != "".join(chars): return cand
        return "".join(chars)
    def get_embed(self):
        return discord.Embed(title="🔀 Xáo chữ", description=f"Từ bị xáo: `{' '.join(self.scrambled)}`\nSố lượt: {self.attempts}", color=0x00bcd4)
    @discord.ui.button(label="Đoán từ", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction, button):
        await interaction.response.send_modal(ScrambleModal(self))

class MathQuizView(discord.ui.View):
    def __init__(self, a,b,op,options,answer_index):
        super().__init__(timeout=60)
        self.answer_index = answer_index
        self.question = f"{a} {op} {b}"
        for idx,val in enumerate(options):
            btn = discord.ui.Button(label=str(val), style=discord.ButtonStyle.secondary)
            btn.callback = self.create_cb(idx)
            self.add_item(btn)
    def create_cb(self, idx):
        async def cb(interaction):
            for c in self.children: c.disabled = True
            if idx == self.answer_index:
                await interaction.response.edit_message(content="✅ **Chính xác!**", view=self)
            else:
                correct = self.children[self.answer_index].label
                await interaction.response.edit_message(content=f"❌ Sai! Đáp án đúng: **{correct}**", view=self)
            self.stop()
        return cb
    def get_embed(self):
        return discord.Embed(title="🧠 Toán nhỏ cùng Monika", description=f"Hãy tính: **{self.question}**", color=0xff5722)

def build_math_quiz():
    a = random.randint(2,12); b = random.randint(2,12); op = random.choice(["+","-","*"])
    if op=="+": ans=a+b
    elif op=="-": ans=a-b
    else: ans=a*b
    opts = {ans}
    while len(opts)<4: opts.add(ans + random.choice([-4,-3,-2,-1,1,2,3,4,5]))
    opts = list(opts); random.shuffle(opts)
    return a,b,op,opts,opts.index(ans)

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

# Admin NSFW enable/disable
@bot.tree.command(name="nsfw", description="Quản lý chế độ soft-NSFW cho server (admin only)")
@discord.app_commands.describe(action="enable / disable / status")
async def nsfw_toggle(interaction: discord.Interaction, action: str):
    if interaction.guild is None:
        await interaction.response.send_message("Lệnh này chỉ dùng trong server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Chỉ quản trị viên mới có thể thay đổi.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    a = action.lower()
    if a in ("enable","on"):
        nsfw_settings[guild_id] = {"enabled": True}
        save_nsfw_settings(nsfw_settings)
        await interaction.response.send_message("Đã bật chế độ soft-NSFW cho server. Người dùng cần /nsfw_allow để mở phiên NSFW.", ephemeral=False)
    elif a in ("disable","off"):
        nsfw_settings[guild_id] = {"enabled": False}
        save_nsfw_settings(nsfw_settings)
        await interaction.response.send_message("Đã tắt chế độ soft-NSFW cho server.", ephemeral=True)
    elif a in ("status","check"):
        s = nsfw_settings.get(guild_id, {}).get("enabled", False)
        await interaction.response.send_message(f"NSFW enabled: {s}", ephemeral=True)
    else:
        await interaction.response.send_message("Tham số không hợp lệ. Dùng: enable / disable / status.", ephemeral=True)

# User-level NSFW session allow/revoke
@bot.tree.command(name="nsfw_allow", description="Cho phép soft-NSFW cho bạn tại kênh này trong X phút (yêu cầu admin bật server NSFW)")
@discord.app_commands.describe(minutes="Số phút cho phiên (mặc định 10)")
async def nsfw_allow(interaction: discord.Interaction, minutes: Optional[int] = 10):
    if interaction.guild:
        guild_id = str(interaction.guild.id)
        if not nsfw_settings.get(guild_id, {}).get("enabled", False):
            await interaction.response.send_message("NSFW chưa được bật cho server này (admin cần dùng /nsfw enable).", ephemeral=True)
            return
    set_nsfw_session(getattr(interaction.guild, "id", None), getattr(interaction.channel, "id", None), interaction.user.id, minutes=minutes or 10)
    await interaction.response.send_message(f"Đã bật soft-NSFW cho bạn trong {minutes or 10} phút ở kênh này.", ephemeral=True)

@bot.tree.command(name="nsfw_revoke", description="Thu hồi phiên soft-NSFW của bạn ở kênh này ngay lập tức")
async def nsfw_revoke(interaction: discord.Interaction):
    revoke_nsfw_session(getattr(interaction.guild, "id", None), getattr(interaction.channel, "id", None), interaction.user.id)
    await interaction.response.send_message("Đã thu hồi phiên NSFW của bạn ở kênh này.", ephemeral=True)

def is_nsfw_allowed_for_interaction(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return is_nsfw_session_active(interaction)
    guild_id = str(interaction.guild.id)
    if not nsfw_settings.get(guild_id, {}).get("enabled", False):
        return False
    return is_nsfw_session_active(interaction)

# Chat command
@bot.tree.command(name="chat", description="Trò chuyện cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    allow_nsfw = is_nsfw_allowed_for_interaction(interaction)
    try:
        reply = await asyncio.wait_for(ai_engine.generate_response(message, user_id=interaction.user.id, allow_nsfw=allow_nsfw), timeout=25)
    except asyncio.TimeoutError:
        reply = "Xin lỗi — Monika hiện phản hồi chậm. Thử lại sau."
    except Exception as e:
        print("AI error:", e)
        traceback.print_exc()
        reply = "Xin lỗi — có lỗi khi gọi AI. Hãy thử lại sau."
    # if session allowed and explicit content in either user or generated, log + refuse
    if allow_nsfw and (contains_explicit(message) or contains_explicit(reply)):
        log_nsfw_attempt(interaction, message, reply)
        reply = "Mình không thể mô tả chi tiết như vậy. Hãy giữ câu chuyện ở tông nhẹ nhàng hoặc hài hước nhé."
    reply = clean_output(reply)
    await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}")

# Voice/music commands with capability checks
@bot.tree.command(name="join", description="Kêu bot vào voice channel của bạn")
async def join(interaction: discord.Interaction):
    if not VOICE_LIB_AVAILABLE:
        await interaction.response.send_message("Voice không khả dụng: PyNaCl chưa cài. Hãy cài PyNaCl hoặc dùng Docker image có PyNaCl/ffmpeg.", ephemeral=True)
        return
    if not interaction.user.voice:
        await interaction.response.send_message("Bạn chưa vào voice channel.", ephemeral=True)
        return
    channel = interaction.user.voice.channel
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice and voice.is_connected():
        await interaction.response.send_message("Bot đã có trong voice channel.", ephemeral=True)
        return
    await interaction.response.defer()
    try:
        await channel.connect()
        await interaction.followup.send(f"Đã vào voice channel: **{channel.name}**")
    except Exception as e:
        print("Join error:", e)
        traceback.print_exc()
        msg = str(e)
        hint = ("Kiểm tra ffmpeg và PyNaCl. Trên Render hãy dùng Dockerfile có ffmpeg, và set PyNaCl trong requirements.")
        await interaction.followup.send(f"Không thể kết nối voice: {msg}\n\n{hint}", ephemeral=True)

@bot.tree.command(name="leave", description="Cho bot rời voice channel")
async def leave(interaction: discord.Interaction):
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice or not voice.is_connected():
        await interaction.response.send_message("Bot không ở trong voice channel.", ephemeral=True)
        return
    await interaction.response.defer()
    try:
        await voice.disconnect()
        await interaction.followup.send("Đã rời voice channel.")
    except Exception as e:
        print("Leave error:", e)
        traceback.print_exc()
        await interaction.followup.send(f"Không thể tháo bot: {e}", ephemeral=True)

@bot.tree.command(name="play", description="Phát nhạc từ URL hoặc tìm kiếm (YouTube).")
async def play(interaction: discord.Interaction, query: str):
    if not VOICE_LIB_AVAILABLE:
        await interaction.response.send_message("Voice không khả dụng: PyNaCl chưa cài. Hãy cài PyNaCl và ffmpeg (Docker recommended).", ephemeral=True)
        return
    if not interaction.user.voice:
        await interaction.response.send_message("Bạn phải ở trong voice channel để phát nhạc.", ephemeral=True)
        return
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice or not voice.is_connected():
        channel = interaction.user.voice.channel
        await interaction.response.defer()
        try:
            await channel.connect()
            voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        except Exception as e:
            print("Connect error:", e)
            traceback.print_exc()
            await interaction.followup.send("Không thể kết nối voice. Hãy kiểm tra ffmpeg/PyNaCl.", ephemeral=True)
            return
    else:
        await interaction.response.defer()
    try:
        source = await YTDLSource.from_url(query, loop=asyncio.get_event_loop(), stream=True)
    except Exception as e:
        print("YTDL error:", e)
        traceback.print_exc()
        await interaction.followup.send("Không tải được media, thử URL khác hoặc kiểm tra ffmpeg.", ephemeral=True)
        return
    player = get_player(interaction.guild)
    player.add(source)
    await interaction.followup.send(f"Đã thêm vào queue: **{source.title}**")

@bot.tree.command(name="skip", description="Chuyển qua bài tiếp theo")
async def skip(interaction: discord.Interaction):
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice or not voice.is_playing():
        await interaction.response.send_message("Không có bài đang phát.", ephemeral=True)
        return
    await interaction.response.defer()
    voice.stop()
    await interaction.followup.send("Đã chuyển bài.")

@bot.tree.command(name="stop", description="Dừng phát và xóa queue")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()
    players.pop(interaction.guild.id, None)
    voice = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice and voice.is_connected():
        voice.stop()
    await interaction.followup.send("Dừng phát và xóa queue.")

@bot.tree.command(name="now", description="Xem bài đang phát")
async def now(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    if player and player.current:
        await interaction.response.send_message(f"Đang phát: **{getattr(player.current, 'title', 'Unknown')}**")
    else:
        await interaction.response.send_message("Chưa có bài nào đang phát.", ephemeral=True)

# Minigame commands
@bot.tree.command(name="hangman", description="Chơi Hangman")
async def cmd_hangman(interaction: discord.Interaction):
    view = HangmanView(random.choice(WORDS))
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="trivia", description="Chơi Trivia")
async def cmd_trivia(interaction: discord.Interaction):
    view = TriviaView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="rps", description="Chơi Kéo-Búa-Bao")
async def cmd_rps(interaction: discord.Interaction):
    view = RPSView()
    await interaction.response.send_message(embed=discord.Embed(title="✂️ Oẳn Tù Tì", description="Chọn lựa chọn nhé:"), view=view)

@bot.tree.command(name="coinflip", description="Tung đồng xu")
async def cmd_coinflip(interaction: discord.Interaction):
    view = CoinFlipView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="scramble", description="Xáo chữ: đoán từ")
async def cmd_scramble(interaction: discord.Interaction):
    secret = random.choice(WORDS)
    view = ScrambleView(secret)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="mathquiz", description="Toán nhanh nhiều lựa chọn")
async def cmd_math(interaction: discord.Interaction):
    a,b,op,opts,ans_idx = build_math_quiz()
    view = MathQuizView(a,b,op,opts,ans_idx)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

# Health server for Render (optional)
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
