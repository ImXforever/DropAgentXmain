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


class TaskCreation(StatesGroup):
    waiting_details = State()


@router.callback_query(F.data == "tasks_menu")
async def tasks_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 تسک‌های فعال", callback_data="available_tasks")],
        [InlineKeyboardButton(text="⏳ در انتظار تأیید", callback_data="my_pending_tasks")],
        [InlineKeyboardButton(text="✅ انجام‌شده‌ها", callback_data="my_completed_tasks")],
        [InlineKeyboardButton(text="➕ ثبت تسک تبلیغی", callback_data="create_task")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    await edit_safe(callback.message, 
        f"✅ **تسک‌ها و کسب درآمد**\n\n"
        f"💰 کردیت شما: **{user['credits']}**\n\n"
        f"🎯 با انجام تسک‌های ساده (فالو/ساب)، کردیت جمع کن و محصول بعدی‌ات را بساز.",
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

    # ---- atomic completion: unique(task,user) guards double-reward ----
    rewarded = False
    reward = title = None
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
            "VALUES (?, ?, 'verified')",
            (task_id, callback.from_user.id),
        )
        if cur.rowcount == 0:
            await callback.answer("قبلاً این تسک رو انجام دادی!", show_alert=True)
            return

        await db.execute(
            "UPDATE tasks SET current_completions = current_completions + 1 WHERE id = ?",
            (task_id,),
        )
        await db.commit()
        rewarded = True
        _, _, reward, title = trow

    if not rewarded:
        return

    await update_credits(
        callback.from_user.id,
        reward,
        "task_completion",
        f"Completed task: {title}",
        task_id,
    )

    # 1-B: tasks count toward referral qualification (need ≥3 tasks OR purchase)
    from handlers.referral import maybe_qualify_referral
    await maybe_qualify_referral(callback.bot, callback.from_user.id)


    user = await get_or_create_user(callback.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 تسک‌های بیشتر", callback_data="available_tasks")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])

    await edit_safe(
        callback.message,
        f"✅ **تسک تکمیل شد! آفرین** 🎉\n\n"
        f"💰 **+{reward:,} کردیت** (≈{reward / 1000:.2f}$)\n"
        f"💳 موجودی: **{user['credits']:,} کردیت** "
        f"(≈{user['credits'] / 1000:.2f}$)\n\n"
        f"💡 همینطور ادامه بده تا به حداقل برداشت برسی!",
        kb,
    )
    await callback.answer("کردیت دریافت شد! 🎉", show_alert=True)


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
    user = await get_or_create_user(callback.from_user)
    min_cost = config.CREDITS_PER_FOLLOW

    await state.set_state(TaskCreation.waiting_details)
    await edit_safe(callback.message, 
        "➕ **ساخت تسک جدید (تبلیغ)**\n\n"
        "برای ساخت تسک، اطلاعات زیر رو به من بده:\n\n"
        f"💰 هزینه هر فالو: حداقل {min_cost} کردیت\n"
        f"💰 موجودی شما: {user['credits']} کردیت\n\n"
        "📝 لطفاً اطلاعات رو به این فرمت بفرست:\n\n"
        "`نام تسک | نوع (follow/subscribe) | لینک | تعداد | پاداش هرکدام`\n\n"
        "مثال:\n"
        "`کانال تکنولوژی | follow | https://t.me/techchannel | 100 | 5`\n\n"
        "برای لغو /cancel بزن.",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(TaskCreation.waiting_details, F.text)
async def process_task_creation(message: Message, state: FSMContext):
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) != 5:
        await message.answer(
            "❌ فرمت اشتباهه! دقیقاً ۵ بخش با `|` جدا کن:\n"
            "`نام | نوع | لینک | تعداد | پاداش`",
            parse_mode="Markdown",
        )
        return

    title, task_type, target_url, max_completions_str, credits_str = parts

    if not title or len(title) > 80:
        await message.answer("❌ نام تسک بین ۱ تا ۸۰ کاراکتر باشه.")
        return

    try:
        max_completions = int(max_completions_str)
        credits_reward = int(credits_str)
    except ValueError:
        await message.answer("❌ «تعداد» و «پاداش» باید عدد باشن.")
        return

    if task_type not in ["follow", "subscribe", "like", "comment"]:
        await message.answer("❌ نوع تسک باید یکی از: follow, subscribe, like, comment باشه")
        return

    if not target_url.startswith(("http://", "https://", "tg://")):
        await message.answer("❌ لینک باید با http:// یا https:// شروع بشه.")
        return

    if max_completions < 1 or max_completions > 100000:
        await message.answer("❌ تعداد باید بین ۱ تا ۱۰۰,۰۰۰ باشه.")
        return

    if credits_reward < config.CREDITS_PER_FOLLOW:
        await message.answer(f"❌ حداقل پاداش: {config.CREDITS_PER_FOLLOW} کردیت")
        return

    total_cost = max_completions * credits_reward
    user = await get_or_create_user(message.from_user)
    if user["credits"] < total_cost:
        await message.answer(
            f"❌ کردیت کافی نداری!\n"
            f"هزینه کل: {total_cost} کردیت\n"
            f"موجودی: {user['credits']} کردیت\n\n"
            f"💡 یا تعداد/پاداش رو کم کن."
        )
        return

    async with get_db() as db:
        await db.execute(
            """INSERT INTO tasks (title, task_type, target_url, credits_reward, max_completions, creator_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, task_type, target_url, credits_reward, max_completions, message.from_user.id),
        )
        await db.commit()

    await update_credits(
        message.from_user.id,
        -total_cost,
        "task_creation",
        f"Created task: {title} (budget: {total_cost})",
    )
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 دیدن تسک‌ها", callback_data="available_tasks")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    await message.answer(
        f"✅ **تسک ساخته شد!**\n\n"
        f"📌 {title}\n"
        f"💰 هزینه: {total_cost} کردیت\n"
        f"📊 {max_completions} نفر می‌تونن انجام بدن",
        reply_markup=kb,
        parse_mode="Markdown",
    )
