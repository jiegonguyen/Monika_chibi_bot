import os
import discord
from discord.ext import commands
import logging

# --- BẢN VÁ DỨT ĐIỂM LỖI 401 UNAUTHORIZED ---
# Nếu Render vẫn lỗi, hãy dán trực tiếp token của Monika vào chuỗi dưới đây
# CẢNH BÁO: Sau khi chạy thành công, hãy đổi token trên Discord Portal để bảo mật
ACTIVE_TOKEN "MTUzODQ0ODY0MzAwNTM1ODE2MA.GuKhV4.g021Btk0hKS3Z8JwkYkH1gcLxJgvjieN69UtJ4" 

# Cấu hình log để theo dõi chính xác lỗi
logging.basicConfig(level=logging.INFO)

# --- BẢN VÁ INTENTS (Giúp Monika online ở mọi server) ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.presences = True  # Quan trọng: Giúp sáng đèn online
intents.members = True    # Quan trọng: Nhận diện thành viên toàn server

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Monika đã kết nối thành công: {bot.user}")
    print(f"Đang hoạt động trên {len(bot.guilds)} máy chủ.")

# Lệnh kiểm tra trạng thái
@tree.command(name="ping", description="Kiểm tra Monika có đang hoạt động không")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Monika vẫn đang ở đây! Độ trễ: {round(bot.latency * 1000)}ms")

# Chạy bot với token cứng để vượt qua lỗi cache của Render
if __name__ == "__main__":
    if ACTIVE_TOKEN == "DÁN_TOKEN_CỦA_MONIKA_VÀO_ĐÂY":
        print("LỖI: Bạn chưa dán token vào code!")
    else:
        bot.run(ACTIVE_TOKEN)
