#!/usr/bin/env python3
"""
Monika bot - full merged version
Features:
 - No music/voice
 - Gemini-based AI replies (requires GEMINI_API_KEY). If missing or failing, returns polite message.
 - Points/Level system:
    * Chat: +5 pts, cooldown 5s
    * Minigames: +50 pts, cooldown 30s
    * Daily cap default 500, can be increased by items/effects and by level (+5% per level)
    * Level every 100 pts; when leveling up user receives +300 pts (may cause multi-level)
 - Shop /store /inventory
    * Items: small_boost, large_boost, daily_plus, doki_chest
    * Buy in /shop (buttons), sell via /store (50% refund)
    * /inventory lists items + active effects
    * /use item qty to activate item(s)
 - Gacha: doki_chest opens to random points/items
 - Persistence: points.json, inventory.json, effects.json, nsfw_settings.json
 - /diag_ai (admin-only) to test Gemini connectivity
 - Health server on PORT (default 5000)
"""
import os
import re
import json
import random
import time
import asyncio
import traceback
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Tuple
from collections import deque

import discord
from discord.ext import commands
from aiohttp import web, ClientSession, ClientTimeout
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not DISCORD_TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN not set")
    raise SystemExit(1)

# ---------------- Persistence files ----------------
POINTS_PATH = Path("points.json")
INVENTORY_PATH = Path("inventory.json")
EFFECTS_PATH = Path("effects.json")
SETTINGS_PATH = Path("nsfw_settings.json")
LOG_PATH = Path("nsfw_attempts.log")

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

points_db: Dict[str, Dict] = load_json(POINTS_PATH, {})
inventory_db: Dict[str, Dict[str, int]] = load_json(INVENTORY_PATH, {})
effects_db: Dict[str, Dict] = load_json(EFFECTS_PATH, {})
nsfw_settings: Dict[str, Dict] = load_json(SETTINGS_PATH, {})

def save_all_state():
    save_json(POINTS_PATH, points_db)
    save_json(INVENTORY_PATH, inventory_db)
    save_json(EFFECTS_PATH, effects_db)
    save_json(SETTINGS_PATH, nsfw_settings)

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

# ---------------- Monika AI Engine (no fallback) ----------------
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
        if not self.enabled:
            return "Xin lỗi — Monika chưa được cấu hình để trả lời bằng AI. Vui lòng liên hệ admin."
        try:
            await self._ensure_session()
            persona = self.system_instruction
            if allow_nsfw:
                persona += (
                    " Bạn được phép dùng ngôn từ gợi ý, dí dỏm, tán tỉnh nhẹ nhàng (joke/flirt), "
                    "nhưng TUYỆT ĐỐI KHÔNG mô tả hành vi tình dục chi tiết, không mô tả bộ phận sinh dục, "
                    "không liên quan trẻ vị thành niên và không khuyến khích bạo lực hay phi pháp."
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
                if cand and isinstance(cand, list) and len(cand) > 0:
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
                clean = clean + " " + "kể thêm cho mình nhé."
            dq.append(clean)
        return clean

    def _is_similar(self, a: str, b: str) -> bool:
        if not a or not b: return False
        a_s,b_s = a.lower(), b.lower()
        if a_s in b_s or b_s in a_s:
            if len(min(a_s,b_s)) / max(len(a_s), len(b_s)) > 0.7:
                return True
        return False

    async def close(self):
        if self.session:
            await self.session.close()

# ---------------- Points / Level system & constants ----------------
DAILY_CAP = 500
CHAT_POINTS = 5
MINIGAME_POINTS = 50
LEVEL_BONUS_POINTS = 300
LEVEL_CAP_INCREASE_PER_LEVEL = 0.05  # 5% per level
POINTS_PER_LEVEL = 100  # 100 pts per level

def today_iso():
    return date.today().isoformat()

def ensure_user_entry(user_id: int):
    key = str(user_id)
    if key not in points_db:
        points_db[key] = {"total": 0, "daily": 0, "last_daily": today_iso(), "level": 0}
    if points_db[key].get("last_daily") != today_iso():
        points_db[key]["daily"] = 0
        points_db[key]["last_daily"] = today_iso()

def compute_level(total_points: int) -> int:
    return total_points // POINTS_PER_LEVEL

# ---------------- Inventory & effects helpers ----------------
ITEMS = {
    "small_boost": {
        "name": "Small Boost",
        "desc": "+20% điểm nhận được trong 60 phút",
        "cost": 100,
        "type": "boost",
        "multiplier": 0.2,
        "duration_minutes": 60
    },
    "large_boost": {
        "name": "Large Boost",
        "desc": "+50% điểm nhận được trong 180 phút",
        "cost": 300,
        "type": "boost",
        "multiplier": 0.5,
        "duration_minutes": 180
    },
    "daily_plus": {
        "name": "Daily +100",
        "desc": "+100 giới hạn điểm hàng ngày trong 24 giờ",
        "cost": 200,
        "type": "daily_bonus",
        "amount": 100,
        "duration_minutes": 24*60
    },
    "doki_chest": {
        "name": "Doki Chest",
        "desc": "Hòm may mắn: mở ngẫu nhiên ra item hoặc điểm",
        "cost": 150,
        "type": "chest"
    }
}

def ensure_inventory_entry(user_id: int):
    k = str(user_id)
    if k not in inventory_db:
        inventory_db[k] = {}

def add_item_to_inventory(user_id: int, item_key: str, qty: int = 1):
    ensure_inventory_entry(user_id)
    inv = inventory_db[str(user_id)]
    inv[item_key] = inv.get(item_key, 0) + qty
    save_json(INVENTORY_PATH, inventory_db)

def remove_item_from_inventory(user_id: int, item_key: str, qty: int = 1) -> bool:
    ensure_inventory_entry(user_id)
    inv = inventory_db[str(user_id)]
    have = inv.get(item_key, 0)
    if have < qty:
        return False
    if have == qty:
        inv.pop(item_key, None)
    else:
        inv[item_key] = have - qty
    save_json(INVENTORY_PATH, inventory_db)
    return True

def ensure_effects_entry(user_id: int):
    k = str(user_id)
    if k not in effects_db:
        effects_db[k] = {"boosts": [], "daily_bonus": [], "nsfw_sessions": {}}

def add_effect_boost(user_id: int, item_key: str, multiplier: float, duration_minutes: int):
    ensure_effects_entry(user_id)
    expires = time.time() + duration_minutes * 60
    effects_db[str(user_id)]["boosts"].append({"key": item_key, "multiplier": multiplier, "expires": expires})
    save_json(EFFECTS_PATH, effects_db)

def add_effect_daily_bonus(user_id: int, amount: int, duration_minutes: int):
    ensure_effects_entry(user_id)
    expires = time.time() + duration_minutes * 60
    effects_db[str(user_id)]["daily_bonus"].append({"amount": amount, "expires": expires})
    save_json(EFFECTS_PATH, effects_db)

def cleanup_expired_effects_for_user(user_id: int):
    ensure_effects_entry(user_id)
    now = time.time()
    e = effects_db[str(user_id)]
    b_before = len(e.get("boosts", []))
    d_before = len(e.get("daily_bonus", []))
    e["boosts"] = [b for b in e.get("boosts", []) if b.get("expires", 0) > now]
    e["daily_bonus"] = [d for d in e.get("daily_bonus", []) if d.get("expires", 0) > now]
    if len(e["boosts"]) != b_before or len(e["daily_bonus"]) != d_before:
        save_json(EFFECTS_PATH, effects_db)

def get_active_multiplier(user_id: int) -> float:
    ensure_effects_entry(user_id)
    cleanup_expired_effects_for_user(user_id)
    boosts = effects_db.get(str(user_id), {}).get("boosts", [])
    total_mul = 0.0
    for b in boosts:
        total_mul += b.get("multiplier", 0.0)
    return 1.0 + total_mul

def get_effective_daily_cap(user_id: int) -> int:
    ensure_effects_entry(user_id)
    cleanup_expired_effects_for_user(user_id)
    bonus = sum(d.get("amount", 0) for d in effects_db.get(str(user_id), {}).get("daily_bonus", []))
    ensure_user_entry(user_id)
    level = points_db.get(str(user_id), {}).get("level", 0)
    base = DAILY_CAP + bonus
    multiplier = 1.0 + LEVEL_CAP_INCREASE_PER_LEVEL * level
    return int(base * multiplier)

# ---------------- Points awarding (applies effects and level bonuses) ----------------
def add_points(user_id: int, base_amt: int) -> Tuple[int, bool, int]:
    ensure_user_entry(user_id)
    key = str(user_id)
    user = points_db[key]
    if user.get("last_daily") != today_iso():
        user["daily"] = 0
        user["last_daily"] = today_iso()

    multiplier = get_active_multiplier(user_id)
    effective_cap = get_effective_daily_cap(user_id)
    desired = int(base_amt * multiplier)
    remaining = effective_cap - user.get("daily", 0)
    if remaining <= 0:
        return 0, False, user.get("level", 0)
    grant = min(desired, remaining)
    user["total"] = user.get("total", 0) + grant
    user["daily"] = user.get("daily", 0) + grant
    old_level = user.get("level", 0)
    new_level = compute_level(user["total"])
    leveled = False
    if new_level > old_level:
        # award level bonus points (one-time) and update level
        user["level"] = new_level
        user["total"] = user.get("total", 0) + LEVEL_BONUS_POINTS
        # recompute final level after adding bonus
        final_level = compute_level(user["total"])
        if final_level > user["level"]:
            user["level"] = final_level
        leveled = True
    save_json(POINTS_PATH, points_db)
    return grant, leveled, user.get("level", 0)

# ---------------- Doki chest gacha ----------------
def open_doki_chest(user_id: int):
    r = random.random()
    if r < 0.4:
        pts = random.randint(50, 200)
        granted, leveled, new_level = add_points(user_id, pts)
        return {"type":"points","amount":granted}
    elif r < 0.8:
        item = random.choice(["small_boost","daily_plus"])
        add_item_to_inventory(user_id, item, 1)
        return {"type":"item","item":item}
    elif r < 0.98:
        item = "large_boost"
        add_item_to_inventory(user_id, item, 1)
        return {"type":"item","item":item}
    else:
        granted, leveled, new_level = add_points(user_id, 500)
        return {"type":"points","amount":granted}

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
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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

# ---------------- Bot setup & cooldowns ----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
ai_engine = MonikaAIEngine(GEMINI_API_KEY, MODEL_NAME)

last_chat_ts: Dict[int, float] = {}
last_minigame_ts: Dict[int, float] = {}

CHAT_COOLDOWN = 5.0
MINIGAME_COOLDOWN = 30.0

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

# ---------------- NSFW session helpers (stored under effects_db 'nsfw_sessions') ----------------
def set_nsfw_session(guild_id: Optional[int], channel_id: Optional[int], user_id: int, minutes: int = 10):
    key = (str(guild_id) if guild_id else "DM", str(channel_id) if channel_id else "DM", str(user_id))
    ensure_effects_entry(user_id)
    effects_db.setdefault("nsfw_sessions", {})
    effects_db["nsfw_sessions"][str(key)] = time.time() + minutes * 60
    save_json(EFFECTS_PATH, effects_db)

def revoke_nsfw_session(guild_id: Optional[int], channel_id: Optional[int], user_id: int):
    key = (str(guild_id) if guild_id else "DM", str(channel_id) if channel_id else "DM", str(user_id))
    effects_db.setdefault("nsfw_sessions", {})
    effects_db["nsfw_sessions"].pop(str(key), None)
    save_json(EFFECTS_PATH, effects_db)

def is_nsfw_session_active(interaction: discord.Interaction) -> bool:
    sessions = effects_db.get("nsfw_sessions", {})
    now = time.time()
    to_del = [k for k,v in sessions.items() if v <= now]
    for k in to_del:
        sessions.pop(k, None)
    effects_db["nsfw_sessions"] = sessions
    save_json(EFFECTS_PATH, effects_db)
    key = (str(getattr(interaction.guild, "id", "DM")) if interaction.guild else "DM",
           str(getattr(interaction.channel, "id", "DM")) if interaction.channel else "DM",
           str(interaction.user.id))
    return str(key) in sessions

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
        save_json(SETTINGS_PATH, nsfw_settings)
        await interaction.response.send_message("Đã bật chế độ soft-NSFW cho server. Người dùng cần /nsfw_allow để mở phiên NSFW.", ephemeral=False)
    elif a in ("disable","off"):
        nsfw_settings[guild_id] = {"enabled": False}
        save_json(SETTINGS_PATH, nsfw_settings)
        await interaction.response.send_message("Đã tắt chế độ soft-NSFW cho server.", ephemeral=True)
    elif a in ("status","check"):
        s = nsfw_settings.get(guild_id, {}).get("enabled", False)
        await interaction.response.send_message(f"NSFW enabled: {s}", ephemeral=True)
    else:
        await interaction.response.send_message("Tham số không hợp lệ. Dùng: enable / disable / status.", ephemeral=True)

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

# ---------------- Chat command (cooldown + award) ----------------
@bot.tree.command(name="chat", description="Trò chuyện cùng Monika AI")
async def chat(interaction: discord.Interaction, message: str):
    now_ts = time.time()
    last = last_chat_ts.get(interaction.user.id, 0)
    if now_ts - last < CHAT_COOLDOWN:
        await interaction.response.send_message(f"Bạn đang cooldown. Vui lòng chờ {int(CHAT_COOLDOWN - (now_ts-last))} giây.", ephemeral=True)
        return
    last_chat_ts[interaction.user.id] = now_ts
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
    if allow_nsfw and (contains_explicit(message) or contains_explicit(reply)):
        log_nsfw_attempt(interaction, message, reply)
        reply = "Mình không thể mô tả chi tiết như vậy. Hãy giữ câu chuyện ở tông nhẹ nhàng hoặc hài hước nhé."
    reply = clean_output(reply)
    granted, leveled, new_level = add_points(interaction.user.id, CHAT_POINTS)
    note = ""
    if granted > 0:
        note = f"\n\n(🏵️ Bạn nhận được {granted} điểm văn học.)"
    else:
        note = f"\n\n(ℹ️ Bạn đã đạt giới hạn điểm hàng ngày ({get_effective_daily_cap(interaction.user.id)}). Không nhận thêm điểm.)"
    if leveled:
        note += f" 🎉 Chúc mừng! Bạn đã lên Level {new_level} và nhận thêm {LEVEL_BONUS_POINTS} điểm!"
    await interaction.followup.send(f"**{interaction.user.name}:** {message}\n\n💬 **Monika:** {reply}{note}")

# ---------------- Minigame award helper & commands ----------------
async def handle_minigame_award(interaction: discord.Interaction):
    now_ts = time.time()
    last = last_minigame_ts.get(interaction.user.id, 0)
    if now_ts - last < MINIGAME_COOLDOWN:
        await interaction.response.send_message(f"Bạn đang cooldown minigame. Vui lòng chờ {int(MINIGAME_COOLDOWN - (now_ts-last))} giây.", ephemeral=True)
        return False
    last_minigame_ts[interaction.user.id] = now_ts
    granted, leveled, new_level = add_points(interaction.user.id, MINIGAME_POINTS)
    if granted > 0:
        msg = f"Bạn nhận được {granted} điểm văn học!"
        if leveled:
            msg += f" 🎉 Bạn đã lên Level {new_level} và nhận thêm {LEVEL_BONUS_POINTS} điểm!"
    else:
        msg = f"Bạn đã đạt giới hạn điểm hàng ngày ({get_effective_daily_cap(interaction.user.id)}). Không nhận thêm điểm."
    await interaction.followup.send(msg)
    return True

@bot.tree.command(name="hangman", description="Chơi Hangman")
async def cmd_hangman(interaction: discord.Interaction):
    view = HangmanView(random.choice(WORDS))
    await interaction.response.send_message(embed=view.get_embed(), view=view)
    await handle_minigame_award(interaction)

@bot.tree.command(name="trivia", description="Chơi Trivia")
async def cmd_trivia(interaction: discord.Interaction):
    view = TriviaView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)
    await handle_minigame_award(interaction)

@bot.tree.command(name="rps", description="Chơi Kéo-Búa-Bao")
async def cmd_rps(interaction: discord.Interaction):
    view = RPSView()
    await interaction.response.send_message(embed=discord.Embed(title="✂️ Oẳn Tù Tì", description="Chọn lựa chọn nhé:"), view=view)
    await handle_minigame_award(interaction)

@bot.tree.command(name="coinflip", description="Tung đồng xu")
async def cmd_coinflip(interaction: discord.Interaction):
    view = CoinFlipView()
    await interaction.response.send_message(embed=view.get_embed(), view=view)
    await handle_minigame_award(interaction)

@bot.tree.command(name="scramble", description="Xáo chữ: đoán từ")
async def cmd_scramble(interaction: discord.Interaction):
    secret = random.choice(WORDS)
    view = ScrambleView(secret)
    await interaction.response.send_message(embed=view.get_embed(), view=view)
    await handle_minigame_award(interaction)

@bot.tree.command(name="mathquiz", description="Toán nhanh nhiều lựa chọn")
async def cmd_math(interaction: discord.Interaction):
    a,b,op,opts,ans_idx = build_math_quiz()
    view = MathQuizView(a,b,op,opts,ans_idx)
    await interaction.response.send_message(embed=view.get_embed(), view=view)
    await handle_minigame_award(interaction)

# ---------------- Shop UI & commands ----------------
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        for key, item in ITEMS.items():
            label = f"Buy {item['name']} ({item['cost']})"
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            btn.callback = self.make_buy_cb(key)
            self.add_item(btn)
    def make_buy_cb(self, item_key):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True)
            user_id = interaction.user.id
            cost = ITEMS[item_key]["cost"]
            ensure_user_entry(user_id)
            user = points_db[str(user_id)]
            if user.get("total",0) < cost:
                await interaction.followup.send("Bạn không đủ điểm để mua món này.", ephemeral=True)
                return
            user["total"] = max(0, user.get("total",0) - cost)
            save_json(POINTS_PATH, points_db)
            it = ITEMS[item_key]
            if it["type"] == "boost":
                add_effect_boost(user_id, item_key, it["multiplier"], it["duration_minutes"])
                await interaction.followup.send(f"Đã mua {it['name']}. Hiệu lực {it['duration_minutes']} phút. Bạn bị trừ {cost} điểm.")
            elif it["type"] == "daily_bonus":
                add_effect_daily_bonus(user_id, it["amount"], it["duration_minutes"])
                await interaction.followup.send(f"Đã mua {it['name']}. +{it['amount']} daily cap trong {it['duration_minutes']//60} giờ. Bạn bị trừ {cost} điểm.")
            elif it["type"] == "chest":
                result = open_doki_chest(user_id)
                if result["type"] == "points":
                    await interaction.followup.send(f"Bạn đã mở Doki Chest và nhận được {result['amount']} điểm!")
                else:
                    add_item_to_inventory(user_id, result["item"], 1)
                    await interaction.followup.send(f"Bạn mở Doki Chest và nhận được vật phẩm **{ITEMS[result['item']]['name']}**! (đã vào kho)")
            else:
                add_item_to_inventory(user_id, item_key, 1)
                await interaction.followup.send(f"Đã thêm {it['name']} vào kho. Bạn bị trừ {cost} điểm.")
        return cb

@bot.tree.command(name="shop", description="Xem cửa hàng vật phẩm (nhấn Buy để mua)")
async def cmd_shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 Shop", description="Các vật phẩm bạn có thể mua bằng điểm văn học", color=0x00ffcc)
    for k, it in ITEMS.items():
        embed.add_field(name=f"{it['name']} — {it['cost']} điểm", value=it['desc'], inline=False)
    view = ShopView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="store", description="Bán vật phẩm trong kho để thu lại 50% giá (lấy lại điểm)")
@discord.app_commands.describe(item="key món (ví dụ small_boost)", qty="Số lượng")
async def cmd_store(interaction: discord.Interaction, item: str, qty: Optional[int] = 1):
    await interaction.response.defer()
    user_id = interaction.user.id
    ensure_inventory_entry(user_id)
    inv = inventory_db.get(str(user_id), {})
    have = inv.get(item, 0)
    if have <= 0:
        await interaction.followup.send("Bạn không có vật phẩm này trong kho.", ephemeral=True)
        return
    if qty < 1:
        qty = 1
    if qty > have:
        qty = have
    if item not in ITEMS:
        await interaction.followup.send("Vật phẩm không hợp lệ.", ephemeral=True)
        return
    sell_price = int(ITEMS[item]["cost"] * 0.5) * qty
    removed = remove_item_from_inventory(user_id, item, qty)
    if not removed:
        await interaction.followup.send("Không thể bán vật phẩm (không đủ).", ephemeral=True)
        return
    ensure_user_entry(user_id)
    points_db[str(user_id)]["total"] = points_db[str(user_id)].get("total",0) + sell_price
    save_json(POINTS_PATH, points_db)
    await interaction.followup.send(f"Bạn đã bán {qty} x {ITEMS[item]['name']} và nhận lại {sell_price} điểm.")

@bot.tree.command(name="inventory", description="Xem kho đồ và hiệu ứng đang hoạt động")
async def cmd_inventory(interaction: discord.Interaction):
    user_id = interaction.user.id
    ensure_inventory_entry(user_id)
    inv = inventory_db.get(str(user_id), {})
    lines = []
    if not inv:
        lines = ["(Kho trống)"]
    else:
        for k, q in inv.items():
            name = ITEMS.get(k, {}).get("name", k)
            lines.append(f"{name} ({k}): {q}")
    ensure_effects_entry(user_id)
    cleanup_expired_effects_for_user(user_id)
    eff = effects_db.get(str(user_id), {})
    boosts = eff.get("boosts", [])
    daily_bonuses = eff.get("daily_bonus", [])
    boost_lines = []
    for b in boosts:
        nm = ITEMS.get(b.get("key"), {}).get("name", b.get("key"))
        expires = datetime.utcfromtimestamp(b.get("expires")).isoformat() + "Z"
        boost_lines.append(f"{nm}: +{int(b.get('multiplier',0)*100)}% until {expires}")
    daily_lines = [f"+{d['amount']} daily until {datetime.utcfromtimestamp(d['expires']).isoformat()}Z" for d in daily_bonuses]
    desc = ""
    desc += "**Kho:**\n" + ("\n".join(lines)) + "\n\n"
    desc += "**Hiệu ứng đang hoạt động:**\n"
    if boost_lines or daily_lines:
        desc += ("\n".join(boost_lines + daily_lines))
    else:
        desc += "(Không có)"
    await interaction.response.send_message(desc, ephemeral=True)

# ---------------- /use command (use items from inventory) ----------------
@bot.tree.command(name="use", description="Sử dụng vật phẩm từ kho (ví dụ: /use small_boost 1)")
@discord.app_commands.describe(item="key món (ví dụ small_boost, doki_chest)", qty="Số lượng (mặc định 1)")
async def cmd_use(interaction: discord.Interaction, item: str, qty: Optional[int] = 1):
    item = item.strip()
    if qty is None or qty < 1:
        qty = 1
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    ensure_inventory_entry(user_id)
    inv = inventory_db.get(str(user_id), {})
    have = inv.get(item, 0)
    if have <= 0:
        await interaction.followup.send("Bạn không có vật phẩm này trong kho.", ephemeral=True)
        return
    if qty > have:
        qty = have

    if item not in ITEMS:
        await interaction.followup.send("Vật phẩm không hợp lệ.", ephemeral=True)
        return

    removed = remove_item_from_inventory(user_id, item, qty)
    if not removed:
        await interaction.followup.send("Không thể sử dụng vật phẩm (không đủ).", ephemeral=True)
        return

    it = ITEMS[item]
    results = []
    if it["type"] == "boost":
        for _ in range(qty):
            add_effect_boost(user_id, item, it["multiplier"], it["duration_minutes"])
        results.append(f"Đã kích hoạt {qty} x {it['name']} (+{int(it['multiplier']*100)}% điểm trong {it['duration_minutes']} phút).")
    elif it["type"] == "daily_bonus":
        for _ in range(qty):
            add_effect_daily_bonus(user_id, it["amount"], it["duration_minutes"])
        results.append(f"Đã thêm {qty} x {it['name']} (+{it['amount']} giới hạn ngày trong {it['duration_minutes']//60} giờ).")
    elif it["type"] == "chest":
        pts_total = 0
        items_got = {}
        for _ in range(qty):
            res = open_doki_chest(user_id)
            if res["type"] == "points":
                pts_total += int(res.get("amount", 0))
            elif res["type"] == "item":
                item_g = res.get("item")
                items_got[item_g] = items_got.get(item_g, 0) + 1
        if pts_total > 0:
            results.append(f"Bạn nhận được tổng {pts_total} điểm từ {qty} hòm.")
        for k,v in items_got.items():
            name = ITEMS.get(k,{}).get("name", k)
            results.append(f"Nhận được {v} x {name} (đã vào kho).")
    else:
        results.append(f"Đã sử dụng {qty} x {it.get('name', item)}.")

    save_all_state()
    await interaction.followup.send("\n".join(results), ephemeral=True)

# ---------------- Points & leaderboard commands ----------------
@bot.tree.command(name="points", description="Xem điểm văn học và level của bạn")
async def cmd_points(interaction: discord.Interaction):
    ensure_user_entry(interaction.user.id)
    user = points_db[str(interaction.user.id)]
    total = user.get("total",0); daily = user.get("daily",0); level = user.get("level",0)
    effective_cap = get_effective_daily_cap(interaction.user.id)
    await interaction.response.send_message(f"🏵️ Điểm văn học: {total}\n📅 Hôm nay: {daily}/{effective_cap}\n⭐ Level: {level}", ephemeral=True)

@bot.tree.command(name="leaderboard", description="Xem top 10 người có nhiều điểm nhất")
async def cmd_leaderboard(interaction: discord.Interaction):
    items = [(int(k), v.get("total",0)) for k,v in points_db.items()]
    items.sort(key=lambda x: x[1], reverse=True)
    top = items[:10]
    if not top:
        await interaction.response.send_message("Chưa có ai ghi điểm.", ephemeral=True)
        return
    lines = []
    for i,(uid,pts) in enumerate(top, start=1):
        try:
            member = await bot.fetch_user(uid)
            name = member.name
        except Exception:
            name = f"User {uid}"
        lines.append(f"{i}. {name}: {pts} điểm")
    await interaction.response.send_message("🏆 Leaderboard:\n" + "\n".join(lines), ephemeral=False)

# ---------------- Admin diag command for Gemini ----------------
@bot.tree.command(name="diag_ai", description="(Admin) Kiểm tra trạng thái kết nối tới Gemini API")
async def diag_ai(interaction: discord.Interaction):
    if interaction.guild and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Chỉ admin server mới được chạy lệnh này.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    info_lines = []
    info_lines.append(f"GEMINI_KEY_CONFIGURED: {'yes' if bool(GEMINI_API_KEY) else 'no'}")
    info_lines.append(f"MODEL_NAME: {MODEL_NAME}")
    if not GEMINI_API_KEY:
        await interaction.followup.send("\n".join(info_lines), ephemeral=True)
        return
    try:
        timeout = ClientTimeout(total=15)
        async with ClientSession(timeout=timeout) as s:
            url = f"https://generative.googleapis.com/v1/models/{MODEL_NAME}:generate"
            body = {"prompt": {"text": "Xin chào. Kiểm tra kết nối."}, "temperature": 0.0, "maxOutputTokens": 10}
            headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"}
            async with s.post(url, json=body, headers=headers) as resp:
                status = resp.status
                text = await resp.text()
                info_lines.append(f"HTTP status: {status}")
                info_lines.append("Response (trimmed):")
                info_lines.append(text[:800])
    except Exception as e:
        info_lines.append("Request failed:")
        info_lines.append(repr(e))
    await interaction.followup.send("\n".join(info_lines), ephemeral=True)

# ---------------- Health server for Render ----------------
async def start_health_server():
    async def handle_root(request): return web.Response(text="OK")
    app = web.Application(); app.router.add_get("/", handle_root)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT","5000"))
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
