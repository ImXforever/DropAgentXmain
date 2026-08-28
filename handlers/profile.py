from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from utils import get_or_create_user,  send_safe, edit_safe
from database import get_user, get_user_stats, get_my_products, get_leaderboard

router = Router()


@router.callback_query(F.data == "leaderboard")
async def leaderboard(callback: CallbackQuery):
    users = await get_leaderboard(limit=10)

    text = "🏆 **رهبران بازار**\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"#{i + 1}"
        name = u["first_name"] or u["username"] or "ناشناس"
        text += (f"{medal} {name} — {u['credits']:,}💰 "
                 f"(≈{u['credits'] / 1000:.2f}$) | فروش: {u['products_sold']}\n")

    if not users:
        text += "_هنوز کسی در جدول نیست — جای تو خالیه!_ ✨\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])

    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "profile")
async def profile_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    if not user:  # DB hiccup — fail gracefully instead of AttributeError
        await callback.answer("خطا در بارگذاری پروفایل — چند لحظه بعد دوباره امتحان کن",
                              show_alert=True)
        return
    stats = await get_user_stats(callback.from_user.id)
    products = await get_my_products(callback.from_user.id)

    per = 1000  # CREDITS_PER_USDT
    total_product_value = sum(p["price_credits"] * p["sales_count"] for p in products)

    rank = user.get("role") or "associate"
    ranks = ["associate", "soldier", "capo", "underboss"]
    try:
        ridx = ranks.index(rank)
    except ValueError:
        ridx = 0
    next_rank_fa = {"associate": "سرباز (اولین فروشت رو بزن!)",
                    "soldier": "کاپو (۱۰ دعوت فعال)",
                    "capo": "آندرباس (انتصاب ادمین)",
                    "underboss": ""}.get(rank, "")
    ladder = (" → ".join("⭐" if i == ridx else "○" for i in range(4)))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 محصولات من", callback_data="my_products"),
         InlineKeyboardButton(text="📊 آمار", callback_data="profile_stats")],
        [InlineKeyboardButton(text="🧠 حافظه من", callback_data="my_memory")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])

    await edit_safe(callback.message,
        f"👤 **پروفایل شما**\n\n"
        f"👤 نام: {user['first_name'] or '-'}"
        f"{' · @' + user['username'] if user['username'] else ''}\n\n"
        f"💰 موجودی: **{user['credits']:,} کردیت** "
        f"(≈{user['credits'] / per:.2f}$)\n"
        f"📈 کل کسب‌شده: {user['total_earned']:,} کردیت\n"
        f"📉 کل خرج‌شده: {user['total_spent']:,} کردیت\n\n"
        f"🎖 رتبه: **{rank}** {ladder}\n"
        + (f"↗️ قدم بعدی: {next_rank_fa}\n" if next_rank_fa else "") +
        f"\n📊 **آمار:**\n"
        f"✅ تسک‌ها: {stats['tasks_done']} · 📦 محصولات: {stats['products_listed']} · "
        f"🛒 خریدها: {stats['products_bought']} · "
        f"💰 ارزش فروش: {total_product_value:,} کردیت\n"
        f"📊 فروش‌های موفق: {user['products_sold']}",
        reply_markup=kb, parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user)
    stats = await get_user_stats(callback.from_user.id)

    products = await get_my_products(callback.from_user.id)
    if products:
        avg_price = sum(p["price_credits"] for p in products) / len(products)
        total_sales = sum(p["sales_count"] for p in products)
    else:
        avg_price = 0
        total_sales = 0

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 پروفایل", callback_data="profile")],
    ])

    per = 1000
    await edit_safe(callback.message,
        f"📊 **آمار کامل**\n\n"
        f"💰 موجودی: **{user['credits']:,} کردیت** (≈{user['credits'] / per:.2f}$)\n"
        f"📈 کل درآمد: {user['total_earned']:,} کردیت (≈{user['total_earned'] / per:.2f}$)\n"
        f"📉 کل هزینه: {user['total_spent']:,} کردیت\n\n"
        f"✅ تسک: {stats['tasks_done']} · 📦 محصول: {stats['products_listed']} · "
        f"🛒 خرید: {stats['products_bought']}\n\n"
        f"📊 **فروش:**\n"
        f"💰 تعداد فروش: {total_sales}\n"
        f"💵 میانگین قیمت: {avg_price:.0f} کردیت (≈{avg_price / per:.2f}$)\n"
        f"📊 نرخ تبدیل: {(total_sales / max(stats['products_listed'], 1) * 100):.1f}%",
        reply_markup=kb, parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "my_memory")
async def my_memory(callback: CallbackQuery):
    from memory import my_memory_summary
    text, total = await my_memory_summary(callback.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 پیشنهاد برای من", callback_data="mp_recs")],
        [InlineKeyboardButton(text="🗑 فراموش کن", callback_data="mem_forget")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="profile")],
    ])
    await edit_safe(
        callback.message,
        f"🧠 **حافظهٔ بلندمدت تو** ({total} خاطره)\n\n{text}\n\n"
        "💡 هرمس از چت‌ها و خریدهایت سلیقه‌ات را یاد می‌گیرد تا پیشنهادها و "
        "پاسخ‌ها شخصی‌تر شوند. با «فراموش کن» همه‌اش پاک می‌شود.",
        reply_markup=kb, parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "mem_forget")
async def mem_forget_confirm(callback: CallbackQuery):
    await edit_safe(
        callback.message,
        "🗑 **پاک کردن حافظهٔ بلندمدت**\n\n"
        "همهٔ خاطرات، پروفایل خرید و شخصیت‌سازی پاک می‌شود "
        "(کردیت و خریدهای واقعی دست نمی‌خورند). مطمئنی؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ بله، فراموش کن", callback_data="mem_forget_yes")],
            [InlineKeyboardButton(text="❌ نه، بی‌خیال", callback_data="my_memory")],
        ]),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "mem_forget_yes")
async def mem_forget_do(callback: CallbackQuery):
    from memory import forget_me
    n = await forget_me(callback.from_user.id)
    await edit_safe(
        callback.message,
        f"🧹 {n} خاطره پاک شد — حافظهٔ بلندمدتت خالی است.\n"
        "از این به بعد دوباره از صفر یاد می‌گیرم.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="profile")],
        ]),
    )
    await callback.answer("فراموش شد ✅", show_alert=True)
