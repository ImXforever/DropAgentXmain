"""v3.5.0 — Growth: بونوس روزانه با استریک · کد هدیه کمپینی · امتیازدهی در-بات"""
import time

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import config as cfg
from utils import edit_safe
import database as db

router = Router()


class GrowthStates(StatesGroup):
    waiting_promo = State()


@router.callback_query(F.data == "daily_bonus")
async def daily_bonus_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    amount, streak = await db.claim_daily_bonus(
        callback.from_user.id,
        base=cfg.DAILY_BONUS_BASE, step=cfg.DAILY_BONUS_STEP, cap=cfg.DAILY_BONUS_CAP)
    if amount > 0:
        fire = "🔥" * min(5, 1 + streak // 2)
        await edit_safe(callback.message,
            f"🎁 **بونوس امروز دریافت شد!**\n\n"
            f"💰 **+{amount:,} کردیت** به موجودیت اضافه شد\n"
            f"{fire}\n"
            f"⚡ استریک تو: **{streak} روز پشت‌سرهم!**\n"
            f"📈 فردا: **+{min(cfg.DAILY_BONUS_BASE + streak * cfg.DAILY_BONUS_STEP, cfg.DAILY_BONUS_CAP):,} کردیت**\n\n"
            f"💡 هر روز بیا — استریک که قطع بشه از اول شروع می‌شه!",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 تسک‌های بیشتر", callback_data="available_tasks"),
                 InlineKeyboardButton(text="🛒 فروشگاه", callback_data="marketplace")],
                [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
            ]), parse_mode="Markdown")
        await callback.answer(f"🎉 +{amount} کردیت!")
    else:
        st = await db.daily_bonus_state(callback.from_user.id)
        hrs, mins = st["next_in"] // 3600, (st["next_in"] % 3600) // 60
        await edit_safe(callback.message,
            f"⏰ **بونوس امروز را گرفتی!**\n\n"
            f"⚡ استریک فعلی: **{st['streak']} روز**\n"
            f"🕒 بونوس بعدی: **{hrs} ساعت و {mins} دقیقه** دیگر\n\n"
            f"💡 تا اون موقع تسک بزن یا فروشگاه رو بگرد!",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 تسک‌ها", callback_data="tasks_menu"),
                 InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
            ]), parse_mode="Markdown")
        await callback.answer("⏰ فردا بیا!")


@router.callback_query(F.data == "promo_redeem")
async def promo_redeem_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GrowthStates.waiting_promo)
    await edit_safe(callback.message,
        "🎟 **کد هدیه**\n\n"
        "کدی که از تبلیغ/کانال گرفتی رو بفرست:\n"
        "(مثلاً: `LAUNCH50`)",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="wallet")],
        ]), parse_mode="Markdown")
    await callback.answer()


@router.message(GrowthStates.waiting_promo, F.text)
async def promo_redeem_msg(message: Message, state: FSMContext):
    await state.clear()
    ok, credits, reason = await db.redeem_promo(message.text.strip(), message.from_user.id)
    if ok:
        user = await db.get_user(message.from_user.id)
        await message.answer(
            f"🎉 **کد درست بود!**\n\n"
            f"💰 **+{credits:,} کردیت** شارژ شد\n"
            f"📌 موجودی جدید: **{user['credits']:,} کردیت**\n\n"
            "🛒 یه سر به فروشگاه بزن!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 فروشگاه", callback_data="marketplace"),
                 InlineKeyboardButton(text="💰 کیف پول", callback_data="wallet")],
            ]), parse_mode="Markdown")
    else:
        await message.answer(
            f"❌ **{reason}**\n\n"
            "کد رو دوباره چک کن (بزرگی/کوچکی حروف مهم نیست).",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎟 دوباره", callback_data="promo_redeem"),
                 InlineKeyboardButton(text="🔙 کیف پول", callback_data="wallet")],
            ]), parse_mode="Markdown")


@router.callback_query(F.data.startswith("rate_prod_"))
async def rate_prod_cb(callback: CallbackQuery):
    try:
        pid = int(callback.data.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("نامعتبر!", show_alert=True)
        return
    if not await db.is_product_purchased_by_user(pid, callback.from_user.id):
        await callback.answer("فقط خریدار می‌تواند امتیاز بدهد!", show_alert=True)
        return
    row = [InlineKeyboardButton(text="⭐" * s, callback_data=f"rate_do_{pid}_{s}") for s in range(1, 6)]
    await callback.message.answer(
        "🌟 **به این محصول امتیاز بده:**\n(کمک می‌کنی بقیه بهترین‌ها را پیدا کنند)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[row]))
    await callback.answer()


@router.callback_query(F.data.startswith("rate_do_"))
async def rate_do_cb(callback: CallbackQuery):
    try:
        _, _, pid_s, s_s = callback.data.split("_")
        pid, stars = int(pid_s), int(s_s)
    except (IndexError, ValueError):
        await callback.answer("نامعتبر!", show_alert=True)
        return
    if not await db.is_product_purchased_by_user(pid, callback.from_user.id):
        await callback.answer("فقط خریدار می‌تواند امتیاز بدهد!", show_alert=True)
        return
    await db.upsert_rate(pid, callback.from_user.id, stars)
    await callback.answer(f"🌟 ثبت شد — {stars} ستاره! مرسی!", show_alert=True)
