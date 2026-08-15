import os
import asyncio
import discord
from discord.ext import commands
import requests

# Cấu hình Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# 🔑 TOKEN & API CỦA MONIKA
GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY"
DISCORD_TOKEN = "YOUR_MONIKA_DISCORD_TOKEN"

# --- HÀM AI ---
def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": f"Bạn là Monika. Trả lời ngắn gọn, thân thiện, tiếng Việt: {prompt}"}]}]}
    try:
        response = requests.post(url, json=payload).json()
        return response['candidates'][0]['content']['parts'][0]['text']
    except:
        return "Tớ đang bận chỉnh lại code một chút, cậu đợi tí nhé! 💚"

# --- LỆNH & COOLDOWN 1 PHÚT ---
@bot.command(name='deptrai')
@commands.cooldown(1, 60, commands.BucketType.user)
async def deptrai_cmd(ctx):
    await ctx.send("💚 Tất nhiên rồi! Người code ra tớ là đỉnh nhất! ✨")

@bot.command(name='Mhelp')
@commands.cooldown(1, 60, commands.BucketType.user)
async def monika_help(ctx):
    await ctx.send("💚 **Lệnh Monika:** `@Monika [chat]`, `!deptrai` (Cooldown 1 phút/lệnh)")

# Xử lý khi bị spam
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⚠️ Cậu spam lệnh nhanh quá! Hãy bình tĩnh chờ **{int(error.retry_after)} giây** nữa rồi dùng tiếp nhé. 🍵", delete_after=10)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # AI Chat không cooldown để đảm bảo trải nghiệm chat mượt mà
    if bot.user.mentioned_in(message) and not message.content.startswith('!'):
        user_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        async with message.channel.typing():
            reply_text = ask_gemini(user_prompt if user_prompt else "chào bạn")
            await message.reply(reply_text)
        
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
