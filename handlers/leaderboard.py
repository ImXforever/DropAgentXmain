"""v4.0.0 — لیدربورد: رقابت سالم برای نگهداشت"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from utils import edit_safe

router = Router()
MEDALS = ["🥇", "🥈", "🥉"]
TABS = {"xp": "⚡ امتیاز", "buyers": "🛒 خریداران", "sellers": "💼 فروشندگان", "referrers": "👥 معرفان"}


@router.callback_query(F.data.startswith("leaderboard"))
async def leaderboard_cb(callback: CallbackQuery):
    parts = callback.data.split("_")
    kind = parts[1] if len(parts) > 1 and parts[1] in TABS else "xp"
    period = parts[2] if len(parts) > 2 else "all"
    days = 7 if period == "7d" else 0
    rows = await db.leaderboard(kind, days, 10)
    icon = "📅 این هفته" if days else "🌍 کل دوره"
    text = f"🏆 **لیدربورد {TABS[kind]}** — {icon}\n\n"
    if not rows:
        text += "هنوز رکوردی نیست — تو اولین باش! 🚀"
    for i, (uid, name, score) in enumerate(rows):
        m = MEDALS[i] if i < 3 else f"{i+1}."
        nm = (name or "کاربر")[:14] + ("…" if len(name or "") > 14 else "")
        me = " 👈 تو" if uid == callback.from_user.id else ""
        text += f"{m} {nm} — **{score:,}**{me}\n"
    text += "\n💪 هفته‌به‌هفته بالا بیا — مدال‌ها منتظرن!"
    kb = []
    row = [InlineKeyboardButton(
        text=f"{v}{'✓' if k == kind else ''}", callback_data=f"leaderboard_{k}_{period}")
        for k, v in TABS.items()]
    kb.append(row[:2]); kb.append(row[2:])
    kb.append([InlineKeyboardButton(text="📅 این هفته" if not days else "🌍 کل دوره",
                                    callback_data=f"leaderboard_{kind}_{'all' if not days else '7d'}"),
               InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")])
    await edit_safe(callback.message, text, InlineKeyboardMarkup(inline_keyboard=kb),
                    parse_mode="Markdown")
    await callback.answer()
