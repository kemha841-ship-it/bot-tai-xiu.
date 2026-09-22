import os
import random
import asyncio
import threading
from datetime import date
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
    return "Bot Tai Xiu VIP & Leveling is running!"

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
last_checkin = {} 
running_games = {} 
recent_results = {} # Lưu lịch sử theo channel_id

# Hệ thống lưu trữ Level và XP của thành viên
user_levels = {} # Format: {user_id: {'xp': 0, 'level': 1}}

SECRET_ADMIN_CODE = "pro"

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
        user_balances[user_id] = 100000 
    return user_balances[user_id]

async def update_vip_nickname(member: discord.Member, level: int):
    """Tự động thêm chữ [VIP 👑] vào tên khi đạt level max (ví dụ >= 999)"""
    try:
        if member.guild.me.guild_permissions.manage_nicknames:
            current_name = member.display_name
            if level >= 999 and "[VIP 👑]" not in current_name:
                new_name = f"[VIP 👑] {current_name}"
                if len(new_name) <= 32: # Giới hạn tên của Discord
                    await member.edit(nick=new_name)
    except Exception as e:
        print(f"Không thể đổi biệt danh VIP cho {member.name}: {e}")

def add_user_xp(user_id, guild_id):
    if user_id not in user_levels:
        user_levels[user_id] = {'xp': 0, 'level': 1}
    
    # Cộng ngẫu nhiên từ 15 đến 25 XP mỗi tin nhắn
    xp_gain = random.randint(15, 25)
    user_levels[user_id]['xp'] += xp_gain
    
    current_level = user_levels[user_id]['level']
    current_xp = user_levels[user_id]['xp']
    
    # Công thức tính XP để lên cấp: Level * 100 XP (Giới hạn tối đa level 999)
    if current_level >= 999:
        user_levels[user_id]['level'] = 999
        return False, 999, 0

    xp_needed = current_level * 100
    
    if current_xp >= xp_needed:
        user_levels[user_id]['level'] += 1
        user_levels[user_id]['xp'] -= xp_needed
        new_lvl = user_levels[user_id]['level']
        
        # Thưởng xu khi lên cấp: Level mới * 10,000 xu
        reward_money = new_lvl * 10000
        user_balances[user_id] = get_balance(user_id) + reward_money
        
        return True, new_lvl, reward_money
    
    return False, current_level, 0

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
            await interaction.response.send_message(f"❌ Bạn không đủ tiền! Số dư hiện tại của bạn: **{bal:,} xu**.", ephemeral=True)
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
    try:
        await bot.tree.sync()
        print("Đã đồng bộ toàn bộ Slash Commands thành công!")
    except Exception as e:
        print(f"Lỗi đồng bộ slash command: {e}")
    print(f'🤖 Bot {bot.user.name} đã sẵn sàng trực tuyến!')

# ==========================================
# LẮNG NGHE TIN NHẮN ĐỂ TỰ ĐỘNG TĂNG LEVEL (XP)
# ==========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    uid = message.author.id
    guild = message.guild
    
    # Kiểm tra nếu là Admin hoặc Chủ server -> Mặc định gán Level 999 và kích hoạt thẻ VIP
    is_admin = False
    if guild:
        if message.author == guild.owner or message.author.guild_permissions.administrator:
            is_admin = True
            
    if is_admin:
        if uid not in user_levels:
            user_levels[uid] = {'xp': 99999, 'level': 999}
        else:
            user_levels[uid]['level'] = 999
        await update_vip_nickname(message.author, 999)
    else:
        # Tự động cộng XP khi thành viên thường chat
        leveled_up, new_level, reward_money = add_user_xp(uid, guild.id if guild else None)
        if leveled_up:
            await message.channel.send(
                f"🎉 **[THĂNG CẤP CỰC CHÁY]** Chúc mừng {message.author.mention} đã đột phá lên **Level {new_level}**! 🚀🔥\n"
                f"🎁 *Phần thưởng thăng cấp:* Nhận ngay **+{reward_money:,} xu** vào ví!"
            )
            if new_level >= 999:
                await update_vip_nickname(message.author, new_level)
                await message.channel.send(f"👑 **[VINH QUANG TỐI THƯỢNG]** {message.author.mention} đã chạm mốc Level Max và chính thức nhận danh hiệu **[VIP 👑]**!")

    await bot.process_commands(message)

# ==========================================
# CÁC LỆNH TIỆN ÍCH & SLASH COMMANDS
# ==========================================
@bot.command(name='taikhoan')
async def taikhoan(ctx):
    bal = get_balance(ctx.author.id)
    await ctx.send(f"💰 Ví tiền của **{ctx.author.display_name}**: **{bal:,} xu** 💎")

@bot.command(name='diemdanh')
async def diemdanh(ctx):
    uid = ctx.author.id
    today = date.today()
    
    if last_checkin.get(uid) == today:
        await ctx.send(f"⚠️ **{ctx.author.display_name}** ơi, hôm nay bạn đã điểm danh rồi! Hãy quay lại vào ngày mai nhé. ⏳")
        return
    
    last_checkin[uid] = today
    user_balances[uid] = get_balance(uid) + 50000
    await ctx.send(f"🎁 Điểm danh thành công! **{ctx.author.display_name}** nhận được **+50,000 xu** vốn hằng ngày. Số dư mới: **{user_balances[uid]:,} xu** 🔥")

@bot.tree.command(name="admin", description="Lệnh nạp xu dành riêng cho Admin")
async def slash_admin(interaction: discord.Interaction, code: str):
    if code == SECRET_ADMIN_CODE:
        uid = interaction.user.id
        user_balances[uid] = get_balance(uid) + 50000
        await interaction.response.send_message(
            f"👑 **[ADMIN PRO]** Chào sếp **{interaction.user.display_name}**! Đã nạp thành công **+50,000 xu** qua mã `pro`. Số dư mới: **{user_balances[uid]:,} xu** 🔥", 
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ Mã code Admin không chính xác!", 
            ephemeral=True
        )

@bot.tree.command(name="top", description="Xem bảng xếp hạng đại gia giàu nhất sòng bài")
async def slash_top(interaction: discord.Interaction):
    if not user_balances:
        await interaction.response.send_message("📊 Sòng bài chưa có dữ liệu tài khoản nào!", ephemeral=True)
        return
    
    sorted_users = sorted(user_balances.items(), key=lambda item: item[1], reverse=True)[:10]
    
    embed = discord.Embed(
        title="🏆 BẢNG XẾP HẠNG ĐẠI GIA TÀI XỈU",
        description="Top 10 các tay chơi giàu nhất hệ thống casino:",
        color=discord.Color.gold()
    )
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, (uid, bal) in enumerate(sorted_users):
        user_obj = bot.get_user(uid)
        name = user_obj.display_name if user_obj else f"Member ID: {uid}"
        embed.add_field(name=f"{medals[idx]} {name}", value=f"💎 **{bal:,} xu**", inline=False)
        
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="lichsu", description="Xem lại kết quả 10 ván tài xỉu gần nhất để soi cầu")
async def slash_lichsu(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    history_list = recent_results.get(channel_id, [])
    if not history_list:
        await interaction.response.send_message("📊 Chưa có ván chơi nào diễn ra trong kênh này!", ephemeral=True)
        return
        
    history_str = "\n".join(history_list[-10:])
    embed = discord.Embed(
        title="📈 LỊCH SỬ SOI CẦU 10 VÁN GẦN NHẤT",
        description=history_str,
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="chuyenxu", description="Chuyển xu cho thành viên khác trong server")
async def slash_chuyenxu(interaction: discord.Interaction, member: discord.Member, so_tien: int):
    sender_id = interaction.user.id
    receiver_id = member.id
    
    if sender_id == receiver_id:
        await interaction.response.send_message("❌ Bạn không thể tự chuyển xu cho chính mình được!", ephemeral=True)
        return
        
    if so_tien <= 0:
        await interaction.response.send_message("❌ Số tiền chuyển phải lớn hơn 0!", ephemeral=True)
        return
        
    sender_bal = get_balance(sender_id)
    if sender_bal < so_tien:
        await interaction.response.send_message(f"❌ Bạn không đủ số dư! Ví hiện tại của bạn chỉ có: **{sender_bal:,} xu**.", ephemeral=True)
        return
        
    user_balances[sender_id] = sender_bal - so_tien
    user_balances[receiver_id] = get_balance(receiver_id) + so_tien
    
    await interaction.response.send_message(
        f"💸 **GIAO DỊCH THÀNH CÔNG!**\n👤 Sếp **{interaction.user.display_name}** đã chuyển thành công **{so_tien:,} xu** cho {member.mention}! 🤝"
    )

# Lệnh kiểm tra cấp độ (/level) - Admin và người đạt Max Level tự động có huy hiệu VIP
@bot.tree.command(name="level", description="Kiểm tra cấp độ (Level) và điểm kinh nghiệm (XP) hiện tại")
async def slash_level(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    uid = target.id
    
    is_admin = False
    if interaction.guild:
        if target == interaction.guild.owner or target.guild_permissions.administrator:
            is_admin = True
            
    if is_admin:
        lvl = 999
        xp_str = "MAX (Vô Cực) 👑"
        title_rank = "⭐ TRÙM TỐI CAO - ADMIN VIP"
    else:
        data = user_levels.get(uid, {'xp': 0, 'level': 1})
        lvl = data['level']
        xp = data['xp']
        xp_needed = lvl * 100
        xp_str = f"{xp} / {xp_needed} XP"
        
        if lvl >= 999:
            title_rank = "💎 HUYỀN THOẠI VIP"
        elif lvl >= 20:
            title_rank = "🔥 ĐẠI GIA KHÉT TIẾNG"
        elif lvl >= 10:
            title_rank = "⚡ TAY CHƠI KỲ CỰU"
        else:
            title_rank = "🌱 TẬP SỰ SÒNG BÀI"
    
    embed = discord.Embed(
        title=f"📊 HỒ SƠ CẤP ĐỘ: {target.display_name.upper()}",
        description=f"👑 **Danh hiệu:** `{title_rank}`\n⭐ **Level:** `{lvl}`\n✨ **Tiến trình XP:** `{xp_str}`",
        color=discord.Color.gold() if lvl >= 999 else discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

@bot.command(name='stop')
async def stop(ctx):
    channel_id = ctx.channel.id
    if running_games.get(channel_id):
        running_games[channel_id] = False
        await ctx.send("🛑 Đã nhận lệnh dừng! Sòng bài sẽ tự động đóng sau khi ván hiện tại kết thúc...")
    else:
        await ctx.send("⚠️ Kênh này hiện không có sòng tài xỉu tự động nào đang chạy.")


# ==========================================
# VÒNG LẶP TÀI XỈU TỰ ĐỘNG CHUẨN XÁC SUẤT
# ==========================================
@bot.command(name='taixiu')
async def taixiu(ctx):
    channel_id = ctx.channel.id
    if running_games.get(channel_id):
        await ctx.send("⚠️ Sòng Tài Xỉu tự động ở kênh này đang chạy rồi! Gõ `!stop` nếu muốn tắt.")
        return

    running_games[channel_id] = True
    await ctx.send("🎰 **[SÒNG CASINO HUY UY TÍN]** Bắt đầu chuỗi ván chơi tự động liên tục chuẩn xác suất! Gõ `!stop` để dừng lại bất cứ lúc nào.")

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

        for remain in range(29, -1, -1):
            if not running_games.get(channel_id):
                break
            await asyncio.sleep(1)
            rand_d1 = DICE_EMOJIS[random.randint(1, 6)]
            rand_d2 = DICE_EMOJIS[random.randint(1, 6)]
            rand_d3 = DICE_EMOJIS[random.randint(1, 6)]
            try:
                embed.description = f"⚡ Hãy bấm chọn cửa đặt bên dưới, sau đó nhập số tiền cược tùy ý!\n\n⏳ **Đếm ngược: {remain} giây**\n\n🎲 Xúc xắc đang lắc: {rand_d1} {rand_d2} {rand_d3}"
                await msg.edit(embed=embed)
            except Exception:
                pass

        if not running_games.get(channel_id):
            try:
                await msg.delete()
            except:
                pass
            break

        for child in view.children:
            child.disabled = True
        
        embed.title = "🎲 SÒNG CASINO - ĐÃ KHÓA CƯỢC, ĐANG MỞ BÁT!"
        embed.description = "🔒 Hết giờ đặt cược! Đang lắc xí ngầu..."
        embed.color = discord.Color.gold()
        await msg.edit(embed=embed, view=view)

        if vc:
            await play_audio(vc, "end.mp3")

        await asyncio.sleep(1)

        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        d3 = random.randint(1, 6)
        tong = d1 + d2 + d3
        
        kq_taixiu = "Tài" if tong >= 11 else "Xỉu"
        kq_chanle = "Chẵn" if tong % 2 == 0 else "Lẻ"
        
        if channel_id not in recent_results:
            recent_results[channel_id] = []
        recent_results[channel_id].append(f"🎲 `{DICE_EMOJIS[d1]} {DICE_EMOJIS[d2]} {DICE_EMOJIS[d3]}` = **{tong}** ➔ **{kq_taixiu.upper()}** ({kq_chanle.upper()})")
        if len(recent_results[channel_id]) > 30:
            recent_results[channel_id].pop(0)
        
        result_embed = discord.Embed(
            title=f"🎉 KẾT QUẢ: {DICE_EMOJIS[d1]} {DICE_EMOJIS[d2]} {DICE_EMOJIS[d3]} = {tong} ➔ {kq_taixiu.upper()} ({kq_chanle.upper()})!",
            color=discord.Color.green() if kq_taixiu == "Tài" else discord.Color.red()
        )
        result_embed.set_thumbnail(url=DICE_GIF_URL)

        has_win = False
        has_bet = False

        if not view.bets:
            result_embed.description = "⚠️ **Ván này không có ai đặt cược cả! Sòng bài tự động đóng cửa để tiết kiệm điện.**"
            await ctx.send(embed=result_embed)
            running_games[channel_id] = False
            break
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
                        user_balances[uid] = get_balance(uid) + amount
                        summary.append(f"🟢 **{name}**: Thắng **+{amount:,} xu** ({choice})")
                        if uid == ctx.author.id:
                            has_win = True
                    else:
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

        if not running_games.get(channel_id):
            break

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

    if vc and vc.is_connected():
        await vc.disconnect()

    running_games[channel_id] = False
    await ctx.send("🛑 **Sòng Tài Xỉu tự động đã chính thức đóng cửa!** (Do không có ai cược hoặc do bạn bấm `!stop`).")


# ==========================================
# 3. KHỞI CHẠY BOT AN TOÀN
# ==========================================
if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("LỖI: Không tìm thấy DISCORD_TOKEN trên Render!")
