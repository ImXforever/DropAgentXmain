import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest

from config import config
from database import init_db
from handlers import all_routers
from hermes_engine import resolve_mode
from observability import setup_logging, init_log_tables, build_error_middleware

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def _file_handler():
    """Daily rotating file logs — 30 days retention (data/logs/)."""
    from logging.handlers import TimedRotatingFileHandler
    os.makedirs(os.path.join("data", "logs"), exist_ok=True)
    fh = TimedRotatingFileHandler(
        filename=os.path.join("data", "logs", "bot.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    return fh


# v2.0.0: replace the plain basicConfig with the structured observability layer
# (JSON to stdout for Railway, WARNING+ drained into the `app_logs` table, plus a
# global exception hook). The daily rotating file handler is kept as a local belt.
setup_logging()
logging.getLogger().addHandler(_file_handler())
logger = logging.getLogger(__name__)




async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN تنظیم نشده! فایل .env را بساز (از روی .env.example).")
        return

    mode = resolve_mode()
    logger.info("AI engine mode: %s", mode)
    if mode == "api" and not config.AI_API_KEY:
        logger.warning(
            "هیچ بک‌اند AI فعال نیست: نه hermes CLI نصب است و نه HERMES_GATEWAY_URL/AI_API_KEY تنظیم شده. "
            "قابلیت‌های AI پاسخ خطا می‌دهند."
        )

    await init_db()
    logger.info("Database initialized at %s", config.DB_PATH)

    # v2.0.0: bring up the observability + v2 feature tables (idempotent).
    await init_log_tables()
    try:
        import memory2
        await memory2.init_tables()
        import identity_rl
        await identity_rl.init_tables()
    except Exception as e:
        logger.warning("v2 feature tables skipped: %s", e)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )
    dp = Dispatcher()

    # v2.0.0: capture handler exceptions into the SQLite log trail.
    try:
        dp.update.outer_middleware(build_error_middleware())
    except Exception as e:
        logger.warning("error middleware skipped: %s", e)

    for router in all_routers:
        dp.include_router(router)

    @dp.errors()
    async def on_handler_error(event, exception: Exception | None = None, **kwargs):
        exc = exception or getattr(event, "exception", None) or kwargs.get("exception")
        if isinstance(exc, TelegramNetworkError):
            logger.warning("قطعی لحظه‌ای شبکه تلگرام — بات به کارش ادامه می‌دهد.")
            return True
        if isinstance(exc, TelegramBadRequest):
            logger.warning("Telegram bad request (نادیده گرفته شد): %s", str(exc)[:120])
            return True
        try:
            uid = getattr(getattr(event, "update", event), "update_id", "?")
        except Exception:
            uid = "?"
        logger.error("Handler error (update=%s): %s", uid, exc, exc_info=exc or True)
        return True

    logger.info("Starting DropAgentX Bot...")
    from cron_jobs import start_cron
    cron_task = start_cron(bot)

    # --- optional services (all degrade gracefully) ---
    extra_tasks = []
    try:
        from treasury_worker import run_treasury
        extra_tasks.append(asyncio.create_task(run_treasury(bot)))
    except Exception as e:
        logger.warning("treasury worker disabled: %s", e)

    if os.getenv("A2A_PORT"):
        try:
            from a2a_server import start_server
            extra_tasks.append(asyncio.create_task(start_server()))
            logger.info("A2A/API server task queued on :%s", os.getenv("A2A_PORT"))
        except Exception as e:
            logger.warning("A2A disabled: %s", e)

    # v3: agent discovery + MCP bridge (agent.json / .well-known / mcp). These run
    # as lightweight Starlette servers on their own ports, exposed via the gateway.
    if os.getenv("A2A_ENABLED", "1") == "1":
        try:
            from a2a_v2 import build_app as _a2a_app
            import uvicorn as _uv
            _port = int(os.getenv("A2A_V2_PORT", "9001") or 9001)
            _cfg = _uv.Config(_a2a_app(), host="0.0.0.0", port=_port, log_level="warning")
            extra_tasks.append(asyncio.create_task(_uv.Server(_cfg).serve()))
            logger.info("A2A v2 (agent card + /a2a) on :%s", _port)
        except Exception as e:
            logger.warning("A2A v2 disabled: %s", e)
    if os.getenv("A2A_ENABLED", "1") == "1":
        try:
            from mcp_bridge import build_app as _mcp_app
            import uvicorn as _uv
            _port = int(os.getenv("MCP_PORT", "9020") or 9020)
            _cfg = _uv.Config(_mcp_app(), host="0.0.0.0", port=_port, log_level="warning")
            extra_tasks.append(asyncio.create_task(_uv.Server(_cfg).serve()))
            logger.info("MCP bridge on :%s", _port)
        except Exception as e:
            logger.warning("MCP bridge disabled: %s", e)

    if os.getenv("WEB_PORT"):
        try:
            from web_admin import start_server
            extra_tasks.append(asyncio.create_task(start_server(bot)))
            logger.info("Web dashboard task queued on :%s (admin: /admin)", os.getenv("WEB_PORT"))
        except Exception as e:
            logger.warning("Web dashboard disabled: %s", e)

    async def _init_mcp():
        try:
            from mcp_lite import start_servers, mcp_tool_specs
            srv = await start_servers()
            n = sum(len(s["tools"]) for s in srv.values())
            if n:
                logger.info("MCP: %d tools از %d سرور", n, len(srv))
        except Exception as e:
            logger.warning("MCP init failed: %s", e)
    extra_tasks.append(asyncio.create_task(_init_mcp()))

    async def _a2a_text(text, uid):
        from hermes_engine import hermes_chat
        return await hermes_chat(text, None, user_key=uid)

    try:
        from platforms import maybe_start_discord
        extra_tasks.append(asyncio.create_task(
            maybe_start_discord(lambda text, uid: _a2a_text(text, uid))))
    except Exception as e:
        logger.warning("discord scaffold error: %s", e)

    delay = 5
    while True:
        try:
            await dp.start_polling(bot)
            break
        except TelegramNetworkError as e:
            logger.warning("شبکه قطع است (%s) — تلاش مجدد در %d ثانیه…", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        except Exception:
            await bot.session.close()
            raise
        else:
            break
    if cron_task:
        cron_task.cancel()
    for tk in extra_tasks:
        tk.cancel()
    try:
        from mcp_lite import stop_servers
        await stop_servers()
    except Exception:
        pass
    await bot.session.close()
    from database import close_pool
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
