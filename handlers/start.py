from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import create_user, get_user
from utils import get_or_create_user, send_safe

router = Router()


@router.message(F.text == "/cancel")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("↩️ باشه، لغو شد. هر وقت آماده بودی /start بزن 💪")


def main_menu_kb() -> InlineKeyboardMarkup:
    """UX v2 — ۷ دکمه به‌جای ۱۰ · گروه‌بندی منطقی · فعل‌محور"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [   # ── Core value props (top row = most visible) ──
            InlineKeyboardButton(text="💗 با هرمسا گپ بزن", callback_data="ai_chat"),
            InlineKeyboardButton(text="🛒 فروشگاه", callback_data="marketplace"),
        ],
        [   # ── Money actions ──
            InlineKeyboardButton(text="✅ کسب کردیت", callback_data="tasks_menu"),
            InlineKeyboardButton(text="💰 کیف پول", callback_data="wallet"),
        ],
        [   # ── Creator tools + growth ──
            InlineKeyboardButton(text="📦 فروش کن", callback_data="my_products"),
            InlineKeyboardButton(text="👥 دعوت دوستان", callback_data="referral"),
        ],
        [
            InlineKeyboardButton(text="👤 پروفایل", callback_data="profile"),
            InlineKeyboardButton(text="❓ راهنما", callback_data="help_menu"),
        ],
    ])


@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    from handlers.admin import is_member_of_force_channel, is_admin
    from database import get_setting
    if not is_admin(message.from_user.id) and \
            (await get_setting("maintenance", "0")) == "1":
        await send_safe(message,
            "🛠 **حالت نگهداری**\n\n"
            "چند دقیقه‌ای آپدیت داریم — الان برگردی همه‌چیز آماده‌ست 🙏")
        return
    if not await is_member_of_force_channel(message.bot, message.from_user.id):
        await message.answer(f"سلام {message.from_user.first_name}! خوشحالم که اینجایی 🌸")
        await send_safe(message,
            "🔒 فقط یه قدم مونده!\n\n"
            "عضو کانالمون شو تا جدیدترین محصولا، تخفیفای محدود و آموزش‌های رایگان "
            "رو قبل از بقیه ببینی:\n\n"
            "بعد از عضویت دکمهٔ زیر رو بزن 👇",
            await join_gate_kb())
        return

    await cmd_start_payload(message)


async def cmd_start_payload(message: Message):
    # deep link: /start ref_<referrer_id>
    referrer_id = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].strip().startswith("ref_"):
        raw = parts[1].strip()[4:]
        if raw.isdigit():
            referrer_id = int(raw)

    is_new = await get_or_create_user(message.from_user) is None
    user = await create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    if referrer_id and is_new:
        from database import set_referred_by
        from handlers.referral import pay_mystery_box
        if await set_referred_by(message.from_user.id, referrer_id):
            await pay_mystery_box(message.bot, referrer_id)

    kb = main_menu_kb()

    if is_new:
        # ── First-time welcome: hook → gift → clear path → FOMO ──
        welcome = (
            f"🌸 سلام {message.from_user.first_name}! خوش اومدی به خانواده 😊\n\n"
            f"🎁 یه هدیهٔ خوش‌اومدی برات گذاشتیم:\n"
            f"**{user['credits']:,} کردیت ≈ ۱$** — همین الان قابل استفاده!\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🚀 **فقط ۳ قدم تا اولین درآمد دلاریت:**\n\n"
            f"۱️⃣ ✅ چند تسک ساده بزن ← کردیت جمع کن\n"
            f"۲️⃣ 💗 با هرمسا حرف بزن ← ایده‌ات رو تبدیل به محصول کن\n"
            f"۳️⃣ 🛒 بفروش ← USDT برداشت کن\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🔥 همین الان {user['credits']:,} کردیت داری — "
            f"می‌تونی همین امروز شروع کنی!\n\n"
            f"💡 *۱٬۰۰۰ کردیت = ۱ USDT*"
        )
    else:
        from database import mem_count
        try:
            mem_n = await mem_count(user["user_id"])
        except Exception:
            mem_n = 0
        usd = user['credits'] / 1000

        # personalized nudge based on balance
        if user["credits"] < 10:
            nudge = (
                "⚠️ کردیتت تموم شده تقریباً! چند تسک بزن دوباره پر شه 💪\n"
                "👉 «✅ کسب کردیت» رو بزن"
            )
        elif user["credits"] < 100:
            nudge = (
                f"💡 با {user['credits']:,} کردیت می‌تونی با هرمسا چت کنی یا "
                f"محصولات ارزون بخری!"
            )
        elif user["credits"] >= 5000:
            nudge = "💸 تو بازهٔ برداختی! کیف پول رو چک کن 🎉"
        else:
            nudge = f"💡 با این موجودی می‌تونی محصولات خوبی بخری!"

        streak_line = ""
        if mem_n > 0:
            streak_line = f"🧠 حافظهٔ گفتگو: {mem_n} پیام — هرمسا یادش هست!\n"

        welcome = (
            f"👋 خوش برگشتی {user['first_name'] or 'عزیز'}! 😊\n\n"
            f"💰 موجودی: **{user['credits']:,} کردیت ≈ {usd:.2f}$**\n"
            + streak_line +
            f"\n{nudge}\n\n"
            f"👇 از کجا شروع کنیم؟"
        )

    await message.answer(welcome, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "main_menu")
async def back_to_main(callback, state: FSMContext):
    await state.clear()
    from handlers.admin import is_member_of_force_channel, join_gate_kb, is_admin
    from database import get_setting
    if not is_admin(callback.from_user.id) and \
            (await get_setting("maintenance", "0")) == "1":
        from utils import edit_safe as _es
        await _es(callback.message,
                  "🛠 حالت نگهداری — چند دقیقه دیگه برگرد.")
        await callback.answer()
        return
    if not await is_member_of_force_channel(callback.bot, callback.from_user.id):
        from utils import edit_safe as _es
        await _es(callback.message, "🔒 اول عضو کانال شو:", await join_gate_kb())
        await callback.answer()
        return

    user = await get_or_create_user(callback.from_user)
    usd = user["credits"] / 1000

    from utils import edit_safe as _es
    kb = main_menu_kb()

    # contextual greeting based on balance
    if user["credits"] < 10:
        tip = "💡 «✅ کسب کردیت» رو بزن تا دوباره شارژ شی!"
    elif user["credits"] >= 5000:
        tip = "💸 می‌تونی برداشت کنی! «💰 کیف پول» رو بزن"
    else:
        tip = "👇 چی می‌خوای انجام بدی؟"

    await _es(
        callback.message,
        f"👋 {user['first_name'] or 'عزیز'} جان!\n\n"
        f"💰 موجودی: **{user['credits']:,} کردیت ≈ {usd:.2f}$**\n"
        f"{tip}",
        kb,
    )
    await callback.answer()
