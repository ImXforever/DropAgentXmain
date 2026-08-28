import asyncio
import os

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
        # ── v2.0 — ابزارهای ظرفیت و سلامت (۱۰ فیچر جدید) ──
        [InlineKeyboardButton(text="⚖️ بررسی تسک‌ها", callback_data="adm_treview"),
         InlineKeyboardButton(text="🗄️ حجم دیتابیس", callback_data="adm_dbmon")],
        [InlineKeyboardButton(text="📈 رشد کاربران", callback_data="adm_growth"),
         InlineKeyboardButton(text="🏆 فروشندگان برتر", callback_data="adm_topsellers")],
        [InlineKeyboardButton(text="📦 سلامت محصولات", callback_data="adm_prodhealth"),
         InlineKeyboardButton(text="💸 درآمد ۳۰ روز", callback_data="adm_revenue")],
        [InlineKeyboardButton(text="🧹 پاک‌سازی چت", callback_data="adm_chatsweep"),
         InlineKeyboardButton(text="🗜️ VACUUM", callback_data="adm_vacuum")],
        [InlineKeyboardButton(text="🗄️ آرشیو تراکنش", callback_data="adm_txarch"),
         InlineKeyboardButton(text="🩺 سلامت سیستم", callback_data="adm_syshealth")],
        # ── v3.5.0 — ابزارهای کمپین و نگهداشت ──
        [InlineKeyboardButton(text="🎟 کد هدیه", callback_data="adm_promo_hint"),
         InlineKeyboardButton(text="🎉 قرعه‌کشی", callback_data="adm_giveaway_hint"),
         InlineKeyboardButton(text="💤 راکدها", callback_data="adm_idle_hint")],
        # ── v4.0.0 — خدمات مشتری ──
        [InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm_tickets_hint"),
         InlineKeyboardButton(text="🚩 گزارش‌ها", callback_data="adm_reports_hint")],
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
    await _users_screen(callback, mode="new", page=0)
    await callback.answer()


USERS_PAGE_SIZE = 10


async def _users_screen(callback, mode: str, page: int):
    """v3.4.0: مدیریت کاربران — صفحه‌بندی + آمار زنده + بک‌اپ CSV"""
    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN is_banned=1 THEN 1 ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN created_at > ? THEN 1 ELSE 0 END),0) FROM users",
            (time.time() - 7 * 86400,))
        total, banned, new7 = await cur.fetchone()
        order = "credits DESC" if mode == "rich" else "user_id DESC"
        cur = await db.execute(
            f"SELECT user_id, username, first_name, credits, is_banned FROM users ORDER BY {order} LIMIT ? OFFSET ?",
            (USERS_PAGE_SIZE, page * USERS_PAGE_SIZE))
        rows = await cur.fetchall()
    pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))

    text = (f"👥 **مدیریت کاربران**\n\n"
            f"📊 کل: **{total:,}** | 🆕 ۷روز: **{new7:,}** | 🚫 بن: **{banned:,}**\n"
            f"📄 صفحهٔ {page + 1} از {pages} ({'🏆 ثروتمندترین' if mode == 'rich' else '🆕 جدیدترین'})\n\n")
    if not rows:
        text += "کاربری نیست."

    kb = []
    for uid, username, first_name, credits, banned_f in rows:
        st = "🚫" if banned_f else ("🟢" if credits > 0 else "⚪")
        nm = esc_md((first_name or "")[:14])
        un = f"@{esc_md(username)}" if username else ""
        kb.append([InlineKeyboardButton(
            text=f"{st} {nm} {un} — {credits:,}💰",
            callback_data=f"adm_uinfo_{uid}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm_users_{mode}_{page-1}"))
    nav.append(InlineKeyboardButton(text="🔄", callback_data=f"adm_users_{mode}_{page}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm_users_{mode}_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([
        InlineKeyboardButton(text="🆕 جدیدترین‌ها" if mode != "new" else "🏆 ثروتمندترین‌ها",
                             callback_data=f"adm_users_{'rich' if mode == 'new' else 'new'}_0"),
        InlineKeyboardButton(text="📤 بک‌اپ کامل", callback_data="adm_ubackup"),
    ])
    kb.append([InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")])
    await edit_safe(callback.message, text, InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")


@router.callback_query(F.data.startswith("adm_users_"))
async def adm_users_nav(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    try:
        _, _, mode, page = callback.data.split("_", 3)
        if mode not in ("new", "rich"):
            raise ValueError
        await _users_screen(callback, mode, int(page))
    except Exception:
        await callback.answer("خطای ناوبری!", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_uinfo_"))
async def adm_uinfo(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    uid = int(callback.data.rsplit("_", 1)[1])
    async with get_db() as db:
        cur = await db.execute(
            "SELECT user_id, first_name, username, credits, total_earned, referred_by, "
            "is_banned, created_at, role FROM users WHERE user_id = ?", (uid,))
        u = await cur.fetchone()
        if not u:
            await callback.answer("کاربر پیدا نشد!", show_alert=True)
            return
        cur = await db.execute("SELECT COUNT(*) FROM purchases WHERE buyer_id = ?", (uid,))
        n_purch = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM task_completions WHERE user_id = ? AND status IN ('pending','verified','completed')", (uid,))
        n_tasks = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM products WHERE creator_id = ?", (uid,))
        n_prods = (await cur.fetchone())[0]

    (_, fname, uname, credits, earned, ref, banned, created, role) = u
    try:
        joined = time.strftime("%Y-%m-%d", time.localtime(created)) if created else "؟"
    except Exception:
        joined = "؟"
    un_s = f"@{uname}" if uname else "—"
    ref_s = str(ref) if ref else "—"
    text = (f"👤 **کارت کاربر**\n\n"
            f"🪪 `{uid}` | {esc_md(fname or '—')} ({esc_md(un_s)})\n"
            f"🎭 نقش: **{esc_md(role or 'associate')}**\n"
            f"💰 کردیت: **{credits:,}** | 📈 درآمد کل: **{earned:,}**\n"
            f"👥 معرف: `{ref_s}` | 📅 عضویت: {joined}\n"
            f"🛒 خریدها: **{n_purch}** | ✅ تسک‌ها: **{n_tasks}** | 📦 محصولات: **{n_prods}**\n"
            f"{'🚫 **مسدود (بن)**' if banned else '✅ فعال'}")

    kb = [
        [InlineKeyboardButton(text="🚫 مسدودسازی" if not banned else "✅ رفع بن",
                              callback_data=f"adm_uban_{uid}"),
         InlineKeyboardButton(text="💰 شارژ کردیت", callback_data=f"adm_ucr_{uid}")],
        [InlineKeyboardButton(text="📥 پیام به کاربر", callback_data=f"adm_udm_{uid}")],
        [InlineKeyboardButton(text="🔙 لیست کاربران", callback_data="admin_users")],
    ]
    await edit_safe(callback.message, text, InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_uban_"))
async def adm_uban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    uid = int(callback.data.rsplit("_", 1)[1])
    if uid in cfg.ADMIN_IDS:
        await callback.answer("⛔ بن ادمین ممکن نیست!", show_alert=True)
        return
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 1 - is_banned WHERE user_id = ?", (uid,))
        await db.commit()
        cur = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,))
        now_banned = (await cur.fetchone())[0]
    try:
        from observability import db_log
        await db_log("admin", f"ban toggle: {uid} → {'banned' if now_banned else 'unbanned'}",
                     user_id=uid, level="WARNING")
    except Exception:
        pass
    await callback.answer(f"{'🚫 مسدود شد' if now_banned else '✅ آزاد شد'}")
    # رندر مجدد کارت
    callback.data = f"adm_uinfo_{uid}"
    await adm_uinfo(callback)


@router.callback_query(F.data.startswith("adm_ucr_"))
async def adm_ucr(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    uid = int(callback.data.rsplit("_", 1)[1])
    await callback.answer(f"بفرست: /addcredits {uid} مقدار", show_alert=True)


@router.callback_query(F.data.startswith("adm_udm_"))
async def adm_udm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    uid = int(callback.data.rsplit("_", 1)[1])
    await callback.answer(f"بفرست: /msg {uid} متن پیام", show_alert=True)


@router.callback_query(F.data == "adm_ubackup")
async def adm_ubackup(callback: CallbackQuery):
    """v3.4.0: بک‌اپ کامل مخاطبان — CSV همهٔ کاربران، ارسال به ادمین"""
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    import csv, tempfile
    from aiogram.types import FSInputFile
    async with get_db() as db:
        cur = await db.execute(
            "SELECT user_id, first_name, username, credits, total_earned, referred_by, "
            "is_banned, role, created_at FROM users ORDER BY user_id")
        rows = await cur.fetchall()
    path = tempfile.mktemp(prefix=f"dax_users_", suffix=".csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "first_name", "username", "credits", "total_earned",
                    "referred_by", "banned", "role", "joined_at"])
        for r in rows:
            w.writerow(list(r))
    total_credits = sum(r[3] or 0 for r in rows)
    sup = config.SUPPORT_CONTACT or "@ImXforevr"
    try:
        await callback.message.answer_document(
            FSInputFile(path),
            caption=(f"📦 **بک‌اپ کامل مخاطبان**\n\n"
                     f"👥 کاربران: **{len(rows):,}**\n"
                     f"💰 مجموع کردیت‌ها: **{total_credits:,}**\n"
                     f"🕘 {time.strftime('%Y-%m-%d %H:%M')}\n"
                     f"🆘 Owner: {sup}"),
            parse_mode="Markdown")
        try:
            from observability import db_log
            await db_log("admin", f"users backup exported: {len(rows)} rows", level="INFO")
        except Exception:
            pass
        await callback.answer("📤 ارسال شد!")
    except Exception as e:
        await callback.answer(f"خطا در ارسال: {type(e).__name__}", show_alert=True)
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


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


# ══════════════════════════════════════════════════════════════════
# v2.0 — ۱۰ فیچر جدید ادمین + صف بررسی گزینه‌به‌گزینه‌ی تسک‌ها
# ══════════════════════════════════════════════════════════════════


# ── 1) ⚖️ صف بررسی تسک‌ها (گزینه‌به‌گزینه) ──

async def _render_review_card(bot, message, cid: int = None):
    """کارت بعدی صف بررسی را رندر می‌کند (یا پیام خالی‌بودن صف)."""
    from database import (get_task_review_item, get_task_review_queue,
                          count_pending_task_reviews)
    item = await get_task_review_item(cid) if cid else None
    if not item:
        queue = await get_task_review_queue(1)
        item = queue[0] if queue else None

    total = await count_pending_task_reviews()
    if not item:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 پنل ادمین", callback_data="admin_panel")],
        ])
        await edit_safe(message, "🎉 **صف بررسی خالی است!**\n\nهمه تسک‌های ارسالی بررسی شده‌اند.", kb)
        return

    import time as _time
    ago = max(1, int((_time.time() - (item.get("completed_at") or _time.time())) / 60))
    ago_s = f"{ago} دقیقه پیش" if ago < 1440 else f"{ago // 1440} روز پیش"
    reward = int(item.get("credits_reward") or 0)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأیید + پاداش", callback_data=f"adm_tk_ok_{item['cid']}"),
         InlineKeyboardButton(text="❌ رد", callback_data=f"adm_tk_no_{item['cid']}")],
        [InlineKeyboardButton(text="⏭ بعدی", callback_data=f"adm_tk_skip_{item['cid']}"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        message,
        f"⚖️ **بررسی تسک — گزینه به گزینه**\n"
        f"🧾 در صف: **{total}** مورد\n\n"
        f"👤 کاربر: **{item['user_name']}** (`{item['user_id']}`)\n"
        f"📌 تسک: **{item['task_title'] or item['task_id']}**\n"
        f"💰 پاداش: **{reward:,} کردیت** (≈{reward / 1000:.2f}$)\n"
        f"🕒 ارسال: {ago_s}\n\n"
        f"👇 حکم صادر کن — بعد از این کارت، مورد بعدی خودکار می‌آید:",
        kb,
    )


@router.callback_query(F.data == "adm_treview")
async def adm_treview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.answer()
    await _render_review_card(callback.bot, callback.message)


@router.callback_query(F.data.startswith("adm_tk_ok_"))
async def adm_tk_approve(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import review_task_approve
    cid = int(callback.data.rsplit("_", 1)[1])
    item = await review_task_approve(cid)
    if not item:
        await callback.answer("این مورد قبلاً بررسی شده!", show_alert=True)
        await _render_review_card(callback.bot, callback.message)
        return
    await callback.answer(f"✅ تأیید شد — {item['credits_reward']:,} کردیت پرداخت شد")
    try:
        await callback.bot.send_message(
            item["user_id"],
            f"✅ **تسکت تأیید شد!**\n📌 {item['task_title']}\n"
            f"💰 **+{int(item['credits_reward']):,} کردیت** به حسابت اضافه شد.",
            parse_mode="Markdown")
    except Exception:
        pass
    # ریفرال: تسک‌های تأییدشده واجد شرایط دعوت می‌کنند (≥۳ تسک)
    from handlers.referral import maybe_qualify_referral
    await maybe_qualify_referral(callback.bot, item["user_id"])
    await _render_review_card(callback.bot, callback.message)


@router.callback_query(F.data.startswith("adm_tk_no_"))
async def adm_tk_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import review_task_reject
    cid = int(callback.data.rsplit("_", 1)[1])
    item = await review_task_reject(cid)
    if not item:
        await callback.answer("این مورد قبلاً بررسی شده!", show_alert=True)
        await _render_review_card(callback.bot, callback.message)
        return
    await callback.answer("❌ رد شد — ظرفیت تسک آزاد شد")
    try:
        await callback.bot.send_message(
            item["user_id"],
            f"❌ **تسکت تأیید نشد**\n📌 {item['task_title']}\n"
            f"💡 اگر واقعاً انجامش دادی، از پشتیبانی پیگیری کن یا دوباره و درست انجامش بده.",
            parse_mode="Markdown")
    except Exception:
        pass
    await _render_review_card(callback.bot, callback.message)


@router.callback_query(F.data.startswith("adm_tk_skip_"))
async def adm_tk_skip(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.answer("⏭ رد شد از این مورد")
    await _render_review_card(callback.bot, callback.message)


# ── 2) 🗄️ مانیتور حجم دیتابیس ──
@router.callback_query(F.data == "adm_dbmon")
async def adm_dbmon(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import db_size_bytes, db_counts, MEMORY_MAX_ROWS
    size = await db_size_bytes()
    mb = size / (1024 * 1024)
    limit_mb = 500.0
    pct = mb / limit_mb * 100
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    counts = await db_counts()
    warn = "🟡 نزدیک آستانه هشدار!" if mb >= config.DB_WARN_MB * 0.9 else ("🔴 بالای آستانه!" if mb >= config.DB_WARN_MB else "🟢 سالم")
    est = int((limit_mb * 1024 * 1024) / max(1, size / max(1, counts.get("users", 1))))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗜️ VACUUM الان", callback_data="adm_vacuum"),
         InlineKeyboardButton(text="🧹 پاک‌سازی چت", callback_data="adm_chatsweep")],
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_dbmon"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"🗄️ **مانیتور دیتابیس** {warn}\n\n"
        f"📦 حجم: **{mb:.1f} MB** از 500MB [{bar}] {pct:.0f}٪\n"
        f"🎯 ظرفیت باقیمانده ≈ **{est:,} کاربر دیگر** (بر اساس مصرف فعلی/کاربر)\n\n"
        f"👥 کاربران: {counts.get('users', -1):,}\n"
        f"💬 پیام‌های چت: {counts.get('chat_messages', -1):,} (سقف {MEMORY_MAX_ROWS}/کاربر)\n"
        f"🧾 تراکنش‌ها: {counts.get('transactions', -1):,}\n"
        f"🛒 خریدها: {counts.get('purchases', -1):,} · 📦 محصولات فعال: {counts.get('products', -1):,}\n"
        f"⚖️ در صف بررسی تسک: **{counts.get('pending_task_reviews', 0)}**\n"
        f"🟡 واریز/برداشت معلق: {counts.get('pending_deposits', 0)}/{counts.get('pending_withdrawals', 0)}\n\n"
        f"⚠️ آستانه هشدار: {config.DB_WARN_MB}MB (80٪)",
        kb,
    )
    await callback.answer()


# ── 3) 🧹 پاک‌سازی چت کاربران راکد ──
@router.callback_query(F.data == "adm_chatsweep")
async def adm_chatsweep(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import db_size_bytes
    mb = (await db_size_bytes()) / 1048576
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🧹 اجرا (حذف چت راکدهای {config.SWEEP_DORMANT_DAYS} روز)", callback_data="adm_chatsweep_go")],
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"🧹 **پاک‌سازی حافظه چت کاربران راکد**\n\n"
        f"حذف می‌شود: پیام‌های چتِ کاربرانی که **{config.SWEEP_DORMANT_DAYS} روز** عضو بودند و هیچ درآمدی نداشتند.\n"
        f"حفظ می‌شود: حساب، اعتبار، محصولات و تراکنش‌ها.\n\n"
        f"📦 حجم فعلی DB: **{mb:.1f} MB**\n\n"
        f"ادامه می‌دهی؟",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_chatsweep_go")
async def adm_chatsweep_go(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import chat_sweep_dormant, db_size_bytes
    n = await chat_sweep_dormant()
    mb = (await db_size_bytes()) / 1048576
    await callback.answer(f"🧹 {n:,} پیام پاک شد", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, f"✅ **پاک‌سازی انجام شد**\n\n🗑 {n:,} پیام چت حذف شد.\n📦 حجم فعلی: {mb:.1f} MB", kb)


# ── 4) 🗜️ VACUUM ──
@router.callback_query(F.data == "adm_vacuum")
async def adm_vacuum(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import db_size_bytes
    mb = (await db_size_bytes()) / 1048576
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗜️ بله، فشرده‌سازی کن", callback_data="adm_vacuum_go")],
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"🗜️ **VACUUM — فشرده‌سازی دیتابیس**\n\n"
        f"پاک‌سازی‌های قبلی صفحات خالی زیادی گذاشته‌اند؛ VACUUM فایل را جمع می‌کند.\n"
        f"📦 حجم فعلی: **{mb:.1f} MB**\n"
        f"⏱ چند ثانیه قفل سبک می‌شود — خارج از پیک بهتر است.\n\n"
        f"ادامه می‌دهی؟",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_vacuum_go")
async def adm_vacuum_go(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import vacuum_now
    before, after = await vacuum_now()
    saved = (before - after) / 1048576
    await callback.answer(f"🗜️ {saved:.1f} MB آزاد شد!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"✅ **VACUUM کامل شد**\n\n"
        f"📦 قبل: {before / 1048576:.1f} MB → بعد: **{after / 1048576:.1f} MB**\n"
        f"🎉 آزادشده: **{saved:.1f} MB**",
        kb,
    )


# ── 5) 📈 رشد کاربران ──
@router.callback_query(F.data == "adm_growth")
async def adm_growth(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import growth_stats
    g = await growth_stats()
    rate7 = g["new_7d"] / 7
    proj30 = int(rate7 * 30)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_growth"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"📈 **گزارش رشد کاربران**\n\n"
        f"👥 کل: **{g['users_total']:,}**\n"
        f"🆕 ۲۴ ساعت: **+{g['new_24h']}**\n"
        f"🆕 ۷ روز: **+{g['new_7d']}**\n"
        f"🆕 ۳۰ روز: **+{g['new_30d']}**\n\n"
        f"🛒 فروش ۳۰ روز: {g['sales_30d_n']} عدد · {g['sales_30d_sum']:,} کردیت\n"
        f"🔮 پیش‌بینی ۳۰ روز بعد (با ریتم هفته): **+{proj30:,}** → {g['users_total'] + proj30:,} کاربر\n\n"
        f"💡 با میانگین مصرف فعلی، سقف 500MB ≈ 8000+ کاربر — ظرفیت سالم است.",
        kb,
    )
    await callback.answer()


# ── 6) 🏆 فروشندگان برتر ──
@router.callback_query(F.data == "adm_topsellers")
async def adm_topsellers(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import top_sellers
    rows = await top_sellers(10)
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = [f"{medals[i]} **{r['name']}** — {r['sales']} فروش · {r['revenue']:,} کردیت"
             for i, r in enumerate(rows)] or ["هنوز فروشی ثبت نشده."]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_topsellers"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, "🏆 **لیدربورد فروشندگان**\n\n" + "\n".join(lines), kb)
    await callback.answer()


# ── 7) 📦 سلامت محصولات ──
@router.callback_query(F.data == "adm_prodhealth")
async def adm_prodhealth(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import product_health
    h = await product_health()
    flags = []
    if h["no_file"]:
        flags.append(f"⚠️ بدون فایل: **{h['no_file']}** (فقط توضیحات نمایش داده می‌شود)")
    if h["no_desc"]:
        flags.append(f"⚠️ بدون توضیحات: **{h['no_desc']}**")
    if h["no_cover"]:
        flags.append(f"🖼 بدون کاور: **{h['no_cover']}**")
    if h["disk_only"]:
        flags.append(f"🛰 قابل انتقال به ذخیره ابری (file_id): **{h['disk_only']}**")
    body = "\n".join(flags) if flags else "✅ همه محصولات سالم‌اند!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_prodhealth"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"📦 **سلامت محصولات**\n\n"
        f"✅ فعال: **{h['active']}**\n{body}\n\n"
        f"💡 نکته ظرفیت: هر فایل روی دیسک ≈ میانگین 1.5MB از Volume مصرف می‌کند؛ "
        f"با تنظیم `FILE_STORAGE_CHANNEL_ID` فایل‌های جدید ابری می‌شوند.",
        kb,
    )
    await callback.answer()


# ── 8) 💸 درآمد ۳۰ روز ──
@router.callback_query(F.data == "adm_revenue")
async def adm_revenue(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import revenue_30d
    r = await revenue_30d(30)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_revenue"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"💸 **گزارش درآمد ۳۰ روز اخیر**\n\n"
        f"🛒 فروش: **{r['sales']}** عدد\n"
        f"💵 ناخالص: **{r['gross_credits']:,} کردیت** (≈{r['gross_credits'] / 1000:.2f}$)\n"
        f"🏦 سهم پلتفرم (~{int(config.COMMISSION_RATE * 100)}٪): **{r['commission_credits']:,} کردیت** "
        f"(≈{r['commission_credits'] / 1000:.2f}$)\n\n"
        f"🔮 سالانه‌شده: ≈{r['commission_credits'] * 12 / 1000:.1f}$ کمیسیون",
        kb,
    )
    await callback.answer()


# ── 9) 🗄️ آرشیو تراکنش‌های قدیمی ──
@router.callback_query(F.data == "adm_txarch")
async def adm_txarch(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    days = int(getattr(config, "TX_ARCHIVE_DAYS", 0) or 0)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗄️ آرشیو کن (365+ روز)", callback_data="adm_txarch_go")],
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    state = f"فعال — تراکنش‌های +{days} روز" if days > 0 else "خاموش (TX_ARCHIVE_DAYS=0) — این اجرا دستی 365+ روز را آرشیو می‌کند"
    await edit_safe(
        callback.message,
        f"🗄️ **آرشیو تراکنش‌های قدیمی**\n\n"
        f"وضعیت خودکار: {state}\n\n"
        f"تراکنش‌های قدیمی به JSON در `data/archives/` خروجی می‌گیرند و از DB حذف می‌شوند\n"
        f"(مجموع اعتبار کسی تغییر نمی‌کند — فقط لاگ سبک می‌شود).",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_txarch_go")
async def adm_txarch_go(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    from database import archive_old_transactions, db_size_bytes
    n = await archive_old_transactions(days=365)
    mb = (await db_size_bytes()) / 1048576
    await callback.answer(f"🗄️ {n:,} تراکنش آرشیو شد", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(callback.message, f"✅ **آرشیو کامل شد**\n\n🗑 {n:,} تراکنش قدیمی به data/archives/ منتقل و از DB حذف شد.\n📦 حجم فعلی: {mb:.1f} MB", kb)


# ── 10) 🩺 سلامت سیستم ──
@router.callback_query(F.data == "adm_syshealth")
async def adm_syshealth(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    import os as _os
    from database import db_counts, db_size_bytes, db_size_bytes as _sz
    size_mb = (await db_size_bytes()) / 1048576
    counts = await db_counts()
    wal = _os.path.exists(config.DB_PATH + "-wal") and _os.path.getsize(config.DB_PATH + "-wal") or 0
    up = _os.popen("cat /proc/uptime 2>/dev/null").read().split()[0] if _os.path.exists("/proc/uptime") else "?"
    try:
        up_s = f"{int(float(up) // 3600)} ساعت {int(float(up) % 3600 // 60)} دقیقه"
    except Exception:
        up_s = "نامشخص"
    alerts = []
    if size_mb >= config.DB_WARN_MB:
        alerts.append("🔴 حجم DB بالای آستانه — پاک‌سازی/VACUUM کن")
    if counts.get("pending_task_reviews", 0) > 20:
        alerts.append("⚖️ صف بررسی تسک‌ها شلوغ است")
    if counts.get("pending_deposits", 0) > 10:
        alerts.append("🟡 واریزهای معلق زیادند")
    body = ("\n".join("• " + x for x in alerts)) if alerts else "✅ همه‌چیز سالم است"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_syshealth"),
         InlineKeyboardButton(text="🔙 پنل", callback_data="admin_panel")],
    ])
    await edit_safe(
        callback.message,
        f"🩺 **سلامت سیستم**\n\n"
        f"⏱ آپتایم کانتینر: {up_s}\n"
        f"📦 حجم DB: **{size_mb:.1f} MB** (آستانه {config.DB_WARN_MB})\n"
        f"📝 WAL: {wal / 1048576:.2f} MB\n"
        f"📁 آپلودها روی دیسک: {_dir_size_mb(config.UPLOAD_DIR):.1f} MB\n"
        f"⚖️ صف تسک: {counts.get('pending_task_reviews', 0)} · 🟡 واریز: {counts.get('pending_deposits', 0)} · 🔵 برداشت: {counts.get('pending_withdrawals', 0)}\n\n"
        f"{body}",
        kb,
    )
    await callback.answer()


def _dir_size_mb(path: str) -> float:
    total = 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total / 1048576


# ── v3.4.0: ابزارهای مستقیم ادمین روی کاربر ──
@router.message(F.text.startswith("/ban "))
async def ban_cmd(message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("فرمت: `/ban user_id`", parse_mode="Markdown")
        return
    if uid in config.ADMIN_IDS:
        await message.answer("⛔ بن ادمین ممکن نیست!")
        return
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (uid,))
        await db.commit()
    await message.answer(f"🚫 کاربر `{uid}` مسدود شد.", parse_mode="Markdown")


@router.message(F.text.startswith("/unban "))
async def unban_cmd(message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("فرمت: `/unban user_id`", parse_mode="Markdown")
        return
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (uid,))
        await db.commit()
    await message.answer(f"✅ کاربر `{uid}` آزاد شد.", parse_mode="Markdown")


@router.message(F.text.startswith("/msg "))
async def msg_cmd(message):
    """DM مستقیم از ادمین به کاربر — /msg user_id متن"""
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit():
        await message.answer("فرمت: `/msg user_id متن پیام`", parse_mode="Markdown")
        return
    uid, text = int(parts[1]), parts[2].strip()[:3500]
    try:
        await message.bot.send_message(uid, f"📩 **پیام از پشتیبانی:**\n\n{text}",
                                       parse_mode="Markdown")
        await message.answer(f"✅ به `{uid}` ارسال شد.", parse_mode="Markdown")
        try:
            from observability import db_log
            await db_log("admin", f"dm sent to {uid}", user_id=uid)
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ ارسال نشد: {type(e).__name__} (شاید بات را استارت نکرده)")


# ── v3.5.0: ابزارهای کمپین و نگهداشت ──
@router.callback_query(F.data.in_({"adm_promo_hint", "adm_giveaway_hint", "adm_idle_hint", "adm_tickets_hint", "adm_reports_hint"}))
async def campaign_hints(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید!", show_alert=True)
        return
    tips = {
        "adm_promo_hint": ("🎟 کد هدیه کمپینی\n\n"
            "ساخت: `/promonew CODE تعداد_کردیت تعداد_استفاده [روز_اعتبار]`\n"
            "مثال: `/promonew TELEGRAM50 50 200 14`\n\n"
            "لیست: `/promolist`\n"
            "کاربرها از «💰 کیف پول → 🎟 کد هدیه دارم» استفاده می‌کنند."),
        "adm_giveaway_hint": ("🎉 قرعه‌کشی بین فعال‌ها\n\n"
            "`/giveaway جایزه تعداد_برنده روزها`\n"
            "مثال: `/giveaway 250 5 7` ← ۵ برندهٔ تصادفی از فعال‌های ۷روز اخیر، هرکدام ۲۵۰ کردیت\n"
            "(حداکثر ۲۵ برنده)\n\n"
            "برنده‌ها خودکار کردیت می‌گیرند + DM تبریک."),
        "adm_idle_hint": ("💤 پیام به کاربران راکد\n\n"
            "`/idlemsg روزها متن`\n"
            "مثال: `/idlemsg 7 غیبت کردی! 🎁 بونوس روزانه منتظرته`\n\n"
            "به کاربرانی که بیش از N روز فعالیت نداشتند ارسال می‌شود (حداکثر ۱۰۰۰ نفر)."),        "adm_tickets_hint": ("🎫 تیکت‌های پشتیبانی\n\n"
            "لیست تیکت‌های باز: `/tickets`\n"
            "پاسخ: `/trep ID متن` ← مستقیم به کاربر DM می‌رود\n"
            "کاربرها از «🎫 پشتیبانی» در منو ثبت می‌کنند."),
        "adm_reports_hint": ("🚩 گزارش‌های تخلف\n\n"
            "لیست: `/reports`\n"
            "بستن پس از بررسی: `/repdone ID`"),
    }
    await callback.answer(tips[callback.data], show_alert=True)


@router.message(F.text.startswith("/promonew"))
async def promonew_cmd(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) not in (4, 5):
        await message.answer("فرمت: `/promonew CODE تعداد_کردیت تعداد_استفاده [روز_اعتبار]`",
                             parse_mode="Markdown")
        return
    code = parts[1].upper()
    try:
        credits, uses = int(parts[2]), int(parts[3])
        days = int(parts[4]) if len(parts) == 5 else 0
    except ValueError:
        await message.answer("عددها نامعتبرند!")
        return
    if credits < 1 or uses < 1 or uses > 100000 or days < 0 or days > 3650:
        await message.answer("مقادیر خارج از محدوده!")
        return
    from database import create_promo
    if await create_promo(code, credits, uses, days, message.from_user.id):
        exp = f"اعتبار {days} روز" if days else "بدون انقضا"
        await message.answer(
            f"✅ کد **{code}** ساخته شد!\n"
            f"💰 {credits:,} کردیت · 👥 {uses:,} استفاده · ⏳ {exp}\n\n"
            f"📢 توی تبلیغات بگذار — کاربرها از کیف پول، «🎟 کد هدیه دارم» را می‌زنند.",
            parse_mode="Markdown")
        try:
            from observability import db_log
            await db_log("admin", f"promo created: {code} x{uses} = {credits}", level="INFO")
        except Exception:
            pass
    else:
        await message.answer("❌ کد تکراری یا نامعتبر است (۳ تا ۲۴ کاراکتر حرف/عدد).")


@router.message(F.text.startswith("/promolist"))
async def promolist_cmd(message):
    if not is_admin(message.from_user.id):
        return
    from database import list_promos
    rows = await list_promos(10)
    if not rows:
        await message.answer("هنوز کدی نساخته‌ای — `/promonew CODE کردیت تعداد [روز]`")
        return
    import time as _t
    text = "🎟 **کدهای هدیه:**\n\n"
    for code, credits, maxu, used, exp in rows:
        if exp and _t.time() > exp:
            st = "⏰ منقضی"
        elif used >= maxu:
            st = "✅ پر"
        else:
            st = "🟢 فعال"
        text += f"{st} `{code}` — {credits:,}💰 | {used:,}/{maxu:,}\n"
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/giveaway "))
async def giveaway_cmd(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer("فرمت: `/giveaway جایزه تعداد_برنده روزها`", parse_mode="Markdown")
        return
    try:
        prize, winners, days = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        await message.answer("عددها نامعتبرند!")
        return
    if not (1 <= winners <= 25 and prize >= 1 and 1 <= days <= 365):
        await message.answer("محدودها: برنده ≤ ۲۵ · روزها ۱ تا ۳۶۵")
        return
    from database import pick_random_active_users, update_credits as _uc
    picked = await pick_random_active_users(days, winners)
    if not picked:
        await message.answer("در این بازه کاربر فعالی پیدا نشد!")
        return
    lines = [f"🎉 **قرعه‌کشی انجام شد!**\n\n🎁 جایزه: **{prize:,} کردیت** برای هر برنده\n👥 از فعال‌های {days} روز اخیر\n\n**🏆 برنده‌ها:**"]
    for uid, fname in picked:
        await _uc(uid, prize, "giveaway", "برنده قرعه‌کشی")
        lines.append(f"• {esc_md(fname or 'کاربر')} — `{uid}`")
        try:
            await message.bot.send_message(uid, f"🎉 **تبریک! تو برنده قرعه‌کشی شدی!**\n💰 **+{prize:,} کردیت** به حسابت اضافه شد\n🛒 برو فروشگاه را بگرد!")
        except Exception:
            pass
    await message.answer("\n".join(lines), parse_mode="Markdown")
    try:
        from observability import db_log
        await db_log("admin", f"giveaway: {len(picked)} winners x {prize}", level="INFO")
    except Exception:
        pass


@router.message(F.text.startswith("/idlemsg "))
async def idlemsg_cmd(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("فرمت: `/idlemsg روزها متن`", parse_mode="Markdown")
        return
    days, text = int(parts[1]), parts[2].strip()[:2000]
    from database import pick_inactive_users
    rows = await pick_inactive_users(days, 1000)
    rows = [(uid, fn) for uid, fn in rows if uid not in config.ADMIN_IDS]
    if not rows:
        await message.answer(f"در {days} روز اخیر کاربر راکدی پیدا نشد 🎉")
        return
    sent = 0
    status = await message.answer(f"⏳ در حال ارسال به {len(rows)} کاربر راکد...")
    for uid, _fn in rows:
        try:
            await message.bot.send_message(uid, f"💌 {text}\n\n🤖 از DropAgentX")
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ به **{sent}** نفر از {len(rows)} کاربر راکد ارسال شد.",
                           parse_mode="Markdown")
    try:
        from observability import db_log
        await db_log("admin", f"idlemsg: {sent}/{len(rows)} sent ({days}d)", level="INFO")
    except Exception:
        pass
