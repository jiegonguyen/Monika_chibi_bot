# Minimal single-file Discord bot with a Gemini client stub + Minesweeper
# Put your DISCORD_TOKEN and GEMINI_API_KEY in env vars. Implement Gemini call where noted.

import os, random, asyncio, aiohttp
from typing import Optional, Tuple
from discord.ext import commands
from discord import Intents

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-default")
if not DISCORD_TOKEN:
    raise SystemExit("Set DISCORD_TOKEN env var")

intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Gemini client (simple async wrapper) ---
class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-default"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        # Example endpoint; adjust to your API
        self.endpoint = f"https://generative.googleapis.com/v1/models/{self.model}:generate"

    async def generate_response(self, prompt: str, max_tokens: int = 512) -> str:
        if not self.enabled:
            raise RuntimeError("Gemini API key not configured.")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"prompt": {"text": prompt}, "maxOutputTokens": max_tokens}
        async with aiohttp.ClientSession() as s:
            async with s.post(self.endpoint, headers=headers, json=body, timeout=30) as r:
                text = await r.text()
                if r.status != 200:
                    raise RuntimeError(f"Gemini error {r.status}: {text}")
                data = await r.json()
        # Simple extractor — adapt to real response shape
        if isinstance(data, dict) and "candidates" in data and data["candidates"]:
            return data["candidates"][0].get("output") or data["candidates"][0].get("content", "")
        return str(data)

gemini = GeminiClient(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)

# --- Minesweeper game (same as module version) ---
EMOJI_HIDDEN = "⬜"
EMOJI_FLAG = "🚩"
EMOJI_BOMB = "💣"
EMOJI_NUM = {0: "▫️",1: "1️⃣",2: "2️⃣",3: "3️⃣",4: "4️⃣",5: "5️⃣",6: "6️⃣",7: "7️⃣",8: "8️⃣"}

class MinesweeperGame:
    def __init__(self, w:int,h:int,bombs:int):
        self.w,self.h,self.bombs = w,h,bombs
        self._make_board()
        self.revealed = [[False]*w for _ in range(h)]
        self.flagged = [[False]*w for _ in range(h)]
        self.lost = False
    def _make_board(self):
        cells = [(x,y) for x in range(self.w) for y in range(self.h)]
        bombs = set(random.sample(cells, k=self.bombs))
        self.board = [[0]*self.w for _ in range(self.h)]
        for x,y in bombs: self.board[y][x] = -1
        for y in range(self.h):
            for x in range(self.w):
                if self.board[y][x]==-1: continue
                cnt=0
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        nx,ny = x+dx,y+dy
                        if 0<=nx<self.w and 0<=ny<self.h and self.board[ny][nx]==-1: cnt+=1
                self.board[y][x]=cnt
    def render(self,reveal_all=False)->str:
        rows=[]
        for y in range(self.h):
            row=[]
            for x in range(self.w):
                if reveal_all:
                    row.append(EMOJI_BOMB if self.board[y][x]==-1 else EMOJI_NUM.get(self.board[y][x],"▫️"))
                else:
                    if self.flagged[y][x]: row.append(EMOJI_FLAG)
                    elif not self.revealed[y][x]: row.append(EMOJI_HIDDEN)
                    else: row.append(EMOJI_BOMB if self.board[y][x]==-1 else EMOJI_NUM.get(self.board[y][x],"▫️"))
            rows.append("".join(row))
        return "\n".join(rows)
    def _flood_fill(self,x,y):
        stack=[(x,y)]
        while stack:
            cx,cy=stack.pop()
            if not (0<=cx<self.w and 0<=cy<self.h): continue
            if self.revealed[cy][cx] or self.flagged[cy][cx]: continue
            self.revealed[cy][cx]=True
            if self.board[cy][cx]==0:
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        nx,ny=cx+dx,cy+dy
                        if (nx,ny)!=(cx,cy) and 0<=nx<self.w and 0<=ny<self.h and not self.revealed[ny][nx]:
                            stack.append((nx,ny))
    def reveal(self,x,y)->Tuple[str,str]:
        if not (0<=x<self.w and 0<=y<self.h): return "invalid","Out of range"
        if self.flagged[y][x]: return "no-op","Cell flagged"
        if self.revealed[y][x]: return "no-op","Already revealed"
        if self.board[y][x]==-1:
            self.revealed[y][x]=True; self.lost=True; return "lost","Boom!"
        self._flood_fill(x,y)
        return ("won","You won!") if self.check_win() else ("ok","Revealed")
    def toggle_flag(self,x,y)->str:
        if not (0<=x<self.w and 0<=y<self.h): return "Out of range"
        if self.revealed[y][x]: return "Cannot flag revealed"
        self.flagged[y][x]=not self.flagged[y][x]; return "Flagged" if self.flagged[y][x] else "Unflagged"
    def check_win(self)->bool:
        for y in range(self.h):
            for x in range(self.w):
                if self.board[y][x]!=-1 and not self.revealed[y][x]: return False
        return True

# per-channel active games
active_games = {}

MONIKA_PROMPT_PREFIX = ("You are Monika (chibi-style): sweet, reflective, short replies. "
                       "Stay in-character. Keep replies <=120 tokens.")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command(name="talk")
async def talk(ctx, *, message: str):
    prompt = MONIKA_PROMPT_PREFIX + "\n\nUser: " + message + "\nMonika:"
    try:
        reply = await gemini.generate_response(prompt)
    except Exception as e:
        await ctx.reply(f"Gemini error: {e}")
        return
    await ctx.reply(reply)

@bot.command(name="ms_start")
async def ms_start(ctx, width: int = 9, height: int = 9, bombs: int = 10):
    width = max(5, min(20, width)); height = max(5, min(15, height))
    bombs = max(1, min(width*height-1, bombs))
    game = MinesweeperGame(width, height, bombs)
    active_games[ctx.channel.id] = game
    await ctx.send(f"Started {width}x{height} with {bombs} bombs\n" + game.render())

@bot.command(name="ms_reveal")
async def ms_reveal(ctx, x: int, y: int):
    game = active_games.get(ctx.channel.id)
    if not game: await ctx.send("No active game"); return
    result,msg = game.reveal(x,y)
    await ctx.send(msg + "\n" + game.render(reveal_all=(result=="lost")))
    if result in ("lost","won"): active_games.pop(ctx.channel.id,None)

@bot.command(name="ms_flag")
async def ms_flag(ctx,x:int,y:int):
    game = active_games.get(ctx.channel.id)
    if not game: await ctx.send("No active game"); return
    await ctx.send(game.toggle_flag(x,y) + "\n" + game.render())
    if game.check_win(): await ctx.send("You won!"); active_games.pop(ctx.channel.id,None)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
