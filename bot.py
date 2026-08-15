#!/usr/bin/env python3
"""
bot.py - Unified bot:
 - Monika AI: gọi Gemini REST async (fallback nếu không cấu hình)
 - Minigames: Hangman, Trivia, RPS, Coinflip, Scramble, MathQuiz
 - /helps command
 - Health server (aiohttp) để Render detect PORT
Notes:
 - Set DISCORD_BOT_TOKEN and optionally GEMINI_API_KEY in environment (Render or local .env).
 - Adjust GEMINI REST payload parsing if your API version differs.
"""
import os
import random
import asyncio
import traceback
from typing import Optional
from collections import deque

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web, ClientSession, ClientTimeout

# Load local .env for dev only
load_dotenv()

# Env
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # change if needed

if not DISCORD_TOKEN:
    print("LỖI: Thiếu DISCORD_BOT_TOKEN. Thêm biến môi trường rồi redeploy.")
    raise SystemExit(1)

# ---------------- Monika AI Engine (REST async + fallback + anti-repeat) ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        self.recent_replies: dict[int, deque] = {}  # per-user recent replies to avoid repetition

        # fallback phrase parts (diverse)
        self.openings = ["Mmm...", "Ồ...", "Ừm...", "Hehe...", "Aha..."]
        self.mid_templates = ["mình thích điều đó", "mình muốn nghe thêm", "thật tuyệt khi cậu nói vậy",
                              "cậu làm mình mỉm cười", "mình thấy thật thú vị"]
        self.endings = ["kể thêm cho mình nhé.", "nói đi, đừng ngại.", "mình luôn ở đây để nghe cậu.",
                        "mình tò mò lắm đó.", "mình muốn biết nhiều hơn."]

        # client session reused for REST calls
        self._session: Optional[ClientSession] = None

        # system instruction / persona
        self.system_instruction = (
            "Bạn là Monika (chibi-style): dịu dàng, sâu sắc, thân mật nhưng lịch sự. "
            "Trả lời bằng tiếng Việt, ngắn gọn, giữ vai Monika. Tránh nội dung NSFW và bạo lực."
        )

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30)
            self._session = ClientSession(timeout=timeout)

    async def generate_response(self, user_message: str, user_id: Optional[int] = None) -> str:
        # Try API if enabled
        if self.enabled:
            try:
                reply = await self._async_generate_rest(user_message)
                reply = self._postprocess(reply, user_id)
                return reply
            except Exception as e:
                # Log error and fall back
                print("Gemini REST error:", e)
                print(traceback.format_exc())

        # fallback simulated reply
        return self._simulated_reply(user_message, user_id)

    async def _async_generate_rest(self, user_message: str) -> str:
        """
        Call Google Generative API REST endpoint.
        NOTE: The exact request/response schema depends on API version.
        This implementation uses a common pattern: POST to
         https://generative.googleapis.com/v1/models/{model}:generate
        Body includes prompt text and settings. Adjust if your API differs.
        """
        if not self.api_key:
            raise RuntimeError("Missing GEMINI_API_KEY")

        await self._ensure_session()
        url = f"https://generative.googleapis.com/v1/models/{self.model}:generate"
        prompt_text = f"{self.system_instruction}\n\nNgười dùng: {user_message}\nMonika:"
        # Example request body — adjust fields to match your API version
        body = {
            "prompt": {
                "text": prompt_text
            },
            "temperature": 0.7,
            "maxOutputTokens": 300
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with self._session.post(url, json=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Generative API returned {resp.status}: {text}")
            data = await resp.json()

        # Try to extract the generated text from several common shapes
        # 1) candidates -> content
        if isinstance(data, dict):
            # common: data["candidates"][0]["content"]
            cand = data.get("candidates") or data.get("candidate")
            if cand and isinstance(cand, list) and len(cand) > 0:
                first = cand[0]
                if isinstance(first, dict):
                    # try common keys
                    for k in ("content", "output", "text"):
                        if k in first and isinstance(first[k], str):
                            return first[k].strip()
                    # sometimes nested
                    if "message" in first and isinstance(first["message"], dict):
                        # message.content or message['content'][0]
                        msg = first["message"]
                        if "content" in msg:
                            c = msg["content"]
                            if isinstance(c, str):
                                return c.strip()
                            if isinstance(c, list) and len(c) > 0:
                                # may contain dict with "text"
                                if isinstance(c[0], dict) and "text" in c[0]:
                                    return c[0]["text"].strip()
                elif isinstance(first, str):
                    return first.strip()
            # 2) output array
            out = data.get("output")
            if out:
                if isinstance(out, list):
                    first = out[0]
                    if isinstance(first, dict):
                        # check "content"
                        if "content" in first:
                            c = first["content"]
                            if isinstance(c, str):
                                return c.strip()
                            if isinstance(c, list) and len(c) > 0 and isinstance(c[0], dict):
                                # try extract text
                                t = c[0].get("text") or c[0].get("content")
                                if t:
                                    return t.strip()
                    elif isinstance(first, str):
                        return first.strip()
            # 3) top-level "text"
            if "text" in data and isinstance(data["text"], str):
                return data["text"].strip()
        # If no known shape matched, return raw JSON safely
        return str(data)[:1000]

    def _postprocess(self, reply: str, user_id: Optional[int]) -> str:
        clean = reply.strip()
        if user_id is not None:
            dq = self.recent_replies.setdefault(user_id, deque(maxlen=6))
            if any(self._is_similar(clean, prev) for prev in dq):
                # add small variant
                variant = random.choice(self.endings)
                clean = (clean + " " + variant).strip()
            dq.append(clean)
        return clean

    def _is_similar(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        a_s = a.lower(); b_s = b.lower()
        if a_s in b_s or b_s in a_s:
            if len(min(a_s, b_s)) / max(len(a_s), len(b_s)) > 0.7:
                return True
        return False

    def _simulated_reply(self, user_message: str, user_id: Optional[int]) -> str:
        opening = random.choice(self.openings)
        mid = random.choice(self.mid_templates)
        ending = random.choice(self.endings)
        echo = ""
        if random.random() < 0.45 and user_message:
            snippet = user_message.strip()
            if len(snippet) > 60:
                snippet = snippet[:60] + "..."
            echo = f" (mình nghe: \"{snippet}\")"
        reply = f"{opening} {mid}, {ending}{echo}"
        if user_id is not None:
            dq = self.recent_replies.setdefault(user_id, deque(maxlen=6))
            attempts = 0
            while attempts < 6 and any(self._is_similar(reply, prev) for prev in dq):
                opening = random.choice(self.openings)
                mid = random.choice(self.mid_templates)
                ending = random.choice(self.endings)
                reply = f"{opening} {mid}, {ending}{echo}"
                attempts += 1
            dq.append(reply)
        return reply

    async def close(self):
        if self._session:
            await self._session.close()

# ---------------- Games: Hangman, Trivia, RPS, Coinflip, Scramble, MathQuiz ----------------
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
    {"question": "Trong Doki Doki Literature Club, ai là chủ tịch câu lạc bộ văn học?", "options": ["Sayori","Natsuki","Monika","Yuri"], "answer": 2},
    {"question": "Tốc độ ánh sáng xấp xỉ bao nhiêu km/s?", "options": ["300,000","150,000","1,000,000","450,000"], "answer": 0},
    {"question": "Nguyên tố có ký hiệu 'Mg' là?", "options": ["Mangan","Magie","Mercury","Molybdenum"], "answer": 1},
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
                correct_text = self.q_data["options"][self.q_data["answer"]]
                await interaction.response.edit_message(content=f"❌ **Sai!** Đáp án đúng: **{correct_text}**", view=self)
            self.stop()
        return cb
    def get_embed(self) -> discord.Embed:
        return discord.Embed(title="📚 Đố vui cùng Monika", description=self.q_data["question"], color=0xff1493)

# RPS
class RPSView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="✊ Búa", style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "Búa")
    @discord.ui.button(label="✋ Bao", style=discord.ButtonStyle.primary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "Bao")
    @discord.ui.button(label="✌️ Kéo", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "Kéo")
    async def play(self, interaction: discord.Interaction, user_choice: str):
        choices = ["Búa","Bao","Kéo"]
        monika_choice = random.choice(choices)
        for child in self.children:
            child.disabled = True
        if user_choice == monika_choice:
            result = "Hòa rồi!"
        elif (user_choice == "Búa" and monika_choice == "Kéo") or (user_choice == "Bao" and monika_choice == "Búa") or (user_choice == "Kéo" and monika_choice == "Bao"):
            result = "🎉 Cậu thắng!"
        else:
            result = "🤭 Lần sau tớ nhường nhé!"
        embed = discord.Embed(title="✂️ Oẳn Tù Tì", description=f"Cậu: **{user_choice}**\nMonika: **{monika_choice}**\n\n{result}", color=0x9932cc)
        await interaction.response.edit_message(embed=embed, view=self)

# Coinflip
class CoinFlipView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    @discord.ui.button(label="🪙 Ngửa", style=discord.ButtonStyle.success)
    async def heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.flip(interaction, "Ngửa")
    @discord.ui.button(label="🪙 Sấp", style=discord.ButtonStyle.danger)
    async def tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.flip(interaction, "Sấp")
    async def flip(self, interaction: discord.Interaction, user_guess: str):
        result = random.choice(["Ngửa","Sấp"])
        for child in self.children:
            child.disabled = True
        msg = f"✨ Kết quả: **{result}**. " + ("Bạn đoán đúng!" if user_guess == result else "Thua rồi, thử lại nhé.")
        embed = discord.Embed(title="🪙 Tung Đồng Xu", description=msg, color=0xffd700)
        await interaction.response.edit_message(embed=embed, view=self)

# Scramble
class ScrambleModal(discord.ui.Modal, title="Đoán từ (viết đúng từ)"):
    guess = discord.ui.TextInput(label="Đoán từ", placeholder="Nhập từ bạn nghĩ là đúng", min_length=1, max_length=50)
    def __init__(self, view):
        super().__init__()
        self.view_ref = view
    async def on_submit(self, interaction: discord.Interaction):
        text = self.guess.value.strip().lower()
        if text == self.view_ref.secret_word:
            embed = self.view_ref.get_embed()
            embed.title = "🎉 Đúng rồi! Cậu đoán chính xác!"
            for child in self.view_ref.children:
                child.disabled = True
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        else:
            self.view_ref.attempts -= 1
            if self.view_ref.attempts <= 0:
                embed = self.view_ref.get_embed()
                embed.title = f"😢 Hết lượt! Từ đúng: **{self.view_ref.secret_word}**"
                for child in self.view_ref.children:
                    child.disabled = True
                await interaction.response.edit_message(embed=embed, view=self.view_ref)
            else:
                await interaction.response.edit_message(embed=self.view_ref.get_embed(), view=self.view_ref)

class ScrambleView(discord.ui.View):
    def __init__(self, secret_word: str):
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
            candidate = "".join(s)
            if candidate != "".join(chars):
                return candidate
        return "".join(chars)
    def get_embed(self):
        return discord.Embed(title="🔀 Xáo chữ", description=f"Từ bị xáo: `{' '.join(self.scrambled)}`\nSố lượt: {self.attempts}", color=0x00bcd4)
    @discord.ui.button(label="Đoán từ", style=discord.ButtonStyle.primary)
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ScrambleModal(self))

# MathQuiz
class MathQuizView(discord.ui.View):
    def __init__(self, a:int, b:int, op:str, options:list[int], answer_index:int):
        super().__init__(timeout=60)
        self.answer_index = answer_index
        self.question = f"{a} {op} {b}"
        for idx, val in enumerate(options):
            btn = discord.ui.Button(label=str(val), style=discord.ButtonStyle.secondary)
            btn.callback = self.create_cb(idx)
            self.add_item(btn)
    def create_cb(self, idx:int):
        async def cb(interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
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

# Slash commands
@bot.tree.command(name="chat", description="Trò chuyện cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    reply = await ai_engine.generate_response(message, user_id=interaction.user.id)
    await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}")

@bot.tree.command(name="hangman", description="Chơi đoán từ (Hangman)")
async def hangman(interaction: discord.Interaction):
    view = HangmanView(random.choice(WORDS))
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="trivia", description="Chơi đố vui")
async def trivia(interaction: discord.Interaction):
    view = TriviaView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="rps", description="Chơi Kéo-Búa-Bao")
async def rps(interaction: discord.Interaction):
    embed = discord.Embed(title="✂️ Oẳn Tù Tì", description="Chọn một lựa chọn để so tài:", color=0x9932cc)
    await interaction.response.send_message(embed=embed, view=RPSView())

@bot.tree.command(name="coinflip", description="Tung đồng xu")
async def coinflip(interaction: discord.Interaction):
    embed = discord.Embed(title="🪙 Tung đồng xu", description="Chọn Ngửa hoặc Sấp:", color=0xffd700)
    await interaction.response.send_message(embed=embed, view=CoinFlipView())

@bot.tree.command(name="scramble", description="Xáo chữ: đoán từ")
async def scramble(interaction: discord.Interaction):
    secret = random.choice(WORDS)
    view = ScrambleView(secret)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="mathquiz", description="Toán nhanh nhiều lựa chọn")
async def mathquiz(interaction: discord.Interaction):
    a,b,op,opts,ans_idx = build_math_quiz()
    view = MathQuizView(a,b,op,opts,ans_idx)
    await interaction.response.send_message(embed=view.get_embed(), view=view)

@bot.tree.command(name="helps", description="Hiển thị trợ giúp")
async def helps(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Danh sách lệnh", color=0x00ffcc)
    embed.add_field(name="/chat <message>", value="Trò chuyện với Monika AI", inline=False)
    embed.add_field(name="/hangman", value="Chơi Hangman", inline=False)
    embed.add_field(name="/scramble", value="Xáo chữ", inline=False)
    embed.add_field(name="/trivia", value="Đố vui (multiple choice)", inline=False)
    embed.add_field(name="/mathquiz", value="Toán nhanh", inline=False)
    embed.add_field(name="/rps", value="Kéo-Búa-Bao", inline=False)
    embed.add_field(name="/coinflip", value="Tung đồng xu", inline=False)
    embed.set_footer(text="Nếu bot không phản hồi, kiểm tra token và intents.")
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
    # Start optional health server so Render (Web Service) sees an open port.
    # If you use Background Worker on Render, you can remove or skip this.
    await start_health_server()
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await ai_engine.close()
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
