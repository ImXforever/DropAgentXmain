"""v4.0.0 — ماموریت‌های روزانه · سطح و XP · آمار شخصی و فروشنده"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from utils import edit_safe

router = Router()


def _bar(cur: int, target: int, width: int = 10) -> str:
    filled = int(width * min(1.0, cur / max(1, target)))
    return "█" * filled + "░" * (width - filled)


@router.callback_query(F.data == "quests_menu")
async def quests_menu(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("اول /start بزن!", show_alert=True)
        return
    xp = await db.xp_snapshot(user["user_id"])
    quests = await db.quests_view(user["user_id"])
    ready = [q for q in quests if q["done"] and not q["claimed"]]

    text = (f"🏆 **ماموریت‌ها و سطح تو**\n\n"
            f"{xp['title']}  ·  سطح **{xp['level']}**  ·  ⚡ **{xp['xp']:,} XP**\n")
    if xp["next_at"]:
        text += (f"{_bar(xp['xp'], xp['next_at'], 12)} `{xp['xp']:,}/{xp['next_at']:,}`\n"
                 f"برای سطح بعدی **{xp['next_at'] - xp['xp']:,} XP** مانده\n")
    text += "\n📜 **ماموریت‌های فعال:**\n"
    for q in quests:
        if q["claimed"]:
            st = "✅ جایزه گرفته شد"
        elif q["done"]:
            st = "🎁 آماده دریافت!"
        else:
            st = f"`{_bar(q['progress'], q['target'])}` `{q['progress']}/{q['target']}`"
        text += f"\n{q['title']}\n  💰 +{q['reward']} کردیت — {st}\n"
    if ready:
        text += f"\n🔥 **{len(ready)} جایزه آماده دریافت است — دکمه‌های پایین!**"

    kb = [[InlineKeyboardButton(text="📊 آمار من", callback_data="mystats"),
           InlineKeyboardButton(text="💸 فروش من", callback_data="mysales")]]
    for q in ready:
        kb.append([InlineKeyboardButton(
            text=f"🎁 دریافت +{q['reward']} — {q['title'][:22]}…",
            callback_data=f"quest_claim_{q['id']}")])
    kb.append([InlineKeyboardButton(text="🏆 لیدربورد", callback_data="leaderboard_xp_all")])
    kb.append([InlineKeyboardButton(text="📋 تسک‌ها", callback_data="tasks_menu"),
               InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")])
    await edit_safe(callback.message, text,
                    InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("quest_claim_"))
async def quest_claim(callback: CallbackQuery):
    try:
        qid = int(callback.data.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("نامعتبر!", show_alert=True)
        return
    ok, info = await db.claim_quest(qid, callback.from_user.id)
    if ok:
        user = await db.get_user(callback.from_user.id)
        await callback.answer(f"🎉 +{info} کردیت!", show_alert=True)
        await callback.message.answer(
            f"🎉 **جایزه ماموریت دریافت شد!**\n💰 **+{info:,} کردیت** — موجودی: **{user['credits']:,}**",
            parse_mode="Markdown")
    else:
        await callback.answer(info, show_alert=True)
    await quests_menu(callback)


@router.callback_query(F.data == "mystats")
async def mystats(callback: CallbackQuery):
    a = await db.user_analytics(callback.from_user.id)
    text = (f"📊 **آمار تو**\n\n"
            f"🛒 خریدها: **{a['purchases']}** | 💸 خرج کردیت: **{a['spent']:,}**\n"
            f"✅ تسک‌ها: **{a['tasks']}** | 👑 دعوت‌ها: **{a['referrals']}**\n"
            f"🏅 سطح: {a['title']} ({a['level']}) · ⚡ {a['xp']:,} XP\n"
            f"📅 {a['days']} روز است که همراه مایی\n"
            f"📊 از **{a['percentile']}٪** کاربرها بالاتری!")
    await edit_safe(callback.message, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 ماموریت‌ها", callback_data="quests_menu"),
         InlineKeyboardButton(text="💰 کیف پول", callback_data="wallet")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ]), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "mysales")
async def mysales(callback: CallbackQuery):
    s = await db.seller_analytics(callback.from_user.id)
    if not s["products"]:
        await callback.answer("هنوز محصولی نساختی — «📦 فروش کن» را بزن!", show_alert=True)
        return
    conv = (100.0 * s["units"] / s["views"]) if s["views"] else 0.0
    text = (f"💸 **فروشگاه تو در یک نگاه**\n\n"
            f"📦 محصولات: **{s['products']}** | 👁 بازدیدها: **{s['views']:,}**\n"
            f"🛒 فروش: **{s['units']}** عدد | 💰 درآمد: **{s['revenue']:,} کردیت**\n"
            f"👥 خریدار یکتا: **{s['buyers']}** | 📈 تبدیل بازدید→خرید: **{conv:.1f}٪**\n"
            f"⭐ میانگین امتیاز: **{s['avg_stars']}** ({s['n_reviews']} نظر)")
    if s["top"]:
        text += f"\n\n🥇 پرفروش‌ترین: **{s['top'][0][:40]}** ({s['top'][1]} فروش)"
    else:
        text += "\n\n💡 هنوز فروشی نداشتی — با «👥 دعوت دوستان» مشتری بیار!"
    await edit_safe(callback.message, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 محصولات من", callback_data="my_products"),
         InlineKeyboardButton(text="🏆 ماموریت‌ها", callback_data="quests_menu")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ]), parse_mode="Markdown")
    await callback.answer()
