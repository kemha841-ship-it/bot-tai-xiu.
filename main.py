import os
import random
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from gtts import gTTS

# ==========================================
# 1. KHỞI ĐỘNG WEB SERVER FLASK (CHO RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Tai Xiu is running successfully!"

def run_web():
    # Render yêu cầu dùng cổng 8080
    app.run(host="0.0.0.0", port=8080)

# Chạy Flask ở luồng nền (background thread)
flask_thread = threading.Thread(target=run_web)
flask_thread.start()


# ==========================================
# 2. KHỞI TẠO DISCORD BOT & DỮ LIỆU GAME
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_balances = {}
DICE_GIF_URL = "https://media.tenor.com/On7y262ne4AAAAAC/dice-roll.gif"
DICE_EMOJIS = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

def create_tts(text, filename):
    if not os.path.exists(filename):
        tts = gTTS(text=text, lang='vi')
        tts.save(filename)

# Khởi tạo các tệp âm thanh thông báo
create_tts("Mời bạn bắt đầu cá cược", "start.mp3")
create_tts("Đã hết thời gian cá cược", "end.mp3")
create_tts("Chúc mừng bạn đã thắng", "win.mp3")
create_tts("Ngu vờ lờ hết tiền rồi", "lose.mp3")

def get_balance(user_id):
    if user_id not in user_balances:
        user_balances[user_id] = 100000
    return user_balances[user_id]

async def play_audio(vc, file_path):
    if vc and vc.is_connected():
        try:
            if vc.is_playing():
                vc.stop()
            vc.play(discord.FFmpegPCMAudio(file_path))
            while vc.is_playing():
                await asyncio.sleep(0.3)
        except Exception as e:
            print(f"Lỗi âm thanh: {e}")

class BetAmountModal(Modal):
    def __init__(self, bet_choice, view_ref):
        super().__init__(title=f"Đặt cược cửa: {bet_choice}")
        self.bet_choice = bet_choice
        self.view_ref = view_ref
        
        self.amount_input = TextInput(
            label="Nhập số tiền muốn cược (xu):",
            placeholder="Ví dụ: 1000, 50000...",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            if amount <= 0:
                await interaction.response.send_message("❌ Số tiền cược phải lớn hơn 0!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Vui lòng chỉ nhập số!", ephemeral=True)
            return

        user_id = interaction.user.id
        bal = get_balance(user_id)

        if bal < amount:
            await interaction.response.send_message(f"❌ Bạn không đủ tiền! Số dư: **{bal:,} xu**.", ephemeral=True)
            return

        if user_id not in self.view_ref.bets:
            self.view_ref.bets[user_id] = []
        
        self.view_ref.bets[user_id].append({
            'choice': self.bet_choice,
            'amount': amount,
            'name': interaction.user.display_name
        })

        await interaction.response.send_message(f"✅ Bạn đã cược **{amount:,} xu** vào cửa **{self.bet_choice}**!", ephemeral=True)

class FullTaiXiuView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.bets = {}
        self.create_buttons()

    def create_buttons(self):
        choices = [
            ("Xỉu (3-10)", "Xỉu", discord.ButtonStyle.danger, 0),
            ("Tài (11-18)", "Tài", discord.ButtonStyle.success, 0),
            ("Chẵn", "Chẵn", discord.ButtonStyle.primary, 0),
            ("Lẻ", "Lẻ", discord.ButtonStyle.secondary, 0)
        ]
        
        for label, val, style, row in choices:
            btn = Button(label=label, style=style, row=row)
            btn.callback = self.make_callback(val)
            self.add_item(btn)

        row_idx = 1
        col_count = 0
        for num in range(3, 19):
            btn_num = Button(label=f"Số {num}", style=discord.ButtonStyle.secondary, row=row_idx)
            btn_num.callback = self.make_callback(f"Số {num}")
            self.add_item(btn_num)
            col_count += 1
            if col_count == 5:
                row_idx += 1
                col_count = 0

    def make_callback(self, choice):
        async def callback(interaction: discord.Interaction):
            modal = BetAmountModal(choice, self)
            await interaction.response.send_modal(modal)
        return callback

@bot.event
async def on_ready():
    print(f'🤖 Bot {bot.user.name} đã sẵn sàng hoạt động trực tuyến!')

@bot.command()
async def taixiu(ctx):
    vc = None
    # 1. Kết nối Voice Channel
    if ctx.author.voice:
        try:
            if ctx.voice_client:
                vc = ctx.voice_client
                if vc.channel != ctx.author.voice.channel:
                    await vc.move_to(ctx.author.voice.channel)
            else:
                vc = await ctx.author.voice.channel.connect()
        except Exception as e:
            print(f"Lỗi Voice: {e}")

    view = FullTaiXiuView()
    
    embed = discord.Embed(
        title="🎲 SÒNG CASINO HUY UY TÍN CHÂU Á BẮT ĐẦU MỞ!",
        description="Hãy bấm chọn cửa đặt bên dưới, sau đó nhập số tiền cược tùy ý!\n\n⏳ **Đếm ngược: 45 giây**\n\n⚀ ⚁ ⚂",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=DICE_GIF_URL)
    
    msg = await ctx.send(embed=embed, view=view)

    # 2. Phát âm thanh "Mời bạn bắt đầu cá cược"
    if vc:
        asyncio.create_task(play_audio(vc, "start.mp3"))

    # 3. Vòng lặp đếm ngược
    for remain in range(44, -1, -1):
        await asyncio.sleep(1)
        rand_d1 = DICE_EMOJIS[random.randint(1, 6)]
        rand_d2 = DICE_EMOJIS[random.randint(1, 6)]
        rand_d3 = DICE_EMOJIS[random.randint(1, 6)]
        
        try:
            embed.description = f"Hãy bấm chọn cửa đặt bên dưới, sau đó nhập số tiền cược tùy ý!\n\n⏳ **Đếm ngược: {remain} giây**\n\n{rand_d1} {rand_d2} {rand_d3}"
            await msg.edit(embed=embed)
        except Exception:
            pass

    # 4. KHÓA TẤT CẢ NÚT BẤM
    for child in view.children:
        child.disabled = True
    
    embed.title = "🎲 SÒNG CASINO HUY UY TÍN CHÂU Á - ĐÃ KHÓA CƯỢC!"
    embed.description = "🔒 **Đã hết thời gian đặt cược!** Đang mở bát và tính kết quả..."
    embed.color = discord.Color.gold()
    await msg.edit(embed=embed, view=view)

    # 5. Phát âm thanh hết giờ
    if vc:
        await play_audio(vc, "end.mp3")

    await asyncio.sleep(1)

    # 6. Tính kết quả
    d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
    tong = d1 + d2 + d3
    
    kq_taixiu = "Tài" if tong >= 11 else "Xỉu"
    kq_chanle = "Chẵn" if tong % 2 == 0 else "Lẻ"
    
    result_embed = discord.Embed(
        title=f"🎲 KẾT QUẢ: {DICE_EMOJIS[d1]} {DICE_EMOJIS[d2]} {DICE_EMOJIS[d3]} = {tong} ➔ {kq_taixiu.upper()} ({kq_chanle.upper()})!",
        color=discord.Color.green() if kq_taixiu == "Tài" else discord.Color.red()
    )
    result_embed.set_thumbnail(url=DICE_GIF_URL)

    has_win = False
    has_bet = False

    if not view.bets:
        result_embed.description = "Không có ai đặt cược trong ván này."
    else:
        summary = []
        has_bet = True
        for uid, user_bets in view.bets.items():
            for b in user_bets:
                choice = b['choice']
                amount = b['amount']
                name = b['name']
                
                is_win = False
                if choice == kq_taixiu or choice == kq_chanle:
                    is_win = True
                elif choice == f"Số {tong}":
                    is_win = True
                    amount *= 5
                
                if is_win:
                    user_balances[uid] += amount
                    summary.append(f"🎉 **{name}**: Thắng **+{amount:,} xu** ({choice})")
                    if uid == ctx.author.id:
                        has_win = True
                else:
                    user_balances[uid] -= amount
                    summary.append(f"💸 **{name}**: Thua **-{amount:,} xu** ({choice})")
                    
        result_embed.description = "\n".join(summary)

    await ctx.send(embed=result_embed)

    # 7. Phát âm thanh kết quả Thắng / Thua & Ngắt kết nối
    if vc and has_bet:
        if has_win:
            await play_audio(vc, "win.mp3")
        else:
            await play_audio(vc, "lose.mp3")
        await vc.disconnect()
    elif vc:
        await vc.disconnect()


# ==========================================
# 3. KHỞI CHẠY BOT AN TOÀN BẰNG BIẾN MÔI TRƯỜNG
# ==========================================
if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("LỖI: Không tìm thấy biến môi trường DISCORD_TOKEN trên Render!")
