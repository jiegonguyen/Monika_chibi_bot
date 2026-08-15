#!/usr/bin/env python3
"""
bot.py - Discord bot:
 - Monika AI (Gemini optional; fallback nếu không cấu hình)
 - Minigame: Hangman, Trivia, RPS, Coinflip
 - Slash command /helps (liệt kê lệnh)
 - Tích hợp HTTP health server (aiohttp) để Render phát hiện PORT nếu chạy Web Service
"""
import os
import random
import asyncio
import traceback
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

# Thử import google genai (nếu có)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

# Load env (chỉ dùng cho local dev; trên Render bạn dùng Env vars)
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Kiểm tra token
if not DISCORD_TOKEN:
    print("LỖI: Thiếu DISCORD_BOT_TOKEN. Thêm biến môi trường rồi redeploy.")
    raise SystemExit(1)

if GEMINI_API_KEY and not GENAI_AVAILABLE:
    print("WARN: GEMINI_API_KEY được set nhưng google-genai chưa cài. Cài package nếu muốn dùng Gemini thực.")

# ---------------- Monika AI Engine ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.enabled = bool(api_key) and GENAI_AVAILABLE
        self.model_name = MODEL_NAME

        if self.enabled:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print("Không thể khởi tạo genai.Client:", e)
                self.enabled = False

        self.system_instruction = (
            "Bạn là Monika (chibi-style): dịu dàng, sâu sắc, thân mật nhưng lịch sự. "
            "Trả lời bằng tiếng Việt, ngắn gọn, giữ vai Monika. Tránh nội dung cấm."
        )

    async def generate_response(self, user_message: str) -> str:
        if self.enabled:
            try:
                # Gọi đồng bộ trong thread nếu SDK là blocking
                return await asyncio.to_thread(self._sync_generate, user_message)
            except Exception as e:
                print("Lỗi khi gọi Gemini:", e)
                print(traceback.format_exc())
        # Fallback mô phỏng trả lời
        return self._simulated_reply(user_message)

    def _sync_generate(self, user_message: str) -> str:
        """
        Gọi SDK đồng bộ. Tuỳ SDK/phiên bản, bạn có thể phải chỉnh phần này.
        Đây là ví dụ giả định dùng client.models.generate_content(...)
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"type": "text", "text": f"{self.system_instruction}\n\nNgười dùng: {user_message}\nMonika:"}],
                config=types.GenerateTextConfig(temperature=0.7, max_output_tokens=300)
            )
            # Nhiều SDK trả response khác nhau — thử các thuộc tính phổ biến
            if hasattr(response, "text") and response.text:
                return response.text
            if isinstance(response, dict):
                if "candidates" in response and response["candidates"]:
                    c = response["candidates"][0]
                    return c.get("output") or c.get("content") or str(c)
                if "output" in response:
                    out = response["output"]
                    if isinstance(out, list) and out:
                        first = out[0]
                        if isinstance(first, dict):
                            return first.get("content", str(first))
                        return str(first)
                    return str(out)
            return str(response)
        except Exception as e:
            print("Exception in _sync_generate:", e)
            raise

    def _simulated_reply(self, user_message: str) -> str:
        samples = [
            "Mmm... mình thích điều đó. Hãy kể thêm cho mình nghe nhé.",
            "Thật thú vị... mình luôn ở đây để lắng nghe cậu.",
            "Cậu làm mình mỉm cười. Kể thêm đi..."
        ]
        tail = (user_message[:100] + "...") if len(user_message) > 100 else user_message
        return f"{random.choice(samples)} (mình nghe: \"{tail}\")"

# ---------------- Games ----------------
WORDS = ["python", "monika", "literature", "poetry", "discord", "cupcake", "yuri", "sayori", "natsuki"]

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
        embed = discord.Embed(
            title="🌿 Trò chơi đoán từ cùng Monika (Hangman)",
            description=f"`{' '.join(self.current_display)}`",
            color=0xff69b4
        )
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

# ---------------- Bot setup ----------------
intents = discord.Intents.default()
intents.message_content = True  # bật message_content nếu cần
bot = commands.Bot(command_prefix="!", intents=intents)
ai_engine = MonikaAIEngine(GEMINI_API_KEY)

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
    try:
        reply = await ai_engine.generate_response(message)
        await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}")
    except Exception as e:
        print("Lỗi khi tạo reply:", e)
        await interaction.followup.send("Đã xảy ra lỗi khi gọi AI. Hãy thử lại sau.")

@bot.tree.command(name="hangman", description="Chơi đoán từ")
async def hangman(interaction: discord.Interaction):
    game_view = HangmanView(random.choice(WORDS))
    await interaction.response.send_message(embed=game_view.get_embed(), view=game_view)

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

@bot.tree.command(name="helps", description="Hiển thị trợ giúp và danh sách lệnh")
async def helps(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Danh sách lệnh", color=0x00ffcc)
    embed.add_field(name="/chat <message>", value="Trò chuyện với Monika AI", inline=False)
    embed.add_field(name="/hangman", value="Bắt đầu trò Hangman (đoán từ)", inline=False)
    embed.add_field(name="/trivia", value="Chơi đố vui kiến thức", inline=False)
    embed.add_field(name="/rps", value="Chơi Kéo-Búa-Bao", inline=False)
    embed.add_field(name="/coinflip", value="Tung đồng xu", inline=False)
    embed.set_footer(text="Sử dụng các lệnh trên trong server đã cài bot. Nếu bot không trả lời, kiểm tra token và intents.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- Health server for Render (optional) ----------------
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

# ---------------- Run: start health server + bot ----------------
async def main():
    # start health server in background (so Render sees an open port)
    # If you prefer Background Worker on Render, you can remove this and just run bot.start
    await start_health_server()
    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
