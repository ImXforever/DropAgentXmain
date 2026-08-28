"""v4.0.0 — تیکت پشتیبانی درون‌باتی + گزارش تخلف + ابزارهای ادمین"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import config as cfg
import database as db
from utils import edit_safe

router = Router()

CATS = {"general": "💬 عمومی", "payment": "💳 پرداخت", "product": "📦 محصول", "bug": "🐛 باگ"}


class TicketFlow(StatesGroup):
    subject = State()
    body = State()
    reply = State()


class ReportFlow(StatesGroup):
    target = State()
    reason = State()


def _is_admin(uid: int) -> bool:
    return uid in cfg.ADMIN_IDS


@router.callback_query(F.data == "support_menu")
async def support_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await edit_safe(callback.message,
        "🎫 **مرکز پشتیبانی**\n\n"
        "هر مشکل یا سوالی داری همین‌جا ثبت کن — تیکتت مستقیم می‌رسد به تیم پشتیبانی "
        f"و جواب را **داخل همین بات** می‌گیری.\n\n"
        f"⏱ معمولاً سریع پاسخ می‌دهیم · 🆘 فوری: {(cfg.SUPPORT_CONTACT or '@ImXforevr')}",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ تیکت جدید", callback_data="ticket_new")],
            [InlineKeyboardButton(text="📂 تیکت‌های من", callback_data="ticket_mine")],
            [InlineKeyboardButton(text="🚩 گزارش تخلف", callback_data="report_new")],
            [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
        ]), parse_mode="Markdown")
    await callback.answer()


# ---------- ساخت تیکت ----------

@router.callback_query(F.data == "ticket_new")
async def ticket_new(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text=v, callback_data=f"ticket_cat_{k}")]
          for k, v in CATS.items()]
    kb.append([InlineKeyboardButton(text="❌ انصراف", callback_data="support_menu")])
    await edit_safe(callback.message, "🎫 **موضوع تیکت چیه؟**",
                    InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_cat_"))
async def ticket_cat(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.rsplit("_", 1)[1]
    if cat not in CATS:
        await callback.answer("نامعتبر!", show_alert=True)
        return
    await state.update_data(tk_cat=cat)
    await state.set_state(TicketFlow.subject)
    await edit_safe(callback.message,
        f"✅ دسته: {CATS[cat]}\n\n✍️ **موضوع را در یک خط بفرست:**\n(مثلاً: فایل خریدم باز نمی‌شود)",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="support_menu")]]))
    await callback.answer()


@router.message(TicketFlow.subject, F.text)
async def ticket_subject(message: Message, state: FSMContext):
    subject = message.text.strip()[:120]
    if len(subject) < 3:
        await message.answer("❌ موضوع خیلی کوتاه است — دوباره بفرست:")
        return
    await state.update_data(tk_subject=subject)
    await state.set_state(TicketFlow.body)
    await message.answer(
        "✅ ثبت شد!\n\n📝 **حالا توضیح کامل را بفرست:**\n"
        "(هرچه دقیق‌تر، سریع‌تر جواب می‌گیری — شماره محصول، مبلغ و… را بگو)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="support_menu")]]))


@router.message(TicketFlow.body, F.text)
async def ticket_body(message: Message, state: FSMContext):
    data = await state.get_data()
    if "tk_subject" not in data:
        await state.clear()
        await message.answer("⌛ منقضی شد — دوباره «✉️ تیکت جدید» را بزن.")
        return
    await state.clear()
    tid = await db.create_ticket(message.from_user.id, data.get("tk_cat", "general"),
                                 data["tk_subject"], message.text.strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 تیکت‌های من", callback_data="ticket_mine")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")]])
    await message.answer(
        f"🎫 **تیکت #{tid} ثبت شد!**\n\n"
        f"📌 {data['tk_subject']}\n\n"
        "👥 تیم پشتیبانی دیدنش می‌کند و جواب را همین‌جا می‌گیری. "
        "از «📂 تیکت‌های من» پیگیری کن.", reply_markup=kb, parse_mode="Markdown")
    for aid in cfg.ADMIN_IDS:
        try:
            await message.bot.send_message(
                aid, f"🎫 **تیکت جدید #{tid}**\n{CATS.get(data.get('tk_cat', 'general'), '')}\n"
                     f"از: `{message.from_user.id}`\n📌 {data['tk_subject']}\n\n"
                     f"پاسخ: `/trep {tid} متن`",
                parse_mode="Markdown")
        except Exception:
            pass


# ---------- پیگیری ----------

@router.callback_query(F.data == "ticket_mine")
async def ticket_mine(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = await db.list_user_tickets(callback.from_user.id)
    if not rows:
        await edit_safe(callback.message, "📂 هنوز تیکتی نداری — سوالی بود «✉️ تیکت جدید» بزن!",
                        InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✉️ تیکت جدید", callback_data="ticket_new")],
                            [InlineKeyboardButton(text="🔙 مرکز پشتیبانی", callback_data="support_menu")]]))
        await callback.answer()
        return
    st_map = {"open": "🟡 در انتظار بررسی", "answered": "✅ پاسخ داده شد", "closed": "🔒 بسته"}
    kb = [[InlineKeyboardButton(text=f"#{tid} {st_map.get(st, st)} — {subj[:24]}",
                                callback_data=f"ticket_view_{tid}")]
          for tid, cat, subj, st in rows]
    kb.append([InlineKeyboardButton(text="🔙 مرکز پشتیبانی", callback_data="support_menu")])
    await edit_safe(callback.message, "📂 **تیکت‌های تو:**",
                    InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_view_"))
async def ticket_view(callback: CallbackQuery):
    try:
        tid = int(callback.data.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("نامعتبر!", show_alert=True)
        return
    t = await db.get_ticket(tid)
    if not t or (t[1] != callback.from_user.id and not _is_admin(callback.from_user.id)):
        await callback.answer("دسترسی نداری!", show_alert=True)
        return
    msgs = await db.ticket_thread(tid)
    st_map = {"open": "🟡 در انتظار بررسی", "answered": "✅ پاسخ داده شد", "closed": "🔒 بسته"}
    text = f"🎫 **تیکت #{tid}** — {CATS.get(t[2], t[2])}\n📌 {t[3]}\nوضعیت: {st_map.get(t[4], t[4])}\n\n"
    for role, body, _ts in msgs:
        who = "🧑 تو" if role == "user" else "🛡 پشتیبانی"
        text += f"**{who}:** {body[:400]}\n\n"
    kb = []
    if t[4] != "closed":
        kb.append([InlineKeyboardButton(text="✉️ پاسخ", callback_data=f"ticket_reply_{tid}")])
    if _is_admin(callback.from_user.id):
        kb.append([InlineKeyboardButton(text="🔒 بستن", callback_data=f"ticket_close_{tid}")])
    kb.append([InlineKeyboardButton(text="🔙 لیست", callback_data="ticket_mine")])
    await edit_safe(callback.message, text[:4000],
                    InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_reply_"))
async def ticket_reply_start(callback: CallbackQuery, state: FSMContext):
    tid = int(callback.data.rsplit("_", 1)[1])
    await state.update_data(tk_reply_id=tid)
    await state.set_state(TicketFlow.reply)
    await callback.message.answer(f"✉️ پاسخت به تیکت #{tid} را بفرست:")
    await callback.answer()


@router.message(TicketFlow.reply, F.text)
async def ticket_reply_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    tid = data.get("tk_reply_id")
    await state.clear()
    if not tid:
        await message.answer("⌛ منقضی شد.")
        return
    t = await db.get_ticket(tid)
    if not t or (t[1] != message.from_user.id and not _is_admin(message.from_user.id)):
        await message.answer("دسترسی نداری!")
        return
    role = "admin" if _is_admin(message.from_user.id) else "user"
    if not await db.add_ticket_msg(tid, message.from_user.id, role, message.text.strip()):
        await message.answer("این تیکت بسته شده است.")
        return
    if role == "admin":
        await db.set_ticket_status(tid, "answered")
        try:
            await message.bot.send_message(t[1], f"📩 **پاسخ پشتیبانی به تیکت #{tid}:**\n\n{message.text.strip()[:2000]}",
                                           parse_mode="Markdown")
        except Exception:
            pass
        await message.answer(f"✅ پاسخ به کاربر ارسال شد (تیکت #{tid}).")
    else:
        await db.set_ticket_status(tid, "open")
        for aid in cfg.ADMIN_IDS:
            try:
                await message.bot.send_message(aid, f"💬 پاسخ جدید کاربر به تیکت #{tid} — `/trep {tid} متن`")
            except Exception:
                pass
        await message.answer(f"✅ پاسخت ثبت شد (تیکت #{tid}).")


@router.callback_query(F.data.startswith("ticket_close_"))
async def ticket_close(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("ادمین نیستی!", show_alert=True)
        return
    tid = int(callback.data.rsplit("_", 1)[1])
    await db.set_ticket_status(tid, "closed")
    await callback.answer(f"🔒 تیکت #{tid} بسته شد")


# ---------- گزارش تخلف ----------

@router.callback_query(F.data == "report_new")
async def report_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReportFlow.target)
    await edit_safe(callback.message,
        "🚩 **گزارش تخلف**\n\nID محصول یا آیدی کاربر خاطی را بفرست:\n(مثلاً: `17` یا `@username`)",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="support_menu")]]),
        parse_mode="Markdown")
    await callback.answer()


@router.message(ReportFlow.target, F.text)
async def report_target(message: Message, state: FSMContext):
    await state.update_data(rp_target=message.text.strip()[:120])
    await state.set_state(ReportFlow.reason)
    await message.answer("📝 **دلیل گزارش را بنویس:**")


@router.message(ReportFlow.reason, F.text)
async def report_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if "rp_target" not in data:
        await message.answer("⌛ منقضی شد.")
        return
    rid = await db.create_report(message.from_user.id, data["rp_target"], message.text.strip())
    for aid in cfg.ADMIN_IDS:
        try:
            await message.bot.send_message(aid,
                f"🚩 **گزارش تخلف #{rid}**\nهدف: `{data['rp_target']}`\nاز: `{message.from_user.id}`\n"
                f"📝 {message.text.strip()[:500]}\n\nبستن: `/repdone {rid}`",
                parse_mode="Markdown")
        except Exception:
            pass
    await message.answer(f"✅ **گزارش #{rid} ثبت شد — مرسی!**\n تیم بررسی می‌کند و در صورت تخلف، اقدام می‌شود.")


# ---------- ادمین ----------

@router.message(F.text.startswith("/tickets"))
async def tickets_cmd(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.list_open_tickets(10)
    if not rows:
        await message.answer("🎉 هیچ تیکت بازی نیست!")
        return
    text = "🎫 **تیکت‌های باز:**\n\n"
    for tid, uid, cat, subj, _upd in rows:
        text += f"#{tid} · {CATS.get(cat, cat)} · `{uid}`\n   📌 {subj[:50]}\n"
    text += "\nپاسخ: `/trep ID متن`"
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/trep "))
async def trep_cmd(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("فرمت: `/trep ID متن`", parse_mode="Markdown")
        return
    tid, body = int(parts[1]), parts[2].strip()
    t = await db.get_ticket(tid)
    if not t:
        await message.answer("تیکت پیدا نشد!")
        return
    if not await db.add_ticket_msg(tid, message.from_user.id, "admin", body):
        await message.answer("تیکت بسته است!")
        return
    await db.set_ticket_status(tid, "answered")
    try:
        await message.bot.send_message(t[1], f"📩 **پاسخ پشتیبانی به تیکت #{tid}:**\n\n{body[:2000]}",
                                       parse_mode="Markdown")
        await message.answer("✅ ارسال شد.")
    except Exception:
        await message.answer("⚠️ ثبت شد ولی DM به کاربر نشد (استارت نکرده؟)")


@router.message(F.text.startswith("/reports"))
async def reports_cmd(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.list_open_reports(10)
    if not rows:
        await message.answer("🎉 هیچ گزارش بازی نیست!")
        return
    text = "🚩 **گزارش‌های باز:**\n\n"
    for rid, uid, target, reason, _ts in rows:
        text += f"#{rid} · `{target}` · از `{uid}`\n   📝 {reason[:60]}\n"
    text += "\nبستن: `/repdone ID`"
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/repdone "))
async def repdone_cmd(message: Message):
    if not _is_admin(message.from_user.id):
        return
    try:
        rid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("فرمت: `/repdone ID`")
        return
    import time as _t
    from database import raw_db
    async with raw_db() as db2:
        cur = await db2.execute("UPDATE reports SET status = 'closed' WHERE id = ?", (rid,))
        await db2.commit()
    await message.answer("✅ بسته شد." if cur.rowcount else "پیدا نشد!")
