"""
DropAgentX v2.0.0 — Observability layer.

Turns the bot from "a cloud of silent `except: pass`" into a system where every
action, every failure and every money-touching operation leaves a trace that can
be searched, counted and alerted on.

Three concerns, one module:

  1. Structured logging        -> JSON lines to stdout (Railway/Docker log drain).
  2. Persisted log/audit trail -> an `app_logs` table inside the same SQLite DB
                                  that the bot already uses (zero extra infra).
  3. Failure capture           -> a global exception hook + aiogram error
                                  middleware that records any unhandled crash so
                                  it can never vanish quietly again.

Usage:
    from observability import setup_logging, db_log, audit, logged, init_log_tables

    setup_logging()                       # call once at boot (replaces basicConfig)
    await init_log_tables()               # create app_logs + index (boot, idempotent)
    await db_log("commerce", "purchase", user_id=7, data={"price": 200}, level="INFO")
    await audit(user_id=7, action="purchase", target="product:42", ok=True)
    @logged("ai", "chat")                 # decorator wraps an async handler
    async def ...(): ...
"""

import functools
import json
import logging
import os
import sys
import time
import traceback
from typing import Any, Optional

from config import config

try:
    from config import VERSION as _APP_VERSION
except Exception:
    _APP_VERSION = "?"

logger = logging.getLogger("dropagentx.observability")

# ---------------------------------------------------------------------------
# Log record -> JSON + optional DB persistence
# ---------------------------------------------------------------------------

class _JsonFilter(logging.Filter):
    """Attach a stable `service`/`version` field to every emitted record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.service = config.APP_NAME
            record.version = _APP_VERSION
        except Exception:
            record.service = "dropagentx"
            record.version = "?"
        return True


def _record_to_json(record: logging.LogRecord) -> str:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
        "level": record.levelname,
        "logger": record.name,
        "msg": record.getMessage(),
    }
    extra = getattr(record, "data", None)
    if extra:
        payload["data"] = extra
    if record.exc_info:
        payload["exc"] = "".join(traceback.format_exception(*record.exc_info))[:4000]
    return json.dumps(payload, ensure_ascii=False, default=str)


class _DbLogger:
    """Drain certain records into the `app_logs` table + SQLite (best-effort)."""

    def __init__(self):
        self._last_emit = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        if not config.LOG_TO_DB:
            return
        # throttle DB writes to avoid a log-storm bottleneck on hot paths
        if record.levelname not in ("WARNING", "ERROR", "CRITICAL") and \
                time.monotonic() - self._last_emit < 0.5:
            return
        self._last_emit = time.monotonic()
        try:
            import asyncio
            loop = _try_run_loop()
            if loop is None or loop.is_closed():
                return
            asyncio.run_coroutine_threadsafe(_db_log_coro(record), loop)
        except Exception:
            pass


def _try_run_loop():
    import asyncio
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


async def _db_log_coro(record: logging.LogRecord) -> None:
    try:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "INSERT INTO app_logs (ts, level, logger, msg, data, exc, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.created,
                    record.levelname,
                    record.name,
                    record.getMessage()[:2000],
                    json.dumps(getattr(record, "data", None), ensure_ascii=False, default=str),
                    (record.exc_info and "".join(traceback.format_exception(*record.exc_info)) or "")[:4000],
                    getattr(record, "user_id", None),
                ),
            )
            await db.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(level: Optional[str] = None) -> None:
    """Configure the root logger: JSON (or plain) to stdout + DB drain.

    Call once at boot instead of `logging.basicConfig(...)`.
    """
    level = (level or config.LOG_LEVEL or "INFO").upper()
    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    # idempotent: clear handlers we may have added on a prior setup
    for h in list(root.handlers):
        if getattr(h, "_dropagentx", False):
            root.removeHandler(h)

    if config.LOG_JSON_ENABLED:
        handler = _JsonStreamHandler(sys.stdout)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._dropagentx = True
    handler.addFilter(_JsonFilter())
    root.addHandler(handler)

    if config.LOG_TO_DB:
        dbh = _DbHandler()
        dbh._dropagentx = True
        dbh.setLevel(logging.WARNING)
        root.addHandler(dbh)

    _install_excepthook()


class _JsonStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            self.stream.write(_record_to_json(record) + "\n")
            self.flush()
        except Exception:
            pass


class _DbHandler(logging.Handler):
    def emit(self, record):
        _DbLogger().emit(record)


def _install_excepthook() -> None:
    """Route any uncaught exception (non-async) into the logger + DB."""

    def _hook(exc_type, exc, tb):
        logging.getLogger("dropagentx.uncaught").critical(
            "Unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            import asyncio
            loop = _try_run_loop()
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(_db_log_coro_manual(exc_type, exc, tb), loop)
        except Exception:
            pass

    sys.excepthook = _hook


async def _db_log_coro_manual(exc_type, exc, tb):
    try:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "INSERT INTO app_logs (ts, level, logger, msg, data, exc, user_id) "
                "VALUES (?, 'CRITICAL', 'dropagentx.uncaught', ?, ?, ?, ?)",
                (time.time(), str(exc)[:2000], None,
                 "".join(traceback.format_exception(exc_type, exc, tb))[:4000], None),
            )
            await db.commit()
    except Exception:
        pass


async def init_log_tables() -> None:
    """Create the `app_logs` table + indexes (idempotent, call at boot)."""
    try:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS app_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL DEFAULT (strftime('%s','now')),
                    level TEXT,
                    logger TEXT,
                    msg TEXT,
                    data TEXT DEFAULT '{}',
                    exc TEXT DEFAULT '',
                    user_id INTEGER,
                    created_at REAL DEFAULT (strftime('%s','now'))
                )""")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_level ON app_logs(level, ts)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_user ON app_logs(user_id, ts)")
            await db.commit()
    except Exception as e:
        logger.warning("init_log_tables skipped: %s", e)


async def db_log(logger_name: str, msg: str, *, user_id: Optional[int] = None,
                 level: str = "INFO", data: Optional[dict] = None) -> None:
    """Log a structured, persisted event (money, admin, identity, ai...)."""
    if not config.LOG_TO_DB:
        return
    try:
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "INSERT INTO app_logs (ts, level, logger, msg, data, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), level.upper(), logger_name, msg[:2000],
                 json.dumps(data or {}, ensure_ascii=False, default=str), user_id),
            )
            await db.commit()
    except Exception:
        pass


async def audit(user_id: int, action: str, target: str = "", ok: bool = True,
                data: Optional[dict] = None) -> None:
    """Human-impact audit record: 'what did this user do, did it succeed?'."""
    await db_log("audit", f"{'OK ' if ok else 'FAIL'} {action} {target}",
                 user_id=user_id, level="INFO", data=data)
    # Also reflect in the composite log line for grepping.
    logging.getLogger("dropagentx.audit").info(
        "%s %s uid=%s target=%s ok=%s",
        "OK" if ok else "FAIL", action, user_id, target, ok)


def logged(dimension: str, name: str):
    """Decorator: wrap an async handler so each completion/failure is logged.

    Example:
        @logged("commerce", "purchase")
        async def buy(...):
            ...
    """
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            user_id = None
            for a in args:
                uid = getattr(a, "from_user", None)
                if uid is not None:
                    user_id = getattr(uid, "id", None)
                    break
            start = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                await db_log(dimension, f"{name} OK", user_id=user_id,
                             level="INFO", data={"ms": int((time.monotonic() - start) * 1000)})
                return result
            except Exception as e:
                await db_log(dimension, f"{name} ERROR", user_id=user_id,
                             level="ERROR", data={"ms": int((time.monotonic() - start) * 1000),
                                                   "err": str(e)[:500]})
                logging.getLogger("dropagentx").exception("%s %s failed", dimension, name)
                raise
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# aiogram dispatcher error middleware (capture handler crashes into DB)
# ---------------------------------------------------------------------------

def build_error_middleware():
    """Return an aiogram BaseMiddleware that records handler errors.
    Register with `dp.update.outer_middleware(build_error_middleware())`.
    """
    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject

    class ErrorCapture(BaseMiddleware):
        async def __call__(self, handler, event: TelegramObject, data):
            try:
                return await handler(event, data)
            except Exception as e:
                from database import get_db
                user = data.get("event_from_user")
                uid = user.id if user else getattr(data.get("update"), "message", None) \
                    and getattr(data.get("update").message, "from_user", None) \
                    and data["update"].message.from_user.id
                try:
                    await db_log("dispatcher", f"handler error: {type(e).__name__}",
                                 user_id=uid, level="ERROR",
                                 data={"err": str(e)[:500], "exc": traceback.format_exc()[:3000]})
                except Exception:
                    pass
                logger.exception("Handler error (user=%s)", uid)
                raise
    return ErrorCapture()
