"""Professional cron scheduler — Hermes-inspired, SQLite-backed.

Schedules:
  - cron: "*/15 * * * *" style 5-field expressions
  - every: "every 2h" / "every 30m" durations
  - once: ISO timestamp for one-shot jobs
  - at: simple hour:minute daily jobs

Features:
  - SQLite-backed job store with WAL
  - Catchup window (handle missed jobs on restart)
  - Per-job config: prompt, skills, model override
  - Job categories: report, reminder, social, custom
  - Executable action types: ai_chat, shell, notify
  - Background worker runs every 30 seconds
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# =========================================================
# Cron expression parser (5-field, simplified)
# =========================================================

def _parse_cron_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a single cron field (e.g., "*/15", "0,30", "1-5", "3") into matching values."""
    result = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            result.update(range(min_val, max_val + 1))
        elif "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                start = min_val
            elif "-" in base:
                start = int(base.split("-")[0])
            else:
                start = int(base)
            result.update(range(start, max_val + 1, step))
        elif "-" in part:
            lo, hi = part.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    return sorted(result)


def cron_matches(expr: str, dt: datetime) -> bool:
    """Check if a 5-field cron expression matches a datetime."""
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    minutes = _parse_cron_field(fields[0], 0, 59)
    hours = _parse_cron_field(fields[1], 0, 23)
    days = _parse_cron_field(fields[2], 1, 31)
    months = _parse_cron_field(fields[3], 1, 12)
    weekdays = _parse_cron_field(fields[4], 0, 6)
    # Convert cron weekday (0=Sun..6=Sat) to Python weekday (0=Mon..6=Sun)
    weekdays = [(d + 6) % 7 for d in weekdays]
    return (dt.minute in minutes and dt.hour in hours and
            dt.day in days and dt.month in months and
            dt.weekday() in weekdays)


def parse_duration(expr: str) -> Optional[int]:
    """Parse '5m', '2h', '30s', '1d' into seconds."""
    m = re.match(r"^(\d+)\s*(s|m|h|d)$", expr.strip().lower())
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers.get(unit, 60)


def parse_at_time(expr: str) -> Optional[tuple[int, int]]:
    """Parse '09:00' into (hour, minute)."""
    m = re.match(r"^(\d{1,2}):(\d{1,2})$", expr.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return (h, mi)
    return None


# =========================================================
# Job types
# =========================================================

ACTION_AI_CHAT = "ai_chat"    # Send message to AI, deliver response
ACTION_SHELL = "shell"        # Execute shell command
ACTION_NOTIFY = "notify"      # Send notification message
ACTION_REPORT = "report"      # Platform analytics report

JOB_CATEGORIES = ("report", "reminder", "social", "schedule", "custom")


# =========================================================
# Job Store (SQLite)
# =========================================================

from database import get_db

async def _ensure_table():
    from database import raw_db
    async with raw_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_expr TEXT NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'notify',
                action_payload TEXT DEFAULT '',
                category TEXT DEFAULT 'custom',
                model_override TEXT DEFAULT '',
                skill_override TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                last_run_at REAL DEFAULT 0,
                next_run_at REAL DEFAULT 0,
                run_count INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            )""")
        await db.commit()


async def job_create(
    owner_id: int,
    title: str,
    schedule_type: str,
    schedule_expr: str,
    action_type: str = ACTION_NOTIFY,
    action_payload: str = "",
    category: str = "custom",
    model_override: str = "",
    skill_override: str = "",
) -> int:
    """Create a new cron job. Returns job_id."""
    await _ensure_table()
    next_run = _compute_next_run(schedule_type, schedule_expr)

    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO cron_jobs
               (owner_id, title, schedule_type, schedule_expr, action_type,
                action_payload, category, model_override, skill_override,
                next_run_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (owner_id, title[:200], schedule_type, schedule_expr,
             action_type, action_payload[:2000], category, model_override,
             skill_override, next_run),
        )
        return cursor.lastrowid


async def job_list(owner_id: int = 0, enabled_only: bool = True) -> list[dict]:
    await _ensure_table()
    q = "SELECT * FROM cron_jobs"
    params = []
    if owner_id:
        q += " WHERE owner_id = ?"
        params.append(owner_id)
    if enabled_only:
        q += " AND enabled = 1" if params else " WHERE enabled = 1"
    q += " ORDER BY next_run_at ASC"
    async with get_db() as db:
        cursor = await db.execute(q, params)
        return [dict(r) for r in await cursor.fetchall()]


async def job_get(job_id: int) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def job_update_next(job_id: int, next_run: float, run_count_inc: int = 1):
    async with get_db() as db:
        await db.execute(
            "UPDATE cron_jobs SET next_run_at = ?, last_run_at = ?, "
            "run_count = run_count + ? WHERE id = ?",
            (next_run, time.time(), run_count_inc, job_id),
        )
        await db.commit()


async def job_set_enabled(job_id: int, enabled: bool) -> bool:
    async with get_db() as db:
        c = await db.execute(
            "UPDATE cron_jobs SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, job_id))
        await db.commit()
        return c.rowcount > 0


async def job_delete(job_id: int) -> bool:
    async with get_db() as db:
        c = await db.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        await db.commit()
        return c.rowcount > 0


async def job_run_now(job_id: int) -> Optional[dict]:
    """Manually trigger a job immediately."""
    job = await job_get(job_id)
    if not job:
        return None
    result = await _execute_job(job)
    await job_update_next(job_id, _compute_next_run(job["schedule_type"], job["schedule_expr"]))
    return result


# =========================================================
# Schedule helpers
# =========================================================

def _compute_next_run(schedule_type: str, expr: str) -> float:
    """Compute the next run timestamp based on schedule type."""
    now = time.time()
    if schedule_type == "every":
        secs = parse_duration(expr)
        return now + (secs or 3600) if secs else now + 3600
    if schedule_type == "at":
        parsed = parse_at_time(expr)
        if parsed:
            target = datetime.now().replace(hour=parsed[0], minute=parsed[1], second=0)
            if target.timestamp() <= now:
                target += timedelta(days=1)
            return target.timestamp()
        return now + 3600
    if schedule_type == "once":
        try:
            target = datetime.fromisoformat(expr)
            return target.timestamp()
        except ValueError:
            return now + 3600
    if schedule_type == "cron":
        # Approximate: check every minute; next_run = next matching minute
        dt = datetime.now().replace(second=0) + timedelta(minutes=1)
        for _ in range(1440):  # max 24h lookahead
            if cron_matches(expr, dt):
                return dt.timestamp()
            dt += timedelta(minutes=1)
        return now + 3600
    return now + 3600


def _should_run(job: dict) -> bool:
    """Check if a job's next_run is due."""
    return job["next_run_at"] <= time.time() and job["enabled"]


# =========================================================
# Job execution
# =========================================================

async def _execute_job(job: dict) -> dict:
    """Execute a cron job based on its action_type."""
    action = job["action_type"]
    payload = job["action_payload"]

    if action == ACTION_NOTIFY:
        # Simple notification: payload is the message to send
        return {"action": "notify", "message": payload, "status": "ok"}

    if action == ACTION_AI_CHAT:
        # Send message to AI and return response
        from hermes_engine import hermes_chat
        from ai_agent import AI_SYSTEM_PROMPT
        model = job.get("model_override") or ""
        system = job.get("skill_override") or AI_SYSTEM_PROMPT
        response = await hermes_chat(payload or "گزارش روزانه را تهیه کن",
                                     system, user_key=job["owner_id"])
        return {"action": "ai_chat", "message": response, "status": "ok"}

    if action == ACTION_SHELL:
        from sandbox import _local_shell
        return await _local_shell(payload)

    if action == ACTION_REPORT:
        # Platform analytics
        from database import get_all_users_count, get_total_products, get_total_sales
        users = await get_all_users_count()
        prods = await get_total_products()
        sales = await get_total_sales()
        return {
            "action": "report",
            "message": f"📊 کاربران: {users} | محصولات: {prods} | فروش: {sales}",
            "status": "ok",
        }

    return {"action": action, "message": f"نوع ناشناخته: {action}", "status": "error"}


# =========================================================
# Background worker
# =========================================================

async def cron_worker(bot, tick_seconds: int = 30):
    """Background worker: checks due jobs every tick_seconds."""
    await _ensure_table()
    logger.info("Cron worker started (tick=%ds)", tick_seconds)

    while True:
        try:
            jobs = await job_list(enabled_only=True)
            now = time.time()
            for job in jobs:
                if not _should_run(job):
                    continue

                # Mark as running (prevent re-entry)
                await job_update_next(job["id"], now + 300, 0)  # hold for 5min

                try:
                    result = await _execute_job(job)
                    await job_update_next(
                        job["id"],
                        _compute_next_run(job["schedule_type"], job["schedule_expr"]),
                    )

                    # Deliver result to owner via Telegram
                    if result.get("message") and job["owner_id"]:
                        try:
                            await bot.send_message(
                                job["owner_id"],
                                f"⏰ **{job['title']}**\n\n{result['message'][:2000]}",
                                parse_mode="Markdown",
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.error("Cron job %d failed: %s", job["id"], e)
                    # Reset schedule on failure
                    await job_update_next(
                        job["id"],
                        _compute_next_run(job["schedule_type"], job["schedule_expr"]),
                    )

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("Cron worker tick error: %s", e)

        await asyncio.sleep(tick_seconds)
