import random

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import config as cfg
from database import (
    get_db, get_user, update_credits,
    count_total_refs, count_qualified_refs,
    list_top_referrers, is_milestone_awarded, award_ref_milestone,
)
from utils import get_or_create_user,  edit_safe

router = Router()


def ref_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


async def pay_mystery_box(bot: Bot, referrer_id: int) -> None:
    """Robinhood-style instant random reward on each new signup."""
    amount = random.randint(cfg.REF_MYSTERY_MIN, cfg.REF_MYSTERY_MAX)
    await update_credits(referrer_id, amount, "ref_mystery", "Mystery box for new referral signup")
    try:
        u = await get_user(referrer_id)
        name = (u or {}).get("first_name") or "دوست"
        await bot.send_message(
            referrer_id,
            f"🎁 جعبه شانس! یک نفر با لینک تو عضو شد و **{amount} کردیت** گرفتی.\n"
            f"بعد از اولین فعالیتش، بونوس کامل {cfg.REF_INVITE_BONUS_REFERRER} کردیتی هم می‌گیری!",
            parse_mode="Markdown",
        )
    except Exception:
        pass


async def check_qualification(uid: int) -> bool:
    """1-B: Referral qualifies after REAL purchase OR 3 completed tasks."""
    from database import get_db
    async with get_db() as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM purchases WHERE buyer_id=?", (uid,))
        has_purchase = (await cur.fetchone())[0] > 0
        cur = await db.execute(
            """SELECT COUNT(DISTINCT task_id) FROM task_completions
               WHERE user_id=? AND status='completed'""", (uid,))
        tasks_done = (await cur.fetchone())[0]
    return has_purchase or tasks_done >= 3


async def maybe_qualify_referral(bot: Bot, referee_id: int) -> None:
    """Call after referee does something. Only pays if 1-B gate passes."""
    from database import get_referrer, mark_ref_bonus_paid

    referrer_id = await get_referrer(referee_id)
    if not referrer_id:
        return

    # 1-B: qualification gate — purchase OR ≥3 tasks
    if not await check_qualification(referee_id):
        return

    if not await mark_ref_bonus_paid(referee_id):
        return

    await update_credits(
        referrer_id, cfg.REF_INVITE_BONUS_REFERRER, "ref_bonus",
        f"Referral bonus — invited user {referee_id} became active",
    )
    await update_credits(
        referee_id, cfg.REF_BONUS_REFEREE, "ref_bonus",
        "Referral welcome bonus",
    )

    try:
        await bot.send_message(
            referrer_id,
            f"🤝 دعوتت موفق بود!\n"
            f"کاربر معرفی‌شده اولین فعالیتش رو انجام داد و **{cfg.REF_INVITE_BONUS_REFERRER} کردیت** به حسابت اضافه شد.",
            parse_mode="Markdown",
        )
        await bot.send_message(
            referee_id,
            f"🎉 بونوس دوستی! **{cfg.REF_BONUS_REFEREE} کردیت** هدیه گرفتی.",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    # Fractal autonomy: enough qualified referrals crowns the referrer a Capo
    qualified_now = await count_qualified_refs(referrer_id)
    from database import get_role, set_role
    if qualified_now >= cfg.CAPO_MIN_REFS and await get_role(referrer_id) == "soldier":
        if await set_role(referrer_id, "capo", granted_by=0):
            try:
                await bot.send_message(
                    referrer_id,
                    f"🕴️ **تو کاپو شدی!**\n\n"
                    f"{qualified_now} سرباز فعال شبکه‌ات داره.\n"
                    f"از هر فروشِ فروشنده‌های زیرمجموعه‌ات {int(cfg.CAPO_OVERRIDE_PCT*100)}٪ "
                    f"اوورراید می‌گیری. تیمت مال توئه — رشدش بده!",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    await check_milestones(bot, referrer_id)


async def check_milestones(bot: Bot, referrer_id: int) -> None:
    qualified = await count_qualified_refs(referrer_id)
    for threshold in sorted(cfg.REF_MILESTONES.keys()):
        if qualified >= threshold and not await is_milestone_awarded(referrer_id, threshold):
            if await award_ref_milestone(referrer_id, threshold):
                reward = cfg.REF_MILESTONES[threshold]
                await update_credits(
                    referrer_id, reward, "ref_milestone",
                    f"Milestone {threshold} referrals reached",
                )
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🏆 **مایلستون {threshold} نفر!**\n"
                        f"جایزه **{reward:,} کردیت** به حسابت اضافه شد.",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass


@router.callback_query(F.data == "referral")
async def referral_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user)
    me = callback.bot._me if hasattr(callback.bot, "_me") else None
    username = getattr(me, "username", None) or (await callback.bot.me()).username

    total = await count_total_refs(user["user_id"])
    qualified = await count_qualified_refs(user["user_id"])
    link = ref_link(username, user["user_id"])

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM transactions
               WHERE user_id = ? AND tx_type IN ('ref_bonus', 'ref_mystery', 'ref_commission', 'ref_milestone')""",
            (user["user_id"],),
        )
        earned = (await cursor.fetchone())[0]

    # Tesla-style progress bar toward next milestone
    thresholds = sorted(cfg.REF_MILESTONES.keys())
    nxt = next((t for t in thresholds if qualified < t), None)
    if nxt:
        filled = int((qualified / nxt) * 10)
        bar = "█" * filled + "░" * (10 - filled)
        ms_line = f"🎯 پله بعدی: **{qualified}/{nxt}** نفر [{bar}] → {cfg.REF_MILESTONES[nxt]:,} کردیت"
    else:
        ms_line = "👑 همه پله‌ها رو فتح کردی!"

    top = await list_top_referrers(5)
    top_line = ""
    if top:
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        names = []
        for i, r in enumerate(top):
            mark = " (تو)" if r["user_id"] == user["user_id"] else ""
            names.append(f"{medals[i]} {r['name']}{mark} — {r['cnt']} نفر")
        top_line = "\n\n🏅 **برترین معرفان:**\n" + "\n".join(names)

    share_url = f"https://t.me/share/url?url={link}&text=%F0%9F%9A%80%20%D8%AF%D8%B1%20Hermes%20Marketplace%20%D8%A8%D8%A7%20AI%20%D9%85%D8%AD%D8%B5%D9%88%D9%84%20%D8%A8%D8%B3%D8%A7%D8%B2%20%D9%88%20%D8%A8%D9%81%D8%B1%D9%88%D8%B4!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 اشتراک‌گذاری لینک", url=share_url)],
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="referral"),
         InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])

    await edit_safe(
        callback.message,
        f"👥 **سیستم دعوت دوستان**\n\n"
        f"🔗 **لینک اختصاصی‌ات:**\n`{link}`\n\n"
        f"📊 آمار:\n"
        f"• دعوت‌شده: **{total}** نفر\n"
        f"• فعال‌شده (با اولین تسک/خرید): **{qualified}** نفر\n"
        f"• درآمد از دعوت: **{earned:,} کردیت**\n\n"
        f"{ms_line}\n\n"
        f"💎 **جایزه‌ها:**\n"
        f"🎁 ثبت‌نام هر نفر → جعبه شانس {cfg.REF_MYSTERY_MIN}-{cfg.REF_MYSTERY_MAX} کردیت (فوری)\n"
        f"🤝 اولین فعالیتش → {cfg.REF_INVITE_BONUS_REFERRER} کردیت برای تو + {cfg.REF_BONUS_REFEREE} برای او\n"
        f"💼 فروش کنه → **{int(cfg.REF_COMMISSION_SHARE*100)}٪ از کمیسیون فروشش، همیشه**، مال تو\n"
        f"🏆 پله‌ها: " + " | ".join(f"{t}نفر={v:,}" for t, v in sorted(cfg.REF_MILESTONES.items())) + "\n"
        f"{top_line}",
        kb,
    )
    await callback.answer()
