#!/usr/bin/env python3
"""0.5.1 — لانچر واحد: هم Railway هم VPS با همان دستور `python run.py`

- Railway: PORT خودکار تزریق می‌شود → به WEB_PORT نگاشت می‌شود (وب+بات در یک سرویس)
- VPS: WEB_PORT در systemd/بی‌خیال PORT → همان رفتار
- فقط بات (بدون وب): WEB_PORT را خالی بگذار و PORT را نزن
"""
import os
import sys


def normalize_env() -> None:
    """Railway PORT → WEB_PORT (bot.py وقتی WEB_PORT هست وب را in-process بالا می‌آورد)."""
    port = os.getenv("PORT", "").strip()
    if port and not os.getenv("WEB_PORT", "").strip():
        os.environ["WEB_PORT"] = port
    # دیتابیس/آپلود روی مسیر volume اگر تعریف شده باشد (Railway Volume یا VPS)
    if os.getenv("DATA_DIR", "").strip():
        data = os.environ["DATA_DIR"].rstrip("/")
        os.environ.setdefault("DB_PATH", f"{data}/marketplace.db")
        os.environ.setdefault("UPLOAD_DIR", f"{data}/uploads")
        os.environ.setdefault("BACKUP_DIR", f"{data}/backups")


def detect_mode() -> str:
    if os.getenv("RAILWAY_ENVIRONMENT", "").strip():
        return "railway"
    mode = os.getenv("DAX_MODE", "").strip().lower()
    return mode if mode in ("railway", "vps", "local") else "vps"


def banner(mode: str) -> None:
    try:
        from config import VERSION
    except Exception:
        VERSION = "0.5.1"
    web = os.getenv("WEB_PORT", "")
    print("=" * 56)
    print(f"  DropAgentX v{VERSION}  ·  mode={mode}")
    print(f"  web: {'ON :' + web if web else 'off (فقط بات)'}  ·  db: {os.getenv('DB_PATH', 'data/marketplace.db')}")
    print("=" * 56)


if __name__ == "__main__":
    normalize_env()
    mode = detect_mode()
    banner(mode)
    import asyncio
    import bot
    asyncio.run(bot.main())
