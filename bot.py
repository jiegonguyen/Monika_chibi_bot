import os
import random
import discord
from discord import app_commands
from google import genai

# Cấu hình Token và API Key
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Cơ sở dữ liệu giả lập trong bộ nhớ (Dùng dict để lưu dữ liệu người dùng)
# Cấu trúc: user_points[user_id] = {"points": int, "level": int, "inventory": []}
user_data = {}

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {"points": 0, "level": 1, "inventory": []}
    return user_data[user_id]

@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot đã sẵn sàng với tên: {client.user}")

# --- 1. TÍNH NĂNG AI TALK ---
@tree.command(name="chat", description="Trò chuyện trực tiếp với Gemini AI")
@app_commands.describe(prompt="Nội dung bạn muốn hỏi")
async def chat(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        answer = response.text
        if len(answer) > 2000:
            answer = answer[:1997] + "..."
        await interaction.followup.send(f"**Hỏi:** {prompt}\n\n**Trả lời:** {answer}")
    except Exception as e:
        await interaction.followup.send(f"Đã xảy ra lỗi kết nối AI: {e}")

# --- 2. HỆ THỐNG ĐIỂM VĂN HỌC & LEVEL ---
@tree.command(name="profile", description="Xem điểm văn học và cấp độ của bạn")
async def profile(interaction: discord.Interaction):
    data = get_user(interaction.user.id)
    embed = discord.Embed(title=f"Hồ sơ của {interaction.user.name}", color=discord.Color.purple())
    embed.add_field(name="📖 Điểm Văn học", value=str(data["points"]), inline=True)
    embed.add_field(name="⭐ Cấp độ (Level)", value=str(data["level"]), inline=True)
    embed.add_field(name="🎒 Số vật phẩm trong kho", value=str(len(data["inventory"])), inline=False)
    await interaction.response.send_message(embed=embed)

# --- 3. CỬA HÀNG & KHO ĐỒ ---
SHOP_ITEMS = {
    "sach_tho": {"name": "Tuyển tập Thơ ca", "price": 50, "desc": "Một cuốn sách thơ truyền cảm hứng."},
    "but_than": {"name": "Bút thần văn học", "price": 100, "desc": "Cây bút giúp tăng điểm thưởng."}
}

@tree.command(name="shop", description="Xem cửa hàng vật phẩm văn học")
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 Cửa hàng Văn học", color=discord.Color.gold())
    for key, item in SHOP_ITEMS.items():
        embed.add_field(name=f"{item['name']} (Mã: {key})", value= giá := f"Giá: {item['price']} điểm\n{item['desc']}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="buy", description="Mua vật phẩm từ cửa hàng")
@app_commands.describe(item_key="Mã vật phẩm muốn mua (sach_tho hoặc but_than)")
async def buy(interaction: discord.Interaction, item_key: str):
    if item_key not in SHOP_ITEMS:
        await interaction.response.send_message("Vật phẩm không tồn tại!", ephemeral=True)
        return
    
    data = get_user(interaction.user.id)
    item = SHOP_ITEMS[item_key]
    
    if data["points"] < item["price"]:
        await interaction.response.send_message(f"Bạn không đủ điểm! Cần {item['price']} điểm văn học.", ephemeral=True)
        return
    
    data["points"] -= item["price"]
    data["inventory"].append(item["name"])
    await interaction.response.send_message(f"🎉 Bạn đã mua thành công **{item['name']}**!")

@tree.command(name="inventory", description="Xem kho đồ cá nhân của bạn")
async def inventory(interaction: discord.Interaction):
    data = get_user(interaction.user.id)
    inv = data["inventory"]
    if not inv:
        await interaction.response.send_message("Kho đồ của bạn đang trống!", ephemeral=True)
        return
    
    items_list = "\n".join([f"- {i}" for i in inv])
    embed = discord.Embed(title=f"🎒 Kho đồ của {interaction.user.name}", description=items_list, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# --- 4. MINIGAME (Đố vui văn học) ---
TRIVIA_QUESTIONS = [
    {"q": "Tác giả của tác phẩm 'Truyện Kiều' là ai?", "a": "nguyễn du"},
    {"q": "Nhà văn nào viết tiểu thuyết 'Số đỏ'?", "a": "vũ trọng phượng"},
    {"q": "Nhân vật Chí Phèo xuất hiện trong sáng tác của nhà văn nào?", "a": "nam cao"}
]

@tree.command(name="trivia", description="Chơi minigame trả lời câu hỏi văn học nhận điểm")
async def trivia(interaction: discord.Interaction):
    q_obj = random.choice(TRIVIA_QUESTIONS)
    await interaction.response.send_message(f"🧠 **Câu hỏi Đố vui:** {q_obj['q']}\n*(Hãy nhắn đáp án của bạn trong vòng 15 giây tới!)*")
    
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await client.wait_for('message', timeout=15.0, check=check)
        if msg.content.lower().strip() == q_obj['a']:
            data = get_user(interaction.user.id)
            data["points"] += 20
            # Cơ chế lên level đơn giản mỗi 50 điểm
            new_level = (data["points"] // 50) + 1
            if new_level > data["level"]:
                data["level"] = new_level
                await interaction.followup.send(f"Chính xác! 🎉 Bạn nhận được **20 điểm văn học** và đã thăng lên **Level {new_level}**!")
            else:
                await interaction.followup.send(f"Chính xác! 🎉 Bạn nhận được **20 điểm văn học**.")
        else:
            await interaction.followup.send(f"Rất tiếc, đáp án đúng phải là: **{q_obj['a']}**.")
    except Exception:
        await interaction.followup.send("Hết giờ! Bạn đã không trả lời kịp thời.")

client.run(DISCORD_TOKEN)
