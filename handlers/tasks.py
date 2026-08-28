from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils import get_or_create_user,  send_safe, edit_safe
from database import (
    get_pending_tasks, get_user, update_credits,
    is_task_completed_by_user, get_user_tasks, get_db
)
from config import config

router = Router()


class TaskWizard(StatesGroup):
    """v3.4.0: ساخت تسک ۵ قدمی تمام‌دکمه‌ای — بدون فرمت تایپی"""
    waiting_title = State()
    waiting_url = State()
    waiting_custom_count = State()
    waiting_custom_reward = State()


@router.callback_query(F.data == "tasks_menu")
async def tasks_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 بونوس روزانه", callback_data="daily_bonus")],
        [InlineKeyboardButton(text="📋 تسک‌های فعال", callback_data="available_tasks")],
        [InlineKeyboardButton(text="⏳ در انتظار تأیید", callback_data="my_pending_tasks")],
        [InlineKeyboardButton(text="✅ انجام‌شده‌ها", callback_data="my_completed_tasks")],
        [InlineKeyboardButton(text="➕ ثبت تسک تبلیغی", callback_data="create_task")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    await edit_safe(callback.message, 
        f"✅ **تسک‌ها و کسب درآمد**\n\n"
        f"💰 کردیت شما: **{user['credits']:,}**\n\n"
        f"🎯 تسک بزن ← کردیت بگیر ← محصول بساز و بفروش!\n"
        f"🧙‍♂️ تبلیغ می‌خوای؟ «➕ ثبت تسک تبلیغی» حالا **تمام‌دکمه‌ای** است — ۵ قدم سریع، بدون تایپ فرمت!",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "available_tasks")
async def available_tasks(callback: CallbackQuery):
    tasks = await get_pending_tasks(limit=10)

    if not tasks:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="tasks_menu")],
        ])
        await edit_safe(callback.message, 
            "📋 **تسکی موجود نیست**\n\n"
            "فعلاً تسکی برای انجام وجود نداره.\n"
            "می‌تونی خودت تسک بسازی و به دیگران تبلیغ بدی!",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    text = "📋 **تسک‌های موجود:**\n\n"
    buttons = []

    for task in tasks:
        completed = await is_task_completed_by_user(task["id"], callback.from_user.id)
        status = "✅" if completed else "⬜"
        type_emoji = {"follow": "👥", "subscribe": "📢", "like": "❤️", "comment": "💬"}.get(task["task_type"], "📌")

        text += f"{status} {type_emoji} **{task['title']}**\n"
        text += f"    💰 {task['credits_reward']} کردیت | {task['task_type']}\n\n"

        if not completed:
            buttons.append([
                InlineKeyboardButton(
                    text=f"{type_emoji} {task['title']} (+{task['credits_reward']}💰)",
                    callback_data=f"do_task_{task['id']}"
                )
            ])

    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="tasks_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("do_task_"))
async def do_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    user = await get_or_create_user(callback.from_user)
    if await is_task_completed_by_user(task_id, callback.from_user.id):
        await callback.answer("قبلاً این تسک رو انجام دادی!", show_alert=True)
        return

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = await cursor.fetchone()
        if not task:
            await callback.answer("تسک پیدا نشد!", show_alert=True)
            return
        task = dict(task)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 باز کردن لینک هدف", url=task["target_url"])],
        [
            InlineKeyboardButton(text="✅ انجام دادم!", callback_data=f"confirm_task_{task_id}"),
            InlineKeyboardButton(text="❌ انصراف", callback_data="available_tasks"),
        ],
    ])

    type_emoji = {"follow": "👥", "subscribe": "📢", "like": "❤️", "comment": "💬"}.get(task["task_type"], "📌")

    await edit_safe(callback.message, 
        f"{type_emoji} **{task['title']}**\n\n"
        f"📝 {task['description'] or 'تسک ساده'}\n\n"
        f"💰 پاداش: **{task['credits_reward']}** کردیت\n"
        f"🔗 لینک: {task['target_url']}\n\n"
        f"1. روی لینک بالا کلیک کن\n"
        f"2. فالو/ساب کن\n"
        f"3. دکمه 'I Did It' رو بزن",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_task_"))
async def confirm_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[2])

    if await is_task_completed_by_user(task_id, callback.from_user.id):
        await callback.answer("قبلاً این تسک رو انجام دادی!", show_alert=True)
        return

    # ---- v2.0: جریان بررسی گزینه‌به‌گزینه ----
    # قبلاً «انجام دادم» = پاداش فوری و بدون بررسی (استاتوس verified) که هم
    # سوءاستفاده‌پذیر بود هم با شمارش واجد شرایطِ ریفرال (completed) نمی‌خواند.
    # حالا: status='pending' → ادمین از پنل، تکتک را ✅/❌ می‌کند.
    async with get_db() as db:
        cur = await db.execute(
            "SELECT COALESCE(max_completions,0), current_completions, "
            "credits_reward, title FROM tasks WHERE id = ?",
            (task_id,))
        trow = await cur.fetchone()
        if not trow:
            await callback.answer("تسک پیدا نشد!", show_alert=True)
            return
        if trow[0] > 0 and trow[1] >= trow[0]:
            await callback.answer("تسک تکمیل شده!", show_alert=True)
            return

        cur = await db.execute(
            "INSERT OR IGNORE INTO task_completions (task_id, user_id, status) "
            "VALUES (?, ?, 'pending')",
            (task_id, callback.from_user.id),
        )
        if cur.rowcount == 0:
            await callback.answer("این تسک در صف بررسی است!", show_alert=True)
            return

        await db.execute(
            "UPDATE tasks SET current_completions = current_completions + 1 WHERE id = ?",
            (task_id,),
        )
        await db.commit()
        reward, title = trow[2], trow[3]

    user = await get_or_create_user(callback.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 تسک‌های بیشتر", callback_data="available_tasks")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])

    await edit_safe(
        callback.message,
        f"⏳ **ثبت شد — در انتظار بررسی!**\n\n"
        f"📌 **{title}**\n"
        f"💰 پاداش پس از تأیید: **+{reward:,} کردیت** (≈{reward / 1000:.2f}$)\n\n"
        f"🕵️ ادمین‌ها تکتک انجام‌ها را بررسی می‌کنند؛ نتیجه به‌صورت پیام اعلام می‌شود.\n"
        f"💡 فعلاً {user['credits']:,} کردیت داری — تسک بعدی را بزن!",
        kb,
    )
    await callback.answer("ثبت شد — در صف بررسی ⏳", show_alert=True)


@router.callback_query(F.data == "my_pending_tasks")
async def my_pending_tasks(callback: CallbackQuery):
    tasks = await get_user_tasks(callback.from_user.id, "pending")

    if not tasks:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="tasks_menu")],
        ])
        await edit_safe(callback.message, 
            "⏳ **تسک در حال انتظار نداری**",
            reply_markup=kb, parse_mode="Markdown",
        )
        await callback.answer()
        return

    text = "⏳ **تسک‌های در حال انتظار:**\n\n"
    for t in tasks:
        text += f"• {t['title']} — {t['credits_reward']}💰\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="tasks_menu")],
    ])
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "my_completed_tasks")
async def my_completed_tasks(callback: CallbackQuery):
    tasks = await get_user_tasks(callback.from_user.id, "verified")

    if not tasks:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="tasks_menu")],
        ])
        await edit_safe(callback.message, 
            "✅ **تسک تکمیل شده‌ای نداری**\n\n"
            "برو تسک‌های موجود رو انجام بده!",
            reply_markup=kb, parse_mode="Markdown",
        )
        await callback.answer()
        return

    total_earned = sum(t["credits_reward"] for t in tasks)
    text = f"✅ **تسک‌های تکمیل شده:** ({len(tasks)} تسک)\n\n"
    for t in tasks[:10]:
        text += f"• {t['title']} — +{t['credits_reward']}💰\n"
    text += f"\n💰 مجموع کسب شده: **{total_earned}** کردیت"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="tasks_menu")],
    ])
    await edit_safe(callback.message, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "create_task")
async def create_task_start(callback: CallbackQuery, state: FSMContext):
    """v3.4.0: ویزارد ۵ قدمی دکمه‌ای — قدم ۱: نام تسک"""
    user = await get_or_create_user(callback.from_user)
    await state.clear()
    await state.set_state(TaskWizard.waiting_title)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    await edit_safe(callback.message,
        "🧙‍♂️ **ساخت تسک تبلیغی — ۵ قدم سریع**\n\n"
        f"**قدم ۱ از ۵ — 📝 اسم تسک:**\n"
        f"یه اسم جذاب بنویس (مثلاً: «فالو کانال تکنولوژی»)\n\n"
        f"💰 موجودی تو: **{user['credits']:,} کردیت**",
        kb, parse_mode="Markdown")
    await callback.answer()


@router.message(TaskWizard.waiting_title, F.text)
async def tw_title(message: Message, state: FSMContext):
    title = message.text.strip().replace("`", "'").replace("*", "")
    if not title or len(title) > 80:
        await message.answer("❌ اسم بین ۱ تا ۸۰ کاراکتر باشه. دوباره بفرست:")
        return
    await state.update_data(tw_title=title)
    await state.set_state(TaskWizard.waiting_url)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    await message.answer(
        "✅ قدم ۱ انجام شد!\n\n"
        "**قدم ۲ از ۵ — 🔗 لینک هدف:**\n"
        "لینکی که کاربرها باید باز کنن رو بفرست\n"
        "(مثلاً لینک کانالت: `https://t.me/MyChannel`)",
        reply_markup=kb, parse_mode="Markdown")


@router.message(TaskWizard.waiting_url, F.text)
async def tw_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(("http://", "https://", "tg://")):
        await message.answer("❌ لینک باید با `https://` یا `tg://` شروع بشه. دوباره بفرست:",
                             parse_mode="Markdown")
        return
    await state.update_data(tw_url=url)
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 فالو کانال", callback_data="tw_type_follow"),
         InlineKeyboardButton(text="📢 عضویت", callback_data="tw_type_subscribe")],
        [InlineKeyboardButton(text="❤️ لایک", callback_data="tw_type_like"),
         InlineKeyboardButton(text="💬 کامنت", callback_data="tw_type_comment")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    await message.answer(
        "✅ قدم ۲ انجام شد!\n\n"
        "**قدم ۳ از ۵ — 🎯 نوع تسک:**\n"
        "کاربرها دقیقاً چیکار باید بکنن؟",
        reply_markup=kb, parse_mode="Markdown")


async def _tw_guard(callback: CallbackQuery, state: FSMContext) -> dict:
    data = await state.get_data()
    if "tw_title" not in data or "tw_url" not in data:
        await callback.answer("⌛ این ویزارد منقضی شده — دوباره «➕ ثبت تسک تبلیغی» رو بزن!", show_alert=True)
        return None
    return data


@router.callback_query(F.data.startswith("tw_type_"))
async def tw_type(callback: CallbackQuery, state: FSMContext):
    data = await _tw_guard(callback, state)
    if not data:
        return
    ttype = callback.data.split("_", 2)[2]
    await state.update_data(tw_type=ttype)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="۵۰ نفر", callback_data="tw_count_50"),
         InlineKeyboardButton(text="۱۰۰ نفر", callback_data="tw_count_100")],
        [InlineKeyboardButton(text="۲۰۰ نفر", callback_data="tw_count_200"),
         InlineKeyboardButton(text="۵۰۰ نفر", callback_data="tw_count_500")],
        [InlineKeyboardButton(text="✍️ عدد دلخواه", callback_data="tw_count_custom")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    await edit_safe(callback.message,
        f"✅ قدم ۳ انجام شد: **{dict(follow='فالو کانال', subscribe='عضویت', like='لایک', comment='کامنت').get(ttype, ttype)}**\n\n"
        "**قدم ۴ از ۵ — 👥 چند نفر انجام بدن؟**",
        kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "tw_count_custom")
async def tw_count_custom(callback: CallbackQuery, state: FSMContext):
    if not await _tw_guard(callback, state):
        return
    await state.set_state(TaskWizard.waiting_custom_count)
    await edit_safe(callback.message,
        "✍️ **تعداد دقیق رو بفرست** (بین ۱ تا ۱۰۰٬۰۰۰):", None, parse_mode="Markdown")
    await callback.answer()


@router.message(TaskWizard.waiting_custom_count, F.text)
async def tw_count_custom_msg(message: Message, state: FSMContext):
    if not message.text.strip().isdigit() or not (1 <= int(message.text.strip()) <= 100000):
        await message.answer("❌ یه عدد بین ۱ تا ۱۰۰٬۰۰۰ بفرست:")
        return
    await state.update_data(tw_count=int(message.text.strip()))
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="۵💰", callback_data="tw_reward_5"),
         InlineKeyboardButton(text="۱۰💰", callback_data="tw_reward_10")],
        [InlineKeyboardButton(text="۲۵💰", callback_data="tw_reward_25"),
         InlineKeyboardButton(text="۵۰💰", callback_data="tw_reward_50")],
        [InlineKeyboardButton(text="✍️ عدد دلخواه", callback_data="tw_reward_custom")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    await message.answer(
        "✅ قدم ۴ انجام شد!\n\n"
        "**قدم ۵ از ۵ — 💰 پاداش هر نفر (کردیت):**",
        reply_markup=kb, parse_mode="Markdown")


async def _tw_ask_reward(callback: CallbackQuery, state: FSMContext, count: int):
    await state.update_data(tw_count=count)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="۵💰", callback_data="tw_reward_5"),
         InlineKeyboardButton(text="۱۰💰", callback_data="tw_reward_10")],
        [InlineKeyboardButton(text="۲۵💰", callback_data="tw_reward_25"),
         InlineKeyboardButton(text="۵۰💰", callback_data="tw_reward_50")],
        [InlineKeyboardButton(text="✍️ عدد دلخواه", callback_data="tw_reward_custom")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    await edit_safe(callback.message,
        f"✅ قدم ۴ انجام شد: **{count:,} نفر**\n\n"
        "**قدم ۵ از ۵ — 💰 پاداش هر نفر (کردیت):**",
        kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("tw_count_"))
async def tw_count(callback: CallbackQuery, state: FSMContext):
    data = await _tw_guard(callback, state)
    if not data:
        return
    await _tw_ask_reward(callback, state, int(callback.data.rsplit("_", 1)[1]))


@router.callback_query(F.data == "tw_reward_custom")
async def tw_reward_custom(callback: CallbackQuery, state: FSMContext):
    if not await _tw_guard(callback, state):
        return
    await state.set_state(TaskWizard.waiting_custom_reward)
    min_r = config.CREDITS_PER_FOLLOW
    await edit_safe(callback.message,
        f"✍️ **پاداش هر نفر رو بفرست** (حداقل {min_r} کردیت):", None, parse_mode="Markdown")
    await callback.answer()


@router.message(TaskWizard.waiting_custom_reward, F.text)
async def tw_reward_custom_msg(message: Message, state: FSMContext):
    min_r = config.CREDITS_PER_FOLLOW
    if not message.text.strip().isdigit() or int(message.text.strip()) < min_r:
        await message.answer(f"❌ یه عدد ≥ {min_r} بفرست:")
        return
    await state.update_data(tw_reward=int(message.text.strip()))
    await _tw_preview(message, state)


async def _tw_preview(message_or_cb, state: FSMContext):
    from utils import edit_safe as _es
    data = await state.get_data()
    title, url = data["tw_title"], data["tw_url"]
    ttype, count, reward = data["tw_type"], data["tw_count"], data["tw_reward"]
    total = count * reward
    user = await get_or_create_user(message_or_cb.from_user)
    type_fa = dict(follow="👥 فالو کانال", subscribe="📢 عضویت", like="❤️ لایک", comment="💬 کامنت").get(ttype, ttype)
    ok = user["credits"] >= total
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 ثبت نهایی", callback_data="tw_go" if ok else "tw_poor")],
        [InlineKeyboardButton(text="🔄 از اول", callback_data="create_task"),
         InlineKeyboardButton(text="❌ لغو", callback_data="tw_cancel")],
    ])
    text = (
        "👀 **پیش‌نمایش تسک — آخرین چک!**\n\n"
        f"📝 اسم: **{title}**\n"
        f"🎯 نوع: {type_fa}\n"
        f"🔗 لینک: {url}\n"
        f"👥 تعداد: **{count:,} نفر**\n"
        f"💰 پاداش هر نفر: **{reward:,} کردیت**\n"
        f"━━━━━━━━━\n"
        f"🧾 هزینه کل: **{total:,} کردیت** | موجودی تو: **{user['credits']:,}**\n\n"
        + ("🚀 همه‌چی آماده‌ست — «ثبت نهایی» رو بزن!" if ok else
           "⚠️ **موجودی کافی نیست!** «تعداد» یا «پاداش» رو کم کن — دکمهٔ 🔄 از اول")
    )
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await _es(message_or_cb.message, text, kb, parse_mode="Markdown")


@router.callback_query(F.data == "tw_poor")
async def tw_poor(callback: CallbackQuery):
    await callback.answer("💰 موجودی کافی نیست — تعداد یا پاداش رو کم کن (🔄 از اول)", show_alert=True)


@router.callback_query(F.data.startswith("tw_reward_"))
async def tw_reward(callback: CallbackQuery, state: FSMContext):
    data = await _tw_guard(callback, state)
    if not data:
        return
    reward = int(callback.data.rsplit("_", 1)[1])
    if reward < config.CREDITS_PER_FOLLOW:
        await callback.answer(f"حداقل پاداش {config.CREDITS_PER_FOLLOW} کردیت است!", show_alert=True)
        return
    await state.update_data(tw_reward=reward)
    await _tw_preview(callback, state)
    await callback.answer()


@router.callback_query(F.data == "tw_go")
async def tw_go(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "tw_title" not in data:
        await callback.answer("⌛ منقضی شده!", show_alert=True)
        return
    title, url = data["tw_title"], data["tw_url"]
    ttype, count, reward = data["tw_type"], data["tw_count"], data["tw_reward"]
    total = count * reward
    user = await get_or_create_user(callback.from_user)
    if user["credits"] < total:
        await callback.answer("موجودی کافی نیست!", show_alert=True)
        return
    async with get_db() as db:
        await db.execute(
            """INSERT INTO tasks (title, task_type, target_url, credits_reward, max_completions, creator_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, ttype, url, reward, count, callback.from_user.id))
        await db.commit()
    await update_credits(callback.from_user.id, -total, "task_creation",
                         f"Created task: {title} (budget: {total})")
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 دیدن تسک‌ها", callback_data="available_tasks")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])
    await edit_safe(callback.message,
        "🎉 **تسکت منتشر شد!**\n\n"
        f"📌 {title}\n"
        f"💰 هزینه: **{total:,} کردیت** کم شد\n"
        f"📊 **{count:,} نفر** می‌تونن انجامش بدن\n\n"
        "⏳ انجام‌ها بعد از بررسی تأیید می‌شن و اگه کسی تقلب کنه پاداش نمی‌گیره — خیالت راحت!",
        kb, parse_mode="Markdown")
    await callback.answer("🎉 منتشر شد!")


@router.callback_query(F.data == "tw_cancel")
async def tw_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 تسک‌های فعال", callback_data="available_tasks")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])
    await edit_safe(callback.message,
        f"🚫 ساخت تسک لغو شد.\n\n💰 موجودی تو: **{user['credits']:,} کردیت**\n"
        "هر وقت خواستی «➕ ثبت تسک تبلیغی» رو بزن — ۵ قدم سریعه!",
        kb, parse_mode="Markdown")
    await callback.answer("لغو شد")
