"""Simple cron: daily platform report to admins + periodic pending-deposit alert."""

import asyncio
import logging
import os
from datetime import datetime, timedelta

from config import config as cfg

logger = logging.getLogger(__name__)


def _seconds_until(hour: int, minute: int = 0) -> float:
    now = datetime.now()
    target = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _daily_report(bot):
    from database import get_db
    from handlers.admin import notify_admins

    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    async with get_db() as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        users_total = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (midnight,))
        users_new = (await cur.fetchone())[0]

        cur = await db.execute(
            """SELECT COUNT(*), COALESCE(SUM(price_credits),0) FROM purchases
               WHERE purchased_at >= ?""", (midnight,))
        sales_n, sales_sum = await cur.fetchone()

        cur = await db.execute(
            "SELECT COUNT(*) FROM deposits WHERE status='pending'")
        dep_pending = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
        wd_pending = (await cur.fetchone())[0]

        cur = await db.execute(
            """SELECT COALESCE(SUM(amount),0) FROM transactions
               WHERE tx_type='deposit' AND created_at >= ?""", (midnight,))
        deposit_credits_today = (await cur.fetchone())[0]

    from hermes_engine import get_dynamic_setting
    rate = float(await get_dynamic_setting(
        "commission_rate", str(cfg.COMMISSION_RATE)))
    commission = int(sales_sum * rate)
    text = (
        f"📊 **گزارش روزانه DropAgentX**\n"
        f"📅 {datetime.now():%Y-%m-%d}\n\n"
        f"👥 کاربران: {users_total:,} (جدید امروز: +{users_new})\n"
        f"🛒 فروش امروز: {sales_n} عدد | {sales_sum:,} کردیت\n"
        f"🏦 کمیسیون امروز (~{int(rate*100)}٪): **{commission:,} کردیت**\n"
        f"💳 شارژ امروز: {deposit_credits_today:,} کردیت\n\n"
    )
    if dep_pending or wd_pending:
        text += f"⚠️ در انتظار بررسی:\n🟡 واریز: {dep_pending} | 🔵 برداشت: {wd_pending}\n(پنل: /admin)\n"

    await notify_admins(bot, text)


async def daily_loop(bot):
    """General scheduler tick: personal reminders every minute + daily report."""
    from database import due_reminders
    logger.info("Cron فعال شد — تیک هر ۶۰ ثانیه (یادآورها + گزارش روزانه)")
    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")

            # personal reminders
            for r in await due_reminders(now.hour, now.minute, today):
                try:
                    await bot.send_message(
                        r["owner_id"],
                        f"⏰ **یادآور** ({now.hour:02d}:{now.minute:02d})\n{r['text']}",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            # daily admin report at configured hour (fires once per day,
            # with catch-up if the bot was down at the exact minute)
            hour = int(await _dyn_hour())
            from database import get_setting, set_setting
            last = await get_setting("last_report_date", "")
            if now.hour >= hour and last != today:
                await set_setting("last_report_date", today)
                daily_loop._fired = today
                await _daily_report(bot)

            # daily off-site backup to admin chats
            bhour = int(await _backup_hour())
            last_b = await get_setting("last_backup_date", "")
            if now.hour >= bhour and last_b != today:
                await set_setting("last_backup_date", today)
                try:
                    await _daily_backup(bot)
                except Exception as be:
                    logger.warning("daily backup failed: %s", be)

            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("cron tick failed: %s", e)
            await asyncio.sleep(30)


async def _dyn_hour() -> int:
    from hermes_engine import get_dynamic_setting
    raw = await get_dynamic_setting("daily_report_hour",
                                    os.getenv("DAILY_REPORT_HOUR", "9"))
    try:
        return int(float(raw))
    except Exception:
        return 9


# ---------------- automatic daily backup → admin Telegram chat ----------------

async def _daily_backup(bot):
    """Snapshot the DB and send it to every admin's chat (off-site copy).
    Local retention: last 7 snapshots in data/backups/."""
    from database import snapshot_to
    from aiogram.types import FSInputFile

    if os.getenv("BACKUP_TO_TELEGRAM", "1") != "1":
        return
    db_dir = os.path.dirname(cfg.DB_PATH) or "."
    bdir = os.path.join(db_dir, "backups")
    os.makedirs(bdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    snap = os.path.join(bdir, f"marketplace-{stamp}.db")
    await snapshot_to(snap)

    # local retention: keep newest 7
    snaps = sorted(f for f in os.listdir(bdir) if f.endswith(".db"))
    for old in snaps[:-7]:
        try:
            os.remove(os.path.join(bdir, old))
        except OSError:
            pass

    size_mb = os.path.getsize(snap) / (1024 * 1024)
    ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
    caption = (f"🛡 بکاپ روزانه دیتابیس\n📅 {datetime.now():%Y-%m-%d %H:%M}\n"
               f"📦 {size_mb:.2f} MB — همین فایل کل پلتفرم است؛ نگهش دار!")
    try:
        if size_mb > 45:
            raise ValueError("file too big for Telegram (>{:.1f}MB)".format(size_mb))
        for aid in ids:
            try:
                await bot.send_document(aid, FSInputFile(snap), caption=caption)
            except Exception:
                pass
        logger.info("daily backup sent (%.2f MB) to %d admins", size_mb, len(ids))
    except Exception as e:
        logger.warning("telegram backup skipped: %s — local copy: %s", e, snap)


async def _backup_hour() -> int:
    from hermes_engine import get_dynamic_setting
    raw = await get_dynamic_setting("backup_hour", os.getenv("BACKUP_HOUR", "4"))
    try:
        return int(float(raw))
    except Exception:
        return 4


def start_cron(bot):
    return asyncio.create_task(daily_loop(bot))
