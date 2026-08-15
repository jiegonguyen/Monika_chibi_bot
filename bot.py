#!/usr/bin/env python3
"""
bot.py - Unified Discord bot
 - Monika AI: Gemini REST async (nếu GEMINI_API_KEY) + fallback + short-term memory
 - Clean output: remove code-like fragments & programming words
 - Minigames: Hangman, Trivia, RPS, CoinFlip, Scramble, MathQuiz
 - Chess: python-chess (Unicode board), modal nhập nước, Monika moves heuristically
 - Health server (aiohttp) so Render detects PORT (if using Web Service)
USAGE:
 - Set DISCORD_BOT_TOKEN (required) and optionally GEMINI_API_KEY in env vars.
 - requirements.txt provided separately.
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

# Optional chess
try:
    import chess
    CHESS_AVAILABLE = True
except Exception:
    CHESS_AVAILABLE = False

# Load .env locally (do not commit)
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not DISCORD_TOKEN:
    print("ERROR: Missing DISCORD_BOT_TOKEN environment variable.")
    raise SystemExit(1)

# ---------------- Utilities: clean / remove programming words ----------------
PROG_TOKENS = [
    "function","variable","stacktrace","traceback","line","file",".py",
    "async","await","Exception","Traceback","Traceback (most recent call last)",
    "print(", "logger", "stack"
]
PROG_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(t) for t in PROG_TOKENS) + r')\b', re.IGNORECASE)

def remove_programming_words(text: str) -> str:
    # Replace programming tokens with empty string
    text = PROG_PATTERN.sub('', text)
    return text

def clean_output(text: str, max_len: int = 800) -> str:
    if not text:
        return ""
    # Remove code blocks and inline code
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    # Remove stacktrace-like lines
    text = re.sub(r'(?mi)^.*traceback.*$', '', text)
    text = re.sub(r'(?mi)^.*exception.*$', '', text)
    # Remove bracketed ids/hex
    text = re.sub(r'\[0x[0-9a-fA-F]+\]', '', text)
    # Remove obvious programming tokens
    text = remove_programming_words(text)
    # Replace multiple whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()
    # Truncate
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + "..."
    return text

# ---------------- Monika AI Engine (REST async with fallback & anti-repeat) ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        self.session: Optional[ClientSession] = None
        self.recent_replies: dict[int, deque] = {}  # per-user recent replies

        # persona & fallback parts
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
        # Try REST call if API key present
        if self.enabled:
            try:
                await self._ensure_session()
                url = f"https://generative.googleapis.com/v1/models/{self.model}:generate"
                prompt_text = f"{self.system_instruction}\n\nNgười dùng: {user_message}\nMonika:"
                body = {
                    "prompt": {"text": prompt_text},
                    "temperature": 0.75,
                    "maxOutputTokens": 300
                }
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                # wrap request with asyncio.wait_for to avoid long hang
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
        if not a or not b:
            return False
        a_s, b_s = a.lower(), b.lower()
        if a_s in b_s or b_s in a_s:
            if len(min(a_s, b_s)) / max(len(a_s, b_s)) > 0.7:
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
        if random.random() < 0.25:
            reply = f"{opening} {mid}{echo}"
        else:
            reply = f"{opening} {mid}, {ending}{echo}"
        # avoid repeats
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

# ---------------- Games implementations ----------------
WORDS = ["python","monika","literature","poetry","discord","cupcake","yuri","sayori","natsuki","botan","chibi","ramen"]

# Hangman
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

# Trivia
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

# RPS
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

# CoinFlip
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

# Scramble
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
            s = chars[:]
            random.shuffle(s)
            cand = "".join(s)
            if cand != "".join(chars):
                return cand
        return "".join(chars)
    def get_embed(self):
        return discord.Embed(title="🔀 Xáo chữ", description=f"Từ bị xáo: `{' '.join(self.scrambled)}`\nSố lượt: {self.attempts}", color=0x00bcd4)
    @discord.ui.button(label="Đoán từ", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction, button):
        await interaction.response.send_modal(ScrambleModal(self))

# MathQuiz
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
            for c in self.children:
                c.disabled = True
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
    while len(opts)<4:
        opts.add(ans + random.choice([-4,-3,-2,-1,1,2,3,4,5]))
    opts = list(opts); random.shuffle(opts)
    return a,b,op,opts,opts.index(ans)

# ---------------- Chess ----------------
UNICODE_PIECES = {'P':'♙','N':'♘','B':'♗','R':'♖','Q':'♕','K':'♔','p':'♟︎','n':'♞','b':'♝','r':'♜','q':'♛','k':'♚'}

def render_board_unicode(board):
    rows=[]
    for rank in range(8,0,-1):
        row=[]
        for file in range(1,9):
            sq = chess.square(file-1, rank-1)
            piece = board.piece_at(sq)
            if piece:
                row.append(UNICODE_PIECES.get(piece.symbol(), piece.symbol()))
            else:
                is_light = (rank + file) % 2 == 0
                row.append('◻️' if is_light else '◼️')
        rows.append(f"{rank} {' '.join(row)}")
    rows.append("  a b c d e f g h")
    return "```\n" + "\n".join(rows) + "\n```"

class ChessMoveModal(discord.ui.Modal, title="Nhập nước đi (ví dụ: e2e4 hoặc Nf3)"):
    move_input = discord.ui.TextInput(label="Nước đi", placeholder="Nhập nước đi", max_length=10, min_length=2)
    def __init__(self, view):
        super().__init__()
        self.view_ref = view
    async def on_submit(self, interaction):
        mv_text = self.move_input.value.strip()
        success,msg = self.view_ref.try_player_move(mv_text)
        if success:
            embed = self.view_ref.get_embed()
            if self.view_ref.board.is_game_over():
                for c in self.view_ref.children:
                    c.disabled = True
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        else:
            await interaction.response.send_message(f"Không hợp lệ: {msg}", ephemeral=True)

class ChessView(discord.ui.View):
    def __init__(self, white_player_id):
        super().__init__(timeout=600)
        if not CHESS_AVAILABLE:
            raise RuntimeError("python-chess chưa cài.")
        self.board = chess.Board()
        self.white = white_player_id
        self.last_move_str = ""
        self.result_message = None
    def get_embed(self):
        title = "♟️ Trận Cờ cùng Monika"
        if self.board.is_checkmate(): title = "♚ Checkmate!"
        embed = discord.Embed(title=title, color=0x8b0000)
        embed.add_field(name="Bàn cờ", value=render_board_unicode(self.board), inline=False)
        embed.add_field(name="Lượt", value="Trắng (bạn)" if self.board.turn==chess.WHITE else "Đen (Monika)", inline=True)
        if self.last_move_str:
            embed.set_footer(text=f"Nước đi trước: {self.last_move_str}")
        if self.result_message:
            embed.add_field(name="Kết quả", value=self.result_message, inline=False)
        return embed
    def try_player_move(self, mv_text):
        try:
            try:
                move = self.board.parse_san(mv_text)
            except Exception:
                move = chess.Move.from_uci(mv_text)
            if move not in self.board.legal_moves:
                return False, "Nước đi không hợp lệ."
            self.board.push(move)
            self.last_move_str = move.uci()
            if not self.board.is_game_over():
                self.monika_move()
            else:
                self._update_result()
            return True, "Ok"
        except Exception as e:
            return False, str(e)
    def monika_move(self):
        legal = list(self.board.legal_moves)
        capture_moves=[]
        for m in legal:
            if self.board.is_capture(m):
                to_sq = m.to_square
                captured = self.board.piece_at(to_sq)
                val = 0
                if captured:
                    vals={'p':1,'n':3,'b':3,'r':5,'q':9,'k':100}
                    val = vals.get(captured.symbol().lower(),0)
                capture_moves.append((val, m))
        if capture_moves:
            capture_moves.sort(key=lambda x:(-x[0], random.random()))
            chosen = capture_moves[0][1]
        else:
            chosen = random.choice(legal)
        self.board.push(chosen)
        self.last_move_str = chosen.uci()
        if self.board.is_game_over():
            self._update_result()
    def _update_result(self):
        if self.board.is_checkmate():
            if self.board.turn==chess.WHITE:
                self.result_message = "Monika thắng bằng chiếu hết."
            else:
                self.result_message = "Bạn đã thắng bằng chiếu hết. Chúc mừng!"
        elif self.board.is_stalemate():
            self.result_message = "Hòa (Stalemate)."
        elif self.board.is_insufficient_material():
            self.result_message = "Hòa (Insufficient material)."
        else:
            self.result_message = "Kết thúc: " + str(self.board.result())
    @discord.ui.button(label="Nhập nước", style=discord.ButtonStyle.primary)
    async def enter_move(self, interaction, button):
        # do not defer if opening modal; send_modal directly
        if interaction.user.id != self.white:
            await interaction.response.send_message("Chỉ người bắt đầu ván mới được đi.", ephemeral=True)
            return
        await interaction.response.send_modal(ChessMoveModal(self))
    @discord.ui.button(label="Đầu hàng", style=discord.ButtonStyle.danger)
    async def resign(self, interaction, button):
        for c in self.children:
            c.disabled = True
        self.result_message = "Bạn đã đầu hàng. Monika mỉm cười..."
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
        self.stop()

# ---------------- Bot setup & commands ----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
ai_engine = MonikaAIEngine(GEMINI_API_KEY, MODEL_NAME)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Đã đồng bộ {len(synced)} lệnh slash.")
    except Exception as e:
        print("Lỗi sync lệnh slash:", e)

# Chat command: defer (ack) early, then call AI with timeout; clean output and send
@bot.tree.command(name="chat", description="Trò chuyện cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    try:
        # call with timeout to avoid blocking too long
        reply = await asyncio.wait_for(ai_engine.generate_response(message, user_id=interaction.user.id), timeout=25)
    except asyncio.TimeoutError:
        reply = "Ừm... tớ mất chút thời gian. Hãy thử gửi lại nhé."
    except Exception as e:
        print("AI call error:", e)
        reply = "Có chút vấn đề khi kết nối AI, nhưng tớ vẫn ở đây nhé."
    reply = clean_output(reply)
    await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}")

# Other slash commands
@bot.tree.command(name="chess", description="Đấu cờ vua cùng Monika")
async def chess_cmd(interaction: discord.Interaction):
    if not CHESS_AVAILABLE:
        await interaction.response.send_message("Trò Cờ Vua cần python-chess (cài trong requirements).", ephemeral=True)
        return
    view = ChessView(interaction.user.id)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="hangman", description="Chơi Hangman")
async def hangman_cmd(interaction: discord.Interaction):
    view = HangmanView(random.choice(WORDS))
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="trivia", description="Chơi Trivia")
async def trivia_cmd(interaction: discord.Interaction):
    view = TriviaView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="rps", description="Chơi Kéo-Búa-Bao")
async def rps_cmd(interaction: discord.Interaction):
    view = RPSView()
    await interaction.response.send_message(embed=discord.Embed(title="✂️ Oẳn Tù Tì", description="Chọn lựa chọn nhé:"), view=view)

@bot.tree.command(name="coinflip", description="Tung đồng xu")
async def coinflip_cmd(interaction: discord.Interaction):
    view = CoinFlipView()
    await interaction.response.send_message(embed=discord.Embed(title="🪙 Tung đồng xu", description="Chọn Ngửa hoặc Sấp:"), view=view)

@bot.tree.command(name="scramble", description="Xáo chữ: đoán từ")
async def scramble_cmd(interaction: discord.Interaction):
    secret = random.choice(WORDS)
    view = ScrambleView(secret)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="mathquiz", description="Toán nhanh nhiều lựa chọn")
async def mathquiz_cmd(interaction: discord.Interaction):
    a,b,op,opts,ans_idx = build_math_quiz()
    view = MathQuizView(a,b,op,opts,ans_idx)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="helps", description="Hiển thị trợ giúp")
async def helps_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Danh sách lệnh", color=0x00ffcc)
    embed.add_field(name="/chat <message>", value="Trò chuyện với Monika AI", inline=False)
    embed.add_field(name="/chess", value="Đấu cờ vua cùng Monika", inline=False)
    embed.add_field(name="/hangman", value="Chơi Hangman", inline=False)
    embed.add_field(name="/trivia", value="Chơi Trivia", inline=False)
    embed.add_field(name="/rps", value="Chơi Kéo-Búa-Bao", inline=False)
    embed.add_field(name="/coinflip", value="Tung đồng xu", inline=False)
    embed.add_field(name="/scramble", value="Xáo chữ", inline=False)
    embed.add_field(name="/mathquiz", value="Toán nhanh", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- Health server for Render ----------------
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

# ---------------- Run ----------------
async def main():
    await start_health_server()
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await ai_engine.close()
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
