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
    return "Bot Tai Xiu VIP is running!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

flask_thread = threading.Thread(target=run_web)
flask_thread.start()


# ==========================================
# 2. KHỞI TẠO DISCORD BOT & DỮ LIỆU GAME
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_balances = {}
running_games = {} # Quản lý trạng thái tự động theo kênh (channel_id)

DICE_GIF_URL = "https://media.tenor.com/On7y262ne4AAAAAC/dice-roll.gif"
DICE_EMOJIS = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

def create_tts(text, filename):
    if not os.path.exists(filename):
        tts = gTTS(text=text, lang='vi')
        tts.save(filename)

create_tts("Mời bạn bắt đầu cá cược", "start.mp3")
create_tts("Đã hết thời gian cá cược", "end.mp3")
create_tts("Chúc mừng bạn đã thắng", "win.mp3")
create_tts("Ngu vờ lờ hết tiền rồi", "lose.mp3")

def get_balance(user_id):
    if user_id not in user_balances:
        user_balances[user_id] = 100000 # Mặc định 100k xu
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
        super().__init__(title=f"🔥 Cửa chọn: {bet_choice}")
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
            await interaction.response.send_message("❌ Vui lòng chỉ nhập số hợp lệ!", ephemeral=True)
            return

        user_id = interaction.user.id
        bal = get_balance(user_id)

        if bal < amount:
            await interaction.response.send_message(f"❌ Bạn không đủ tiền! Số dư: **{bal:,} xu**. Gõ `!xin` để nhận thêm vốn!", ephemeral=True)
            return

        if user_id not in self.view_ref.bets:
            self.view_ref.bets[user_id] = []
        
        self.view_ref.bets[user_id].append({
            'choice': self.bet_choice,
            'amount': amount,
            'name': interaction.user.display_name
        })

        await interaction.response.send_message(f"✅ Đã nhận cược **{amount:,} xu** vào cửa **{self.bet_choice}** thành công! 🎰", ephemeral=True)

class FullTaiXiuView(View):
    def __init__(self):
        super().__init__(timeout=40)
        self.bets = {}
        self.create_buttons()

    def create_buttons(self):
        choices = [
            ("🔴 Xỉu (3-10)", "Xỉu", discord.ButtonStyle.danger, 0),
            ("🟢 Tài (11-18)", "Tài", discord.ButtonStyle.success, 0),
            ("🔵 Chẵn", "Chẵn", discord.ButtonStyle.primary, 0),
            ("🟣 Lẻ", "Lẻ", discord.ButtonStyle.secondary, 0)
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
    print(f'🤖 Bot {bot.user.name} đã sẵn sàng trực tuyến!')

# ==========================================
# LỆNH XEM SỐ DƯ & XIN TIỀN
# ==========================================
@bot.command(name='taikhoan')
async def taikhoan(ctx):
    bal = get_balance(ctx.author.id)
    await ctx.send(f"💰 Ví tiền của **{ctx.author.display_name}**: **{bal:,} xu** 💎")

@bot.command(name='xin')
async def xin(ctx):
    uid = ctx.author.id
    bal = get_balance(uid)
    if bal < 50000: # Được xin khi dưới 50k xu
        user_balances[uid] += 50000
        await ctx.send(f"🎁 Đại gia bố thí cho **{ctx.author.display_name}** **+50,000 xu** làm vốn! Số dư mới: **{user_balances[uid]:,} xu** 🔥")
    else:
        await ctx.send(f"⚠️ Số dư của bạn còn nhiều (**{bal:,} xu**), tự làm tự ăn đi không cho xin nữa! 😎")

@bot.command(name='stop')
async def stop(ctx):
    channel_id = ctx.channel.id
    if running_games.get(channel_id):
        running_games[channel_id] = False
        await ctx.send("🛑 Đã nhận lệnh dừng! Sòng bài sẽ tự động đóng sau khi ván hiện tại kết thúc...")
    else:
        await ctx.send("⚠️ Kênh này hiện không có sòng tài xỉu tự động nào đang chạy.")


# ==========================================
# VÒNG LẶP TÀI XỈU TỰ ĐỘNG LIÊN TỤC
# ==========================================
@bot.command(name='taixiu')
async def taixiu(ctx):
    channel_id = ctx.channel.id
    if running_games.get(channel_id):
        await ctx.send("⚠️ Sòng Tài Xỉu tự động ở kênh này đang chạy rồi! Gõ `!stop` nếu muốn tắt.")
        return

    running_games[channel_id] = True
    await ctx.send("🎰 **[SÒNG CASINO HUY UY TÍN]** Bắt đầu chuỗi ván chơi tự động liên tục! Gõ `!stop` để dừng lại bất cứ lúc nào.")

    vc = None
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

    while running_games.get(channel_id):
        view = FullTaiXiuView()
        
        embed = discord.Embed(
            title="🎲 SÒNG CASINO HUY UY TÍN CHÂU Á - VÁN MỚI BẮT ĐẦU!",
            description="⚡ Hãy bấm chọn cửa đặt bên dưới, sau đó nhập số tiền cược tùy ý!\n\n⏳ **Thời gian cược: 30 giây**\n\n⚀ ⚁ ⚂",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=DICE_GIF_URL)
        
        msg = await ctx.send(embed=embed, view=view)

        if vc:
            asyncio.create_task(play_audio(vc, "start.mp3"))

        # Đếm ngược 30 giây đặt cược
        for remain in range(29, -1, -1):
            if not running_games.get(channel_id):
                break
            await asyncio.sleep(1)
            rand_d1 = DICE_EMOJIS[random.randint(1, 6)]
            rand_d2 = DICE_EMOJIS[random.randint(1, 6)]
            rand_d3 = DICE_EMOJIS[random.randint(1, 6)]
            try:
                embed.description = f"⚡ Hãy bấm chọn cửa đặt bên dưới, sau đó nhập số tiền cược tùy ý!\n\n⏳ **Đếm ngược: {remain} giây**\n\n{rand_d1} {rand_d2} {rand_d3}"
                await msg.edit(embed=embed)
            except Exception:
                pass

        if not running_games.get(channel_id):
            try:
                await msg.delete()
            except:
                pass
            break

        # Khóa nút bấm
        for child in view.children:
            child.disabled = True
        
        embed.title = "🎲 SÒNG CASINO - ĐÃ KHÓA CƯỢC, ĐANG MỞ BÁT!"
        embed.description = "🔒 Hết giờ đặt cược! Đang lắc xí ngầu..."
        embed.color = discord.Color.gold()
        await msg.edit(embed=embed, view=view)

        if vc:
            await play_audio(vc, "end.mp3")

        await asyncio.sleep(1)

        # Tính kết quả
        d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
        tong = d1 + d2 + d3
        
        kq_taixiu = "Tài" if tong >= 11 else "Xỉu"
        kq_chanle = "Chẵn" if tong % 2 == 0 else "Lẻ"
        
        result_embed = discord.Embed(
            title=f"🎉 KẾT QUẢ: {DICE_EMOJIS[d1]} {DICE_EMOJIS[d2]} {DICE_EMOJIS[d3]} = {tong} ➔ {kq_taixiu.upper()} ({kq_chanle.upper()})!",
            color=discord.Color.green() if kq_taixiu == "Tài" else discord.Color.red()
        )
        result_embed.set_thumbnail(url=DICE_GIF_URL)

        has_win = False
        has_bet = False

        if not view.bets:
            result_embed.description = "Ván này không có ai đặt cược cả!"
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
                        amount *= 5 # Trúng số chuẩn ăn x5
                    
                    if is_win:
                        user_balances[uid] = get_balance(uid) + amount
                        summary.append(f"🟢 **{name}**: Thắng **+{amount:,} xu** ({choice})")
                        if uid == ctx.author.id:
                            has_win = True
                    else:
                        # Trừ tiền, nếu âm thì về 0
                        current_bal = get_balance(uid)
                        user_balances[uid] = max(0, current_bal - amount)
                        summary.append(f"🔴 **{name}**: Thua **-{amount:,} xu** ({choice})")
                        
            result_embed.description = "\n".join(summary)

        await ctx.send(embed=result_embed)

        if vc and has_bet:
            if has_win:
                await play_audio(vc, "win.mp3")
            else:
                await play_audio(vc, "lose.mp3")

        # Kiểm tra xem có lệnh dừng chưa
        if not running_games.get(channel_id):
            break

        # Đếm ngược 5 giây sống động để sang ván tiếp theo
        countdown_msg = await ctx.send("🔄 *Sòng bài tiếp tục mở bàn sau **5 giây** nữa... Chuẩn bị vốn nào!* ⏳")
        for sec in range(5, 0, -1):
            if not running_games.get(channel_id):
                break
            try:
                await countdown_msg.edit(content=f"🔄 *Sòng bài tiếp tục mở bàn sau **{sec} giây** nữa... Chuẩn bị vốn nào!* ⏳")
            except:
                pass
            await asyncio.sleep(1)
        
        try:
            await countdown_msg.delete()
        except:
            pass

    # Ngắt voice khi dừng hẳn
    if vc and vc.is_connected():
        await vc.disconnect()

    running_games[channel_id] = False
    await ctx.send("🛑 **Sòng Tài Xỉu tự động đã chính thức đóng cửa!** Gõ `!taixiu` để mở lại bất cứ lúc nào.")


# ==========================================
# 3. KHỞI CHẠY BOT AN TOÀN
# ==========================================
if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("LỖI: Không tìm thấy DISCORD_TOKEN trên Render!")
