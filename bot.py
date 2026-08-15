#!/usr/bin/env python3
"""
Single-file Discord bot prototype:
 - đọc DISCORD_TOKEN và GEMINI_API_KEY từ biến môi trường
 - Gemini client: stub async (implement API call yourself)
 - Minesweeper minigame (in-memory, per-channel)
 - Debug nhẹ: in ra chỉ "DISCORD_TOKEN present" (KHÔNG in token)
"""
import os
import random
import asyncio
import aiohttp
from typing import Optional, Tuple
from discord.ext import commands
from discord import Intents

# ---- Config / Env ----
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-default")

# Debug presence check (safe: KHÔNG in token)
if DISCORD_TOKEN:
    print("DEBUG: DISCORD_TOKEN present")
else:
    print("DEBUG: DISCORD_TOKEN missing")
    raise SystemExit("Set DISCORD_TOKEN env var and redeploy")

# ---- Gemini client (stub) ----
class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-default"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)

    async def generate_response(self, prompt: str, max_tokens: int = 512) -> str:
        """
        Implement the real call to Gemini/Generative API here.
        For now we return a simple echo or raise if not configured.
        """
        if not self.enabled:
            raise RuntimeError("Gemini client not configured (GEMINI_API_KEY missing)")
        # Example: perform HTTP call to your provider here.
        # This is a placeholder that simply returns an acknowledgement.
        await asyncio.sleep(0.1)
        return "Monika (simulated): " + (prompt[:200] + "..." if len(prompt) > 200 else prompt)

# ---- Minesweeper game ----
EMOJI_HIDDEN = "⬜"
EMOJI_FLAG = "🚩"
EMOJI_BOMB = "💣"
EMOJI_NUM = {
    0: "▫️",
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
}

class MinesweeperGame:
    def __init__(self, width: int, height: int, bombs: int):
        self.w = width
        self.h = height
        self.bombs = bombs
        self._make_board()
        self.revealed = [[False]*self.w for _ in range(self.h)]
        self.flagged = [[False]*self.w for _ in range(self.h)]
        self.lost = False

    def _make_board(self):
        cells = [(x, y) for x in range(self.w) for y in range(self.h)]
        bomb_positions = set(random.sample(cells, k=self.bombs))
        self.board = [[0]*self.w for _ in range(self.h)]
        for x, y in bomb_positions:
            self.board[y][x] = -1
        for y in range(self.h):
            for x in range(self.w):
                if self.board[y][x] == -1:
                    continue
                count = 0
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        nx, ny = x+dx, y+dy
                        if 0 <= nx < self.w and 0 <= ny < self.h and self.board[ny][nx] == -1:
                            count += 1
                self.board[y][x] = count

    def render(self, reveal_all=False) -> str:
        rows = []
        for y in range(self.h):
            row = []
            for x in range(self.w):
                if reveal_all:
                    if self.board[y][x] == -1:
                        row.append(EMOJI_BOMB)
                    else:
                        row.append(EMOJI_NUM.get(self.board[y][x], "▫️"))
                else:
                    if self.flagged[y][x]:
                        row.append(EMOJI_FLAG)
                    elif not self.revealed[y][x]:
                        row.append(EMOJI_HIDDEN)
                    else:
                        if self.board[y][x] == -1:
                            row.append(EMOJI_BOMB)
                        else:
                            row.append(EMOJI_NUM.get(self.board[y][x], "▫️"))
            rows.append("".join(row))
        return "\n".join(rows)

    def reveal(self, x: int, y: int) -> Tuple[str, str]:
        if not (0 <= x < self.w and 0 <= y < self.h):
            return "invalid", "Coordinates out of range."
        if self.flagged[y][x]:
            return "no-op", "Cell is flagged. Unflag first to reveal."
        if self.revealed[y][x]:
            return "no-op", "Cell already revealed."
        if self.board[y][x] == -1:
            self.revealed[y][x] = True
            self.lost = True
            return "lost", "Boom! You hit a bomb. Game over."
        self._flood_fill(x, y)
        if self.check_win():
            return "won", "All safe cells revealed. You won!"
        return "ok", "Revealed."

    def _flood_fill(self, x: int, y: int):
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if not (0 <= cx < self.w and 0 <= cy < self.h):
                continue
            if self.revealed[cy][cx] or self.flagged[cy][cx]:
                continue
            self.revealed[cy][cx] = True
            if self.board[cy][cx] == 0:
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        nx, ny = cx+dx, cy+dy
                        if (nx, ny) != (cx, cy) and 0 <= nx < self.w and 0 <= ny < self.h:
                            if not self.revealed[ny][nx]:
                                stack.append((nx, ny))

    def toggle_flag(self, x: int, y: int) -> str:
        if not (0 <= x < self.w and 0 <= y < self.h):
            return "Coordinates out of range."
        if self.revealed[y][x]:
            return "Cannot flag a revealed cell."
        self.flagged[y][x] = not self.flagged[y][x]
        return "Flagged." if self.flagged[y][x] else "Unflagged."

    def check_win(self) -> bool:
        for y in range(self.h):
            for x in range(self.w):
                if self.board[y][x] != -1 and not self.revealed[y][x]:
                    return False
        return True

# ---- Discord bot setup ----
intents = Intents.default()
intents.message_content = True  # nếu bạn dùng message content, bật trong Dev Portal
bot = commands.Bot(command_prefix="!", intents=intents)
gemini = GeminiClient(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)

active_games: dict[int, MinesweeperGame] = {}

MONIKA_PROMPT_PREFIX = (
    "You are Monika (chibi-style): sweet, reflective, concise. Reply in-character."
)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")

@bot.command(name="talk", help="Talk to Monika: !talk <message>")
async def talk(ctx, *, message: str):
    prompt = MONIKA_PROMPT_PREFIX + "\n\nUser: " + message + "\nMonika:"
    try:
        reply = await gemini.generate_response(prompt)
    except Exception as e:
        # Nếu Gemini chưa cấu hình, báo lỗi nhẹ cho user
        await ctx.reply("Gemini client không cấu hình hoặc lỗi: " + str(e))
        return
    await ctx.reply(reply)

@bot.command(name="ms_start", help="Start a Minesweeper: !ms_start <width> <height> <bombs>")
async def ms_start(ctx, width: int = 9, height: int = 9, bombs: int = 10):
    width = max(5, min(30, width))
    height = max(5, min(20, height))
    bombs = max(1, min(width * height - 1, bombs))
    game = MinesweeperGame(width, height, bombs)
    active_games[ctx.channel.id] = game
    await ctx.send(f"Started Minesweeper {width}x{height} with {bombs} bombs.\n" + game.render())

@bot.command(name="ms_reveal", help="Reveal cell: !ms_reveal x y (0-based)")
async def ms_reveal(ctx, x: int, y: int):
    game = active_games.get(ctx.channel.id)
    if not game:
        await ctx.send("No active game. Start with !ms_start")
        return
    result, msg = game.reveal(x, y)
    await ctx.send(msg + "\n" + game.render(reveal_all=(result == "lost")))
    if result in ("lost", "won"):
        active_games.pop(ctx.channel.id, None)

@bot.command(name="ms_flag", help="Flag/unflag: !ms_flag x y (0-based)")
async def ms_flag(ctx, x: int, y: int):
    game = active_games.get(ctx.channel.id)
    if not game:
        await ctx.send("No active game. Start with !ms_start")
        return
    msg = game.toggle_flag(x, y)
    await ctx.send(msg + "\n" + game.render())
    if game.check_win():
        await ctx.send("You won! 🎉")
        active_games.pop(ctx.channel.id, None)

# ---- Run ----
if __name__ == "__main__":
    # đảm bảo token tồn tại đã kiểm ở trên
    bot.run(DISCORD_TOKEN)
