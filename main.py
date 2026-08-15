import os
import asyncio
from discord.ext import commands
from gemini_client import GeminiClient
from games.minesweeper import MinesweeperGame

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-default")

if not DISCORD_TOKEN:
    raise SystemExit("Set DISCORD_TOKEN env var")

intents = None
# If you need presence/member info, enable intents appropriately
from discord import Intents
intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
gemini = GeminiClient(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)

# per-channel active games
active_games: dict[int, MinesweeperGame] = {}

MONIKA_PROMPT_PREFIX = (
    "You are Monika (chibi-style): sweet, reflective, a little meta and kind. "
    "You respond in short, gentle sentences. Stay in-character as Monika. "
    "If the user asks to roleplay, continue as Monika. Avoid disallowed content."
)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("------")

@bot.command(name="talk", help="Talk to Monika: !talk <message>")
async def talk(ctx, *, message: str):
    prompt = MONIKA_PROMPT_PREFIX + "\n\nUser: " + message + "\nMonika:"
    # You might want to pass conversation history; keep it short to avoid token costs.
    try:
        reply = await gemini.generate_response(prompt)
    except NotImplementedError:
        await ctx.reply("Gemini client not configured. Please set GEMINI_API_KEY and implement the client.")
        return
    await ctx.reply(reply)

@bot.command(name="ms_start", help="Start a Minesweeper game: !ms_start <width> <height> <bombs>")
async def ms_start(ctx, width: int = 9, height: int = 9, bombs: int = 10):
    width = max(5, min(30, width))
    height = max(5, min(20, height))
    bombs = max(1, min(width * height - 1, bombs))
    game = MinesweeperGame(width, height, bombs)
    active_games[ctx.channel.id] = game
    await ctx.send(f"Started Minesweeper {width}x{height} with {bombs} bombs.\n" + game.render())

@bot.command(name="ms_reveal", help="Reveal a cell: !ms_reveal x y (0-based)")
async def ms_reveal(ctx, x: int, y: int):
    game = active_games.get(ctx.channel.id)
    if not game:
        await ctx.send("No active game. Start one with !ms_start")
        return
    result, msg = game.reveal(x, y)
    await ctx.send(msg + "\n" + game.render())
    if result in ("lost", "won"):
        active_games.pop(ctx.channel.id, None)

@bot.command(name="ms_flag", help="Flag/unflag a cell: !ms_flag x y (0-based)")
async def ms_flag(ctx, x: int, y: int):
    game = active_games.get(ctx.channel.id)
    if not game:
        await ctx.send("No active game. Start one with !ms_start")
        return
    msg = game.toggle_flag(x, y)
    await ctx.send(msg + "\n" + game.render())
    if game.check_win():
        await ctx.send("You won! 🎉")
        active_games.pop(ctx.channel.id, None)

@bot.command(name="ms_show", help="Show the current board (hidden cells shown as emojis).")
async def ms_show(ctx):
    game = active_games.get(ctx.channel.id)
    if not game:
        await ctx.send("No active game. Start one with !ms_start")
        return
    await ctx.send(game.render())

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
