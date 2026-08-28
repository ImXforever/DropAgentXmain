"""
DropAgentX v2.0.0 — Admin v2.

The v1 admin panel was rich in *finance/moderation* but thin on *intelligence,
observability and support tools*. This module adds a second admin surface that
fills the gaps:

    /id      <user>   live identity (RL label + confidence + behaviour features)
    /mem2    <user>   multi-faceted memory: stats per facet + sticky identity
    /logs    [user]   recent persisted logs (observability) via Telegram
    /errmap           overview: errors per logger, counts, uptime signal
    /rlset   on|off   toggle the identity RL agent
    /system           runtime health (DB size, users, purchases, open errors)

All replies go through `send_safe` so they never hit the legacy-Markdown crash.
"""

import time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import config
from utils import send_safe, edit_safe

router = Router()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_rows(rows, cols=("id", "ts", "level", "logger", "msg")):
    out = []
    for r in rows:
        out.append(f"{r.get('ts','')} {r.get('level','')} {r.get('logger','')} {str(r.get('msg',''))[:120]}")
    return "\n".join(out) or "(خالی)"


async def _admin_only(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def _kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])


# ---------------------------------------------------------------------------
# /id — live identity (RL label + behaviour)
# ---------------------------------------------------------------------------

def _uid_from(message: Message):
    parts = message.text.split()
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None


@router.message(F.text.startswith("/id"))
async def cmd_identity(message: Message):
    if not await _admin_only(message.from_user.id):
        return await send_safe(message, "⛔ ادمین نیستی.")
    uid = _uid_from(message)
    if uid is None:
        return await send_safe(message, "استفاده: `/id <user_id>`  (مثلاً `/id 12345678`)")
    try:
        from identity_rl import get_identity
        snap = await get_identity(uid)
    except Exception as e:
        return await send_safe(message, f"❌ خطا:\n{e}")
    f = snap.get("features", {})
    txt = (
        f"🪪 هویت کاربر **{uid}**\n"
        f"━━━━━━━━━━━\n"
        f"🎯 برچسب: **{snap.get('label')}**\n"
        f"📊 اطمینان: `{snap.get('confidence', 0)}`\n"
        f"👀 بازدید/فعالیت: `{f.get('visits', 0)}`\n"
        f"🛒 خرید: `{f.get('purchases', 0)}`\n"
        f"📋 تسک: `{f.get('tasks', 0)}`\n"
        f"💸 برداشت: `{f.get('withdraws', 0)}`\n"
        f"🗣 چت: `{f.get('chat_level', 0)}`\n"
        f"🕒 سشن: bucket `{f.get('session_bucket', 0)}`\n"
        f"🆕 تازه‌وارد: `{f.get('freshness', 0)}`\n"
        f"🖥 state: `{snap.get('state','')}`"
    )
    await send_safe(message, txt)


@router.message(F.text.startswith("/mem2"))
async def cmd_mem2(message: Message):
    if not await _admin_only(message.from_user.id):
        return
    uid = _uid_from(message)
    if uid is None:
        return await send_safe(message, "استفاده: `/mem2 <user_id>`  — آمار و محتوای حافظهٔ چندوجهی")
    try:
        import memory2
        stats = await memory2.facet_stats(uid)
        mems = await memory2.list_all(uid, limit=40)
    except Exception as e:
        return await send_safe(message, f"❌ خطا:\n{e}")
    lines = [f"🧠 حافظهٔ چندوجهی کاربر **{uid}**", "━━━━━━━━━━━"]
    if not stats:
        lines.append("(هیچ حافظه‌ای ثبت نشده)")
    for f, s in sorted(stats.items()):
        lines.append(f"`{f}`: {s['count']} مورد · میانگین اهمیت {s['avg_importance']}")
    lines.append("━━━━━━━━━━━")
    for m in mems[:8]:
        tag = m.facet
        lines.append(f"[{tag}] {m.content[:90]}")
    await send_safe(message, "\n".join(lines))


# ---------------------------------------------------------------------------
# /logs — recent persisted logs
# ---------------------------------------------------------------------------

@router.message(F.text.startswith("/logs"))
async def cmd_logs(message: Message):
    if not await _admin_only(message.from_user.id):
        return
    uid = _uid_from(message)
    limit = 12
    try:
        from database import raw_db
        async with raw_db() as db:
            if uid:
                cur = await db.execute(
                    "SELECT id, ts, level, logger, msg FROM app_logs "
                    "WHERE user_id=? ORDER BY id DESC LIMIT ?", (int(uid), limit))
            else:
                cur = await db.execute(
                    "SELECT id, ts, level, logger, msg FROM app_logs "
                    "ORDER BY id DESC LIMIT ?", (limit,))
            rows = [dict(zip(("id", "ts", "level", "logger", "msg"), r))
                    for r in await cur.fetchall()]
    except Exception as e:
        return await send_safe(message, f"❌ جدول لاگ در دسترس نیست: {e}")
    if not rows:
        return await send_safe(message, "📭 لاگی ثبت نشده (یا ادمین محتوا فعال نیست).")
    body = "\n".join(f"{r['level']:<7} {r['logger']}: {str(r['msg'])[:110]}" for r in rows)
    await send_safe(message, f"🗒 آخرین لاگ‌ها:\n━━━━━━━━━━━\n{body}")


# ---------------------------------------------------------------------------
# /errmap — error overview
# ---------------------------------------------------------------------------

@router.message(F.text == "/errmap")
async def cmd_errmap(message: Message):
    if not await _admin_only(message.from_user.id):
        return
    try:
        from database import raw_db
        async with raw_db() as db:
            cur = await db.execute(
                "SELECT level, COUNT(*) FROM app_logs WHERE level IN ('ERROR','CRITICAL') "
                "GROUP BY level ORDER BY 2 DESC")
            by_level = {str(r[0]): r[1] for r in await cur.fetchall()}
            cur2 = await db.execute(
                "SELECT logger, COUNT(*) FROM app_logs WHERE level IN ('ERROR','CRITICAL') "
                "GROUP BY logger ORDER BY 2 DESC LIMIT 10")
            by_logger = [(str(r[0]), r[1]) for r in await cur2.fetchall()]
    except Exception as e:
        return await send_safe(message, f"❌ {e}")
    lines = ["🧨 نمای خطاها (حدود ۲۴h)", "━━━━━━━━━━━"]
    lines.append(f"خطاهای ERROR/CRITICAL: `{sum(by_level.values())}`")
    for lg, c in by_logger:
        lines.append(f"`{lg}` → {c}")
    await send_safe(message, "\n".join(lines))


# ---------------------------------------------------------------------------
# /rlset — toggle identity RL
# ---------------------------------------------------------------------------

@router.message(F.text.startswith("/rlset"))
async def cmd_rlset(message: Message):
    if not await _admin_only(message.from_user.id):
        return
    val = (message.text.split()[-1] if len(message.text.split()) > 1 else "").lower() in ("on", "1", "true")
    try:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "INSERT INTO settings (key,value) VALUES ('identity_rl_enabled',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("1" if val else "0"))
            await db.commit()
    except Exception as e:
        return await send_safe(message, f"❌ {e}")
    await send_safe(message, f"✅ ایجنت هویت RL: **{'فعال' if val else 'غیرفعال'}**")


# ---------------------------------------------------------------------------
# /system — runtime health
# ---------------------------------------------------------------------------

@router.message(F.text == "/system")
async def cmd_system(message: Message):
    if not await _admin_only(message.from_user.id):
        return
    try:
        from database import raw_db
        async with raw_db() as db:
            users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
            buys = (await (await db.execute("SELECT COUNT(*) FROM purchases")).fetchone())[0]
            errs = (await (await db.execute(
                "SELECT COUNT(*) FROM app_logs WHERE level='ERROR'")).fetchone())[0]
        import os
        db_size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
    except Exception as e:
        return await send_safe(message, f"❌ {e}")
    txt = (
        f"🩺 سلامت سامانه — **{config.APP_NAME} v{config.VERSION}**\n"
        f"━━━━━━━━━━━\n"
        f"👥 کاربران: `{users}`\n"
        f"🛒 خریدها: `{buys}`\n"
        f"🧨 خطاهای ثبت‌شده: `{errs}`\n"
        f"💾 حجم دیتابیس: `{db_size/1024:.0f} KB`\n"
        f"🪪 ایجنت هویت: `{'فعال' if config.IDENTITY_RL_ENABLED else 'غیرفعال'}`"
    )
    await send_safe(message, txt)


# ---------------------------------------------------------------------------
# Panel (callback) entry
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_v2_panel")
async def admin_v2_panel(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return await cb.answer("⛔", show_alert=True)
    txt = (
        "🛠 **پنل ادمین v2**\n"
        "فهرست ابزارهای هوشمندی…\n"
        "‣ `/id <uid>` — هویت RL\n‣ `/mem2 <uid>` — حافظهٔ چندوجهی\n"
        "‣ `/logs [uid]` — لاگ‌ها\n‣ `/errmap` — نمای خطاها\n"
        "‣ `/rlset on|off` — ایجنت هویت\n‣ `/system` — سلامت"
    )
    await edit_safe(cb.message, txt, reply_markup=_kb(
        [("🧨 خطاها", "adm_v2_errs"), ("🧠 حافظه", "adm_v2_mem")],
        [("🎲 سیگنال هویت", "adm_v2_rl"), ("💳 سلامت", "adm_v2_sys")],
    ))


@router.callback_query(F.data.startswith("adm_v2_"))
async def admin_v2_quick(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return await cb.answer("⛔", show_alert=True)
    act = cb.data.split("_", 2)[2]
    try:
        from database import raw_db
        async with raw_db() as db:
            if act == "errs":
                cur = await db.execute(
                    "SELECT logger, COUNT(*) FROM app_logs WHERE level='ERROR' "
                    "GROUP BY logger ORDER BY 2 DESC LIMIT 8")
                rows = [(str(r[0]), r[1]) for r in await cur.fetchall()]
                body = "\n".join(f"`{l}` → {c}" for l, c in rows) or "(بدون خطا 🎉)"
            elif act == "mem":
                cur = await db.execute(
                    "SELECT facet, COUNT(*) FROM memory_facets GROUP BY facet ORDER BY 2 DESC")
                rows = [(str(r[0]), r[1]) for r in await cur.fetchall()]
                body = "\n".join(f"`{f}` → {c}" for f, c in rows) or "(خالی)"
            elif act == "rl":
                cur = await db.execute(
                    "SELECT label, COUNT(*) FROM rl_identity GROUP BY label ORDER BY 2 DESC")
                rows = [(str(r[0]), r[1]) for r in await cur.fetchall()]
                body = "\n".join(f"`{l}` → {c}" for l, c in rows) or "(خالی)"
            elif act == "sys":
                users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
                errs = (await (await db.execute("SELECT COUNT(*) FROM app_logs WHERE level='ERROR'")).fetchone())[0]
                body = f"👥 {users} کاربر · 🧨 {errs} خطا"
            else:
                body = ""
        await edit_safe(cb.message, f"📊 {act}:\n━━━━━━━━━\n{body}")
    except Exception as e:
        await edit_safe(cb.message, f"❌ {e}")
