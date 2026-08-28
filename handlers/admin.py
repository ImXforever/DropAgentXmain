import asyncio

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    get_db, get_all_users_count, get_total_products, get_total_sales,
    update_credits, get_user, ban_user,
    set_deposit_status, set_withdrawal_status,
    approve_deposit_manual, reject_withdrawal_and_refund,
    list_pending_deposits, list_pending_withdrawals,
    get_setting as db_get_setting, set_setting,
)
from config import config
from utils import send_safe, edit_safe, esc_md

router = Router()


class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_user_msg = State()
    waiting_social_task = State()
    waiting_ai_value = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def notify_admins(bot: Bot, text: str, kb=None):
    """Admin notifications that survive Markdown-breaking content (TXIDs etc.)."""
    from aiogram.exceptions import TelegramBadRequest
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="Markdown")
            continue
        except TelegramBadRequest:
            pass
        except Exception:
            continue
        try:
            await bot.send_message(admin_id, text[:4000], reply_markup=kb, parse_mode=None)
        except Exception:
            continue


# ---------- Force-channel gate helpers (called from start router) ----------

async def is_member_of_force_channel(bot, user_id: int) -> bool:
    channel = await db_get_setting("force_channel")
    on = await db_get_setting("force_channel_on", "0")
    if not channel or on != "1":
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return True  # misconfigured → fail-open


async def join_gate_kb() -> InlineKeyboardMarkup:
    ch = (await db_get_setting("force_channel") or "channel").lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 عضویت در کانال", url=f"https://t.me/{ch}")],
        [InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="fc_check")],
    ])


def _panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Dashboard", callback_data="admin_dashboard"),
         InlineKeyboardButton(text="👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton(text="🟡 Deposits", callback_data="adm_deps"),
         InlineKeyboardButton(text="🔵 Withdrawals", callback_data="adm_wds")],
        [InlineKeyboardButton(text="🔒 قفل کانال", callback_data="adm_fc"),
         InlineKeyboardButton(text="📣 تسک سوشال", callback_data="adm_social")],
        [InlineKeyboardButton(text="🛡 تأیید محصولات", callback_data="adm_prods"),
         InlineKeyboardButton(text="⚙️ متغیرها", callback_data="adm_vars")],
        [InlineKeyboardButton(text="🔒 قفل پلتفرم", callback_data="adm_lock")],
        [InlineKeyboardButton(text="🤖 تنظیمات AI", callback_data="adm_ai"),
         InlineKeyboardButton(text="💰 Add Credits", callback_data="admin_add_credits")],
        [InlineKeyboardButton(text="📣 Broadcast", callback_data="admin_broadcast")],
    ])


@router.message(F.text == "/admin")
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ دسترسی ندارید.")
        return

    total_users = await get_all_users_count()
    total_products = await get_total_products()
    total_sales = await get_total_sales()

    await message.answer(
        f"🔧 **Admin Panel**\n\n"
        f"👥 کاربران: {total_users}\n"
        f"📦 محصولات: {total_products}\n"
        f"🛒 فروش‌ها: {total_sales}",
        reply_markup=_panel_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    total_users = await get_all_users_count()
    total_products = await get_total_products()
    total_sales = await get_total_sales()

    await edit_safe(callback.message, 
        f"🔧 **Admin Panel**\n\n"
        f"👥 کاربران: {total_users}\n"
        f"📦 محصولات: {total_products}\n"
        f"🛒 فروش‌ها: {total_sales}",
        reply_markup=_panel_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    total_users = await get_all_users_count()
    total_products = await get_total_products()
    total_sales = await get_total_sales()

    async with get_db() as db:
        cursor = await db.execute("SELECT COALESCE(SUM(credits), 0) FROM users")
        total_credits = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(price_credits), 0) FROM purchases"
        )
        total_revenue = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE tx_type = 'task_creation'")
        ad_budget = abs((await cursor.fetchone())[0])

        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL")
        total_refs = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM products WHERE status='pending'")
        pending_prods = (await cursor.fetchone())[0]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")],
    ])

    commission_earned = int(total_revenue * config.COMMISSION_RATE)
    await edit_safe(callback.message, 
        f"📊 **Admin Dashboard**\n\n"
        f"👥 کل کاربران: {total_users}\n"
        f"📦 محصولات فعال: {total_products}\n"
        f"🛒 کل فروش: {total_sales}\n"
        f"💰 کردیت در گردش: {total_credits}\n"
        f"💵 حجم معاملات: {total_revenue} کردیت\n"
        f"🏦 درآمد کمیسیون شما (~{int(config.COMMISSION_RATE*100)}%): {commission_earned} کردیت\n"
        f"📣 بودجه تبلیغات تسک‌ها: {ad_budget} کردیت\n"
        f"👥 کل دعوت‌شده‌ها (ریفرال): {total_refs}\n"
        f"🛡 محصولات در انتظار تأیید: {pending_prods}",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, credits, is_banned FROM users ORDER BY credits DESC LIMIT 20"
        )
        rows = await cursor.fetchall()

    text = "👥 **کاربران (بر اساس کردیت):**\n\n"
    for uid, username, first_name, credits, banned in rows:
        status = "🚫" if banned else "✅"
        name = esc_md(first_name or "-")
        uname = esc_md(username or "-")
        text += f"{status} {name} (@{uname}) — {credits}💰\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "admin_add_credits")
async def admin_add_credits_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    await edit_safe(callback.message, 
        "💰 **افزودن کردیت**\n\n"
        "این دستور رو بفرست:\n"
        "`/addcredits user_id مقدار`\n\n"
        "مثال: `/addcredits 123456789 100`\n"
        "(مقدار منفی = کسر کردیت)",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(F.text.startswith("/addcredits"))
async def add_credits_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("فرمت: `/addcredits user_id مقدار`", parse_mode="Markdown")
        return

    try:
        target_user_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ user_id و مقدار باید عدد باشن.")
        return

    from database import get_user
    user = await get_user(target_user_id)
    if not user:
        await message.answer("❌ کاربر پیدا نشد!")
        return

    await update_credits(target_user_id, amount, "admin_grant", f"Admin granted {amount} credits")
    fresh = await get_user(target_user_id)
    await message.answer(
        f"✅ {amount:+d} کردیت برای `{target_user_id}` اعمال شد.\n"
        f"موجودی جدید: {fresh['credits']}",
        parse_mode="Markdown",
    )


@router.message(F.text.startswith("/setrole"))
async def set_role_command(message: Message):
    """Godfather command: /setrole user_id soldier|capo|associate|underboss [category]"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "👑 **انتصاب رتبه**\n\n"
            "`/setrole user_id soldier`\n"
            "`/setrole user_id capo`\n"
            "`/setrole user_id associate`\n"
            "`/setrole user_id underboss education`\n\n"
            "دسته‌ها: education graphics coding content template tools general",
            parse_mode="Markdown",
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id باید عدد باشه.")
        return

    role = parts[2].lower()
    domain = parts[3].lower() if len(parts) > 3 else None
    valid_cats = {"education", "graphics", "coding", "content", "template", "tools", "general"}

    if role == "underboss" and (domain not in valid_cats):
        await message.answer("❌ آندرباس باید دسته داشته باشه: `/setrole uid underboss education`")
        return

    from database import set_role as db_set_role, ROLE_FA, get_user
    target = await get_user(target_id)
    if not target:
        await message.answer("❌ کاربر پیدا نشد (اول تو بات /start بزنه).")
        return

    ok = await db_set_role(target_id, role, granted_by=message.from_user.id, domain=domain)
    if not ok:
        await message.answer("❌ رتبه نامعتبر.")
        return

    title_fa = "👑 باس بزرگ" if role in ("godfather",) and target_id in config.ADMIN_IDS else ROLE_FA.get(role, role)
    domain_line = f"\nقلمرو: {domain}" if domain else ""
    await message.answer(f"✅ `{target_id}` الان **{title_fa}** شد.{domain_line}", parse_mode="Markdown")
    try:
        rank_msg = {
            "soldier": "🪖 تو **سرباز** شدی — فروشگاه شخصی‌ات رسماً مال خودته + کد تخفیف فعال!",
            "capo": "🕴️ تو **کاپو** شدی — تیم معرفی دست توئه و اوورراید می‌گیری!",
            "underboss": f"👔 تو **آندرباس حوزه {domain}** شدی — داشبورد و مدیریت محصولات حوزه‌ات در «👑 قلمرو»!",
            "associate": "🎓 رتبه‌ات به **کارآموز** برگشت.",
        }.get(role)
        if rank_msg:
            await message.bot.send_message(target_id, rank_msg, parse_mode="Markdown")
    except Exception:
        pass


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_broadcast)
    await edit_safe(callback.message, 
        "📣 **ارسال پیام همگانی**\n\n"
        "پیامی که می‌خواهی به همه کاربران برسه رو بفرست.\n"
        "برای لغو /cancel بزن.",
        parse_mode="Markdown",
    )
    await callback.answer()


# ---------------- Treasury management ----------------

DEP_STATUS_ICON = {"pending": "🟡", "approved": "✅", "rejected": "❌"}
WD_STATUS_ICON = {"pending": "🔵", "paid": "💸", "rejected": "↩️"}


@router.callback_query(F.data == "adm_deps")
async def adm_deps_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    deps = await list_pending_deposits(10)
    if not deps:
        text = "🟡 **واریزهای در انتظار:** هیچ"
    else:
        rows = []
        for d in deps:
            u = await get_user(d["user_id"])
            uname = f"@{u['username']}" if u and u.get("username") else str(d["user_id"])
            rows.append(f"#{d['id']} | {d['amount_usdt']:g}$ | {d['network']} | {uname}")
        text = "🟡 **واریزهای در انتظار** (از نوتیف هر آیتم، تأیید/رد بزن):\n\n" + "\n".join(rows)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_deps")],
        [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "adm_wds")
async def adm_wds_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    wds = await list_pending_withdrawals(10)
    if not wds:
        text = "🔵 **برداشت‌های در انتظار:** هیچ"
    else:
        rows = []
        for w in wds:
            payout = w["amount_usdt"] - w["fee_usdt"]
            rows.append(f"#{w['id']} | pay {payout:g}$ | {w['network']} | `{w['address'][:14]}…`")
        text = "🔵 **برداشت‌های در انتظار** («پرداخت شد» یعنی واریز کردی؛ «رد» یعنی به حسابش برگشت):\n\n" + "\n".join(rows)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_wds")],
        [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_dep_ok_"))
async def adm_dep_approve(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    dep_id = int(callback.data.rsplit("_", 1)[1])
    from database import usdt_to_credits
    dep = await approve_deposit_manual(dep_id, callback.from_user.id)
    if not dep:
        await callback.answer("این درخواست قبلاً بررسی شده!", show_alert=True)
        return

    credits = usdt_to_credits(dep["amount_usdt"])
    await update_credits(dep["user_id"], credits, "deposit", f"Deposit #{dep_id} approved")

    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await callback.bot.send_message(
            dep["user_id"],
            f"✅ واریز #{dep_id} تأیید شد!\n💰 {credits:,} کردیت به حسابت اضافه شد.",
        )
    except Exception:
        pass
    await callback.answer(f"واریز #{dep_id} تأیید شد (+{credits:,})", show_alert=True)


@router.callback_query(F.data.startswith("adm_dep_no_"))
async def adm_dep_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    dep_id = int(callback.data.rsplit("_", 1)[1])
    dep = await set_deposit_status(dep_id, "rejected", callback.from_user.id)
    if not dep:
        await callback.answer("این درخواست قبلاً بررسی شده!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await callback.bot.send_message(
            dep["user_id"],
            f"❌ واریز #{dep_id} تأیید نشد. اگر مبلغ کم شده با پشتیبانی تماس بگیر.",
        )
    except Exception:
        pass
    await callback.answer(f"واریز #{dep_id} رد شد", show_alert=True)


@router.callback_query(F.data.startswith("adm_wd_ok_"))
async def adm_wd_paid(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    wd_id = int(callback.data.rsplit("_", 1)[1])
    wd = await set_withdrawal_status(wd_id, "paid", callback.from_user.id)
    if not wd:
        await callback.answer("این درخواست قبلاً بررسی شده!", show_alert=True)
        return

    payout = wd["amount_usdt"] - wd["fee_usdt"]
    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await callback.bot.send_message(
            wd["user_id"],
            f"💸 برداشت #{wd_id} پرداخت شد!\n📩 {payout:g} USDT به کیف پولت ارسال شد.",
        )
    except Exception:
        pass
    await callback.answer(f"برداشت #{wd_id} علامت پرداخت‌شده خورد", show_alert=True)


@router.callback_query(F.data.startswith("adm_wd_no_"))
async def adm_wd_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    wd_id = int(callback.data.rsplit("_", 1)[1])
    wd = await reject_withdrawal_and_refund(wd_id, callback.from_user.id)
    if not wd:
        await callback.answer("این درخواست قبلاً بررسی شده!", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await callback.bot.send_message(
            wd["user_id"],
            f"↩️ برداشت #{wd_id} رد شد و {_fmt(wd['amount_usdt'])} USDT به حسابت برگشت.",
        )
    except Exception:
        pass
    await callback.answer(f"برداشت #{wd_id} رد و مبلغ برگشت داده شد", show_alert=True)


def _fmt(x: float) -> str:
    return f"{x:g}"


@router.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("↩️ Broadcast لغو شد.")
        return

    await state.clear()
    status = await message.answer("⏳ در حال ارسال...")

    async with get_db() as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        rows = await cursor.fetchall()

    sent = failed = 0
    for (uid,) in rows:
        try:
            # copy_message supports ALL content types (photo/video/text/…)
            await bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        if sent % 25 == 0:
            await asyncio.sleep(1)

    await status.edit_text(f"📣 Broadcast تمام شد.\n✅ ارسال شد: {sent}\n❌ ناموفق: {failed}")


# ================= User control =================

@router.message(F.text.startswith("/user"))
async def user_info_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("`/user <user_id>`", parse_mode="Markdown")
        return
    uid = int(parts[1])
    u = await get_user(uid)
    if not u:
        await message.answer("❌ کاربر پیدا نشد.")
        return

    from database import count_total_refs, count_qualified_refs
    stats = {
        "نام": u.get("first_name") or "-",
        "یوزرنیم": f"@{u.get('username')}" if u.get("username") else "-",
        "کردیت": f"{u['credits']:,}",
        "فروش": u.get("products_sold", 0),
        "بن": "🚫" if u.get("is_banned") else "✅",
        "دعوت‌شده": f"{await count_total_refs(uid)} (فعال: {await count_qualified_refs(uid)})",
    }
    text = "👤 **پروفایل کاربر**\n\n" + "\n".join(f"• {k}: {v}" for k, v in stats.items())

    ban_label = "✅ رفع بن" if u.get("is_banned") else "🚫 بن"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_label, callback_data=f"adm_ban_{uid}_{0 if u.get('is_banned') else 1}")],
        [InlineKeyboardButton(text="📨 پیام به کاربر", callback_data=f"adm_msg_{uid}")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("adm_ban_"))
async def adm_toggle_ban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    _, _, uid, val = callback.data.split("_")
    await ban_user(int(uid), val == "1")
    await callback.answer("انجام شد.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_msg_"))
async def adm_dm_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    uid = int(callback.data.split("_")[2])
    await state.set_state(AdminStates.waiting_user_msg)
    await state.update_data(dm_uid=uid)
    await edit_safe(callback.message, f"📨 پیامت برای `{uid}` رو بفرست:\nلغو: /cancel", parse_mode="Markdown")
    await callback.answer()


@router.message(AdminStates.waiting_user_msg)
async def adm_dm_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("↩️ لغو شد.")
        return
    uid = data.get("dm_uid")
    if not uid:
        await state.clear()
        return
    await state.clear()
    try:
        await bot.copy_message(uid, message.chat.id, message.message_id)
        await message.answer("✅ ارسال شد.")
    except Exception as e:
        await message.answer(f"❌ ارسال ناموفق: {e}")


# ================= Force channel panel =================

@router.callback_query(F.data == "fc_open")
async def fc_open(callback: CallbackQuery):
    ch = await db_get_setting("force_channel") or "channel"
    await callback.answer(f"https://t.me/{ch.lstrip('@')}", show_alert=False)


@router.callback_query(F.data == "fc_check")
async def fc_check(callback: CallbackQuery):
    ok = await is_member_of_force_channel(callback.bot, callback.from_user.id)
    if ok:
        from handlers.start import cmd_start_payload
        await edit_safe(callback.message, "✅ عضویت تأیید شد! خوش آمدی 🎉")
        callback.message.text = "/start"
        await cmd_start_payload(callback.message)
    else:
        await callback.answer("هنوز عضو کانال نشدی!", show_alert=True)


@router.callback_query(F.data == "adm_fc")
async def adm_fc_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    ch = await db_get_setting("force_channel") or "— تنظیم نشده —"
    on = await db_get_setting("force_channel_on", "0") == "1"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🟢 قفعال است — خاموش کن" if on else "🔴 خاموش است — روشن کن",
            callback_data="adm_fc_toggle",
        )],
        [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
    ])
    status = "🟢 فعال" if on else "🔴 خاموش"
    await edit_safe(callback.message, 
        f"🔒 **قفل کانال**\n\n"
        f"کانال فعلی: `{ch}`\nوضعیت: {status}\n\n"
        f"تنظیم کانال جدید از ترمینال:\n`/forcechan @mychannel`",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(F.text.startswith("/forcechan"))
async def forcechan_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("`/forcechan @channel`  یا  `/forcechan off`", parse_mode="Markdown")
        return
    val = parts[1]
    if val.lower() == "off":
        await set_setting("force_channel_on", "0", message.from_user.id)
        await message.answer("🔒 قفل کانال خاموش شد.")
        return
    if not val.startswith("@"):
        await message.answer("❌ با @ شروع کن یا `off` بفرست.")
        return
    await set_setting("force_channel", val, message.from_user.id)
    await set_setting("force_channel_on", "1", message.from_user.id)
    await message.answer(f"✅ قفل روی `{val}` فعال شد.", parse_mode="Markdown")


@router.callback_query(F.data == "adm_fc_toggle")
async def adm_fc_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    cur = await db_get_setting("force_channel_on", "0")
    if not await db_get_setting("force_channel"):
        await callback.answer("اول /forcechan @channel بزن!", show_alert=True)
        return
    await set_setting("force_channel_on", "0" if cur == "1" else "1", callback.from_user.id)
    await adm_fc_panel(callback)


# ================= Social media tasks (1-10 credits) =================

@router.callback_query(F.data == "adm_social")
async def adm_social_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_social_task)
    await edit_safe(callback.message, 
        "📣 **تسک سوشال مدیا**\n\n"
        "فرمت بفرست:\n`عنوان | لینک | پاداش(1-10) | ظرفیت`\n\n"
        "مثال:\n`ری‌اکت پست | https://t.me/ch/12 | 5 | 200`\n\n"
        "بعد از ثبت، به همه کاربران هم اطلاع می‌ره!\nلغو: /cancel",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(AdminStates.waiting_social_task)
async def adm_social_create(message: Message, state: FSMContext, bot: Bot):
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("↩️ لغو شد.")
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) != 4:
        await send_safe(message, "❌ فرمت: `عنوان | لینک | پاداش | ظرفیت`")
        return
    title, url, reward_s, cap_s = parts
    if not url.startswith(("http://", "https://", "tg://")):
        await message.answer("❌ لینک نامعتبر.")
        return
    try:
        reward, cap = int(reward_s), int(cap_s)
    except ValueError:
        await message.answer("❌ پاداش/ظرفیت عدد باشه.")
        return
    if not (1 <= reward <= 10):
        await message.answer("❌ پاداش تسک سوشال بین **۱ تا ۱۰** کردیت.")
        return
    if not (1 <= cap <= 100000):
        await message.answer("❌ ظرفیت ۱ تا ۱۰۰٬۰۰۰.")
        return

    async with get_db() as db:
        await db.execute(
            """INSERT INTO tasks (title, task_type, target_url, credits_reward,
                                   max_completions, creator_id)
               VALUES (?, 'social', ?, ?, ?, ?)""",
            (title, url, reward, cap, message.from_user.id),
        )
        await db.commit()

    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 انجام بده (+%d💰)" % reward, callback_data="tasks_menu")],
    ])
    await message.answer(
        f"✅ تسک سوشال «{title}» ثبت شد ({cap} نفر × {reward}💰).",
    )

    # announce to all users
    async with get_db() as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        rows = await cursor.fetchall()

    sent = 0
    for (uid,) in rows:
        try:
            await bot.send_message(
                uid,
                f"📣 **تسک سوشال جدید!**\n\n{title}\n🎁 +{reward} کردیت فقط با یک کلیک!",
                reply_markup=kb,
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            continue
        if sent % 25 == 0:
            await asyncio.sleep(1)
    await message.answer(f"🔔 اطلاع‌رسانی: {sent} نفر.")


# ================= AI settings panel =================

def _mask(k: str) -> str:
    if not k:
        return "—"
    return k[:6] + "…" + k[-4:] if len(k) > 14 else "***"


@router.callback_query(F.data == "adm_ai")
async def adm_ai_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return

    from hermes_engine import get_ai_config
    conf = await get_ai_config()
    mode = None
    from hermes_engine import resolve_mode
    mode = resolve_mode()
    stream_on = (await db_get_setting("stream_enabled", "1")) == "1"
    fleet_on = (await db_get_setting("fleet_enabled", "1")) == "1"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Set API KEY", callback_data="aiset_key"),
         InlineKeyboardButton(text="🌐 Set ENDPOINT", callback_data="aiset_url")],
        [InlineKeyboardButton(text="🧠 Set MODEL", callback_data="aiset_model"),
         InlineKeyboardButton(text="♻️ Reset to .env", callback_data="aiset_reset")],
        [InlineKeyboardButton(text=f"⚡ استریم: {'روشن' if stream_on else 'خاموش'}", callback_data="aiset_stream")],
        [InlineKeyboardButton(text=f"🛰️ Fleet: {'روشن' if fleet_on else 'خاموش'}", callback_data="fleet_toggle")],
        [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, 
        f"🤖 **مدیریت دستی AI**\n\n"
        f"⚙️ موتور: `{mode}` | ⚡ استریم: `{'روشن' if stream_on else 'خاموش'}`\n"
        f"🛰️ Fleet: `{'روشن' if fleet_on else 'خاموش'}`\n"
        f"🌐 Endpoint:\n`{conf['base_url']}`\n"
        f"🔑 Key: `{_mask(conf['api_key'])}`\n"
        f"🧠 Model: `{conf['model']}`\n\n"
        f"هر تغییری فوری اعمال می‌شه (بدون ری‌استارت).\n"
        f"مدل هر نقش Fleet: `/fleetmodel cipher <model>`",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


AI_FIELDS = {"aiset_key": ("ai_api_key", "کلید API جدید رو بفرست:"),
             "aiset_url": ("ai_base_url", "Endpoint جدید (مثل https://host/v1):"),
             "aiset_model": ("ai_model", "نام مدل جدید:")}


@router.callback_query(F.data.startswith("aiset_"))
async def adm_ai_set(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    action = callback.data
    if action == "aiset_reset":
        for k in ("ai_api_key", "ai_base_url", "ai_model"):
            await set_setting(k, None, callback.from_user.id)
        from hermes_engine import invalidate_dyn_cache
        invalidate_dyn_cache()
        await callback.answer("بازگشت به مقادیر .env ✅", show_alert=True)
        await adm_ai_panel(callback)
        return
    if action == "aiset_stream":
        cur = (await db_get_setting("stream_enabled", "1")) == "1"
        await set_setting("stream_enabled", "0" if cur else "1", callback.from_user.id)
        from hermes_engine import invalidate_dyn_cache
        invalidate_dyn_cache()
        await callback.answer(f"استریم {'خاموش شد' if cur else 'روشن شد'} ⚡", show_alert=True)
        await adm_ai_panel(callback)
        return
    if action == "fleet_toggle":
        cur = (await db_get_setting("fleet_enabled", "1")) == "1"
        await set_setting("fleet_enabled", "0" if cur else "1", callback.from_user.id)
        await callback.answer(f"Fleet {'خاموش شد' if cur else 'روشن شد'} 🛰️", show_alert=True)
        await adm_ai_panel(callback)
        return
    field, prompt = AI_FIELDS[action]
    await state.set_state(AdminStates.waiting_ai_value)
    await state.update_data(ai_field=field)
    await edit_safe(callback.message, prompt)
    await callback.answer()


@router.message(AdminStates.waiting_ai_value)
async def adm_ai_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("↩️ لغو شد.")
        return
    data = await state.get_data()
    field = data.get("ai_field")
    if field not in ("ai_api_key", "ai_base_url", "ai_model"):
        await state.clear()
        return
    await set_setting(field, message.text.strip(), message.from_user.id)
    from hermes_engine import invalidate_dyn_cache
    invalidate_dyn_cache()
    await state.clear()
    await message.answer("✅ ذخیره و اعمال شد. با دکمه Test در پنل چک کن.")


@router.message(F.text == "/aitest")
async def ai_test_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    m = await message.answer("⏳ تست...")
    from hermes_engine import hermes_chat
    resp = await hermes_chat("سلام، در یک خط معرفی کن.")
    await m.edit_text(f"🧪 پاسخ موتور AI:\n\n{resp[:600]}", parse_mode=None)


@router.message(F.text.startswith("/fleetmodel"))
async def fleet_model_cmd(message: Message):
    """Set per-role model: /fleetmodel cipher gpt-4o-mini  |  /fleetmodel off"""
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        from fleet import ROLES, ROLE_FA
        await message.answer(
            "🛰️ `/fleetmodel <role> <model>`\n"
            "نقش‌ها: " + ", ".join(ROLES) +
            "\nپاک‌کردن: `/fleetmodel cipher -` | همه: `/fleetmodel off`",
            parse_mode="Markdown",
        )
        return

    if parts[1].lower() == "off":
        for r in ("atlas", "cipher", "vega", "quant", "forge", "rook", "librarian", "muse"):
            await set_setting(f"fleet_model_{r}", None, message.from_user.id)
        from hermes_engine import invalidate_dyn_cache
        invalidate_dyn_cache()
        await message.answer("✅ همه نقش‌ها به مدل پیش‌فرض برگشتند.")
        return

    role = parts[1].lower()
    model = parts[2].strip() if len(parts) > 2 else "-"
    valid_roles = ("atlas", "cipher", "vega", "quant", "forge", "rook", "librarian", "muse")
    if role not in valid_roles:
        await message.answer(f"❌ نقش نامعتبر: {role}")
        return
    val = None if model == "-" else model
    await set_setting(f"fleet_model_{role}", val, message.from_user.id)
    from hermes_engine import invalidate_dyn_cache
    invalidate_dyn_cache()
    await message.answer(
        f"✅ {role} → `{val or 'مدل پیش‌فرض'}`",
        parse_mode="Markdown",
    )


# ================= Product moderation =================

@router.callback_query(F.data == "adm_prods")
async def adm_prods_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    from database import list_pending_products
    rows = await list_pending_products(10)
    if not rows:
        text = "🛡 **محصولات در انتظار تأیید:** هیچ"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_prods")],
            [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
        ])
    else:
        lines = [f"#{d['id']} | {d['price_credits']}💰 | "
                 f"{(d['title'] or '')[:28]} | @{d.get('creator_username') or '-'}"
                 for d in rows]
        text = ("🛡 **تأیید محصولات** (از نوتیف هر آیتم یا همینجا):\n"
                + "\n".join(lines))
        kb_rows = [[InlineKeyboardButton(
                        text=f"✅ #{d['id']}",
                        callback_data=f"adm_appr_{d['id']}"),
                    InlineKeyboardButton(
                        text=f"❌ #{d['id']}",
                        callback_data=f"adm_rej_{d['id']}")]
                   for d in rows]
        kb_rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_prods")])
        kb_rows.append([InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    from utils import edit_safe
    await edit_safe(callback.message, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_appr_"))
async def adm_prod_approve(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    pid = int(callback.data.rsplit("_", 1)[1])
    from database import set_product_status
    row = await set_product_status(pid, "approved", callback.from_user.id)
    if not row:
        await callback.answer("قبلاً بررسی شده!", show_alert=True)
        return
    try:
        await callback.bot.send_message(
            row["creator_id"],
            f"✅ محصول «{row['title']}» تأیید و در مارکت منتشر شد!",
        )
    except Exception:
        pass
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer(f"محصول #{pid} منتشر شد ✅", show_alert=True)


@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_prod_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    pid = int(callback.data.rsplit("_", 1)[1])
    from database import set_product_status
    row = await set_product_status(pid, "rejected", callback.from_user.id)
    if not row:
        await callback.answer("قبلاً بررسی شده!", show_alert=True)
        return
    try:
        await callback.bot.send_message(
            row["creator_id"],
            f"❌ محصول «{row['title']}» تأیید نشد. پس از اصلاح، دوباره ارسال کن.",
        )
    except Exception:
        pass
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer(f"محصول #{pid} رد شد", show_alert=True)


# ================= Runtime variables panel =================

@router.callback_query(F.data == "adm_vars")
async def adm_vars_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    from platform_settings import SETTINGS_META
    from hermes_engine import get_dynamic_setting
    defaults = __import__("platform_settings").defaults_from_env()

    lines = ["⚙️ **متغیرهای زنده پلتفرم**\n"]
    for key, (label, typ, lo, hi) in SETTINGS_META.items():
        raw = await get_dynamic_setting(key, defaults.get(key, ""))
        lines.append(f"• `{key}` = {raw} — {label}")
    lines.append("\nتغییر: `/set <key> <value>`")
    lines.append("نمایش همین لیست: `/vars`")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, "\n".join(lines), kb)
    await callback.answer()


@router.message(F.text.startswith("/set "))
async def set_var_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("`/set <key> <value>`", parse_mode="Markdown")
        return
    key, raw = parts[1].strip(), parts[2].strip()
    from platform_settings import SETTINGS_META, validate
    if key not in SETTINGS_META:
        await message.answer(f"❌ کلید ناشناخته. لیست: /vars")
        return
    val, err = validate(key, raw)
    if err:
        await message.answer(err)
        return
    await set_setting(key, str(val), message.from_user.id)
    from hermes_engine import invalidate_dyn_cache
    invalidate_dyn_cache()
    label = SETTINGS_META[key][0]
    await message.answer(
        f"✅ **{label}**\n`{key}` = **{val}**\n\nفوری اعمال شد (بدون ری‌استارت).",
        parse_mode="Markdown",
    )


@router.message(F.text == "/vars")
async def vars_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    from platform_settings import SETTINGS_META, defaults_from_env
    from hermes_engine import get_dynamic_setting
    d = defaults_from_env()
    lines = []
    for key in SETTINGS_META:
        raw = await get_dynamic_setting(key, d.get(key, ""))
        lines.append(f"`{key}` = {raw}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ================= Maintenance lock =================

async def is_locked() -> bool:
    return (await db_get_setting("maintenance", "0")) == "1"


@router.callback_query(F.data == "adm_lock")
async def adm_lock_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    on = await is_locked()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔓 باز کردن پلتفرم" if on else "🔒 قفل کردن پلتفرم",
            callback_data="lock_toggle")],
        [InlineKeyboardButton(text="🔙 Panel", callback_data="admin_panel")],
    ])
    state_fa = "🔒 قفل" if on else "🟢 باز"
    await callback.message.edit_text(
        f"🔒 **قفل نگهداری**\n\nوضعیت: {state_fa}\n\n"
        f"در حالت قفل، فقط ادمین‌ها می‌توانند از بات استفاده کنند؛ "
        "بقیه پیام «در حال بروزرسانی» می‌بینند.",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "lock_toggle")
async def lock_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    cur = await is_locked()
    await set_setting("maintenance", "0" if cur else "1", callback.from_user.id)
    await callback.answer("قفل شد 🔒" if not cur else "باز شد 🔓", show_alert=True)
    await adm_lock_panel(callback)


@router.message(F.text.startswith("/lock"))
async def lock_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    arg = (message.text or "").split()
    on = len(arg) > 1 and arg[1] == "on"
    await set_setting("maintenance", "1" if on else "0", message.from_user.id)
    await message.answer("🔒 پلتفرم قفل شد." if on else "🔓 پلتفرم باز شد.")
