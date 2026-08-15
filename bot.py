#!/usr/bin/env python3
# bot.py
# Phiên bản hợp nhất: Discord bot + Monika AI (Gemini stub/fallback) + Hangman + Trivia
# Lưu ý: KHÔNG đặt token vào mã nguồn. Đặt DISCORD_BOT_TOKEN và GEMINI_API_KEY trên Render (env vars).

import os
import random
import asyncio
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Thử import google genai (nếu có)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

# Load .env (chỉ dùng cho dev local; trên Render bạn sẽ dùng env vars)
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")   # tên biến bạn đang dùng
API_KEY = os.getenv("GEMINI_API_KEY")    # optional

# Debug presence (SAFE: không in token)
if TOKEN:
    print("DEBUG: DISCORD_BOT_TOKEN present")
else:
    print("DEBUG: DISCORD_BOT_TOKEN missing")
    # Không exit ngay nếu bạn muốn deploy test; nhưng tốt nhất exit để bạn bổ sung secret
    raise SystemExit("Thiếu DISCORD_BOT_TOKEN - thêm biến môi trường rồi redeploy")

if API_KEY and not GENAI_AVAILABLE:
    print("WARN: GEMINI_API_KEY set nhưng google.genai chưa cài. Cài package google-genai nếu muốn gọi Gemini thật.")

# --- AI Engine: dùng genai nếu có, fallback nếu không ---
class MonikaAIEngine:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self.enabled = bool(api_key) and GENAI_AVAILABLE
        self.model_name = "gemini-2.5-flash"  # chỉnh nếu bạn có model khác

        if self.enabled:
            # Khởi tạo client genai (đồng bộ) — các SDK khác nhau có API khác nhau
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print("Lỗi khi khởi tạo genai.Client:", e)
                self.enabled = False

        # System prompt cho persona Monika (ngắn gọn, bằng tiếng Việt)
        self.system_instruction = (
            "Bạn là Monika (chibi-style): dịu dàng, sâu sắc, thân mật nhưng lịch sự. "
            "Trả lời bằng tiếng Việt, ngắn gọn, giữ vai Monika. Tránh nội dung cấm."
        )

    async def generate_response(self, user_message: str) -> str:
        # Nếu client thật sẵn sàng, gọi API (nếu SDK blocking thì dùng to_thread)
        if self.enabled:
            try:
                # Tùy SDK: nhiều SDK trả về object khác nhau. Gọi trong thread nếu blocking.
                return await asyncio.to_thread(self._sync_generate, user_message)
            except Exception as e:
                print("Genai generate error:", e)
                print(traceback.format_exc())
                # rơi xuống fallback
        # Fallback: trả text mô phỏng (để bot chạy được ngay)
        return self._simulated_reply(user_message)

    def _sync_generate(self, user_message: str) -> str:
        """
        Gọi SDK đồng bộ. Tùy phiên bản SDK của bạn, phương thức có thể khác.
        Bạn cần kiểm tra tài liệu google genai python SDK và chỉnh phần này.
        Ví dụ giả định: client.models.generate_content(...) trả về object hoặc dict.
        """
        try:
            # Cấu trúc body / call tùy phiên bản SDK -> hãy chỉnh theo SDK bạn có.
            # Đây là ví dụ giả định; nếu SDK của bạn khác, thay đổi ở đây.
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"type": "text", "text": f"{self.system_instruction}\n\nNgười dùng: {user_message}\nMonika:"}],
                config=types.GenerateTextConfig(temperature=0.7, max_output_tokens=300)
            )
            # Thử nhiều cách lấy text (tùy response)
            if hasattr(response, "text") and response.text:
                return response.text
            # nếu có candidates
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
            # cuối cùng
            return str(response)
        except Exception as e:
            print("Exception in _sync_generate:", e)
            raise

    def _simulated_reply(self, user_message: str) -> str:
        # Tạm thời mô phỏng trả lời theo persona — ngắn gọn
        samples = [
            "Mmm... mình thích điều đó. Hãy nói thêm cho mình nghe nhé.",
            "Thật thú vị... mình luôn ở đây để lắng nghe cậu.",
            "Cậu làm mình mỉm cười. Kể thêm đi..."
        ]
        # Trả chuỗi mô phỏng + echo 1 phần message
        tail = user_message[:80] + ("..." if len(user_message) > 80 else "")
        return f"{random.choice(samples)} (mình nghe: \"{tail}\")"

# --- Hangman (Modal + View) ---
WORDS = ["python", "monika", "literature", "poetry", "discord", "cupcake", "yuri", "sayori", "natsuki"]

class HangmanModal(discord.ui.Modal, title="Nhập chữ cái bạn muốn đoán"):
    letter_input = discord.ui.TextInput(
        label="Chữ cái (a-z)",
        placeholder="Nhập 1 ký tự...",
        max_length=1,
        min_length=1
    )

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

    @discord.ui.button(label="Đoán chữ cái", style=discord.ButtonStyle.primary, custom_id="guess_btn")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HangmanModal(self))

# --- Trivia ---
QUESTIONS = [
    {"question": "Trong Doki Doki Literature Club, ai là chủ tịch câu lạc bộ văn học?",
     "options": ["Sayori", "Natsuki", "Monika", "Yuri"], "answer": 2},
    {"question": "Tốc độ ánh sáng xấp xỉ bao nhiêu km/s?", "options": ["300,000", "150,000", "1,000,000", "450,000"], "answer": 0},
    {"question": "Nguyên tố có ký hiệu 'Mg' là?", "options": ["Mangan", "Magie", "Mercury", "Molybdenum"], "answer": 1},
]

class TriviaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.q_data = random.choice(QUESTIONS)
        for idx, option in enumerate(self.q_data["options"]):
            btn = discord.ui.Button(label=f"{chr(65+idx)}. {option}", style=discord.ButtonStyle.secondary, custom_id=f"opt_{idx}")
            btn.callback = self.create_callback(idx)
            self.add_item(btn)

    def create_callback(self, index: int):
        async def button_callback(interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
            if index == self.q_data["answer"]:
                await interaction.response.edit_message(content="✅ **Chính xác!**", view=self)
            else:
                correct_text = self.q_data["options"][self.q_data["answer"]]
                await interaction.response.edit_message(content=f"❌ **Sai!** Đáp án đúng: **{correct_text}**", view=self)
            self.stop()
        return button_callback

    def get_embed(self) -> discord.Embed:
        return discord.Embed(title="📚 Đố vui cùng Monika", description=self.q_data["question"], color=0xff1493)

# --- Bot setup & commands ---
intents = discord.Intents.default()
intents.message_content = True  # bật message_content trong Developer Portal nếu dùng
bot = commands.Bot(command_prefix="!", intents=intents)
ai_engine = MonikaAIEngine(API_KEY)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Đã đồng bộ {len(synced)} lệnh slash.")
    except Exception as e:
        print("Lỗi sync lệnh slash:", e)

@bot.tree.command(name="chat", description="Trò chuyện cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    await interaction.response.defer()  # tránh timeout
    try:
        reply = await ai_engine.generate_response(message)
        await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}")
    except Exception as e:
        print("Lỗi khi tạo reply:", e)
        await interaction.followup.send("Đã có lỗi khi gọi AI. Hãy thử lại sau.")

@bot.tree.command(name="hangman", description="Chơi đoán từ")
async def hangman(interaction: discord.Interaction):
    game_view = HangmanView(random.choice(WORDS))
    await interaction.response.send_message(embed=game_view.get_embed(), view=game_view)

@bot.tree.command(name="trivia", description="Chơi đố vui")
async def trivia(interaction: discord.Interaction):
    view = TriviaView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)

if __name__ == "__main__":
    bot.run(TOKEN)
