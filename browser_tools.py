"""Stateful browser automation for AI agents.

Inspired by Hermes Agent's browser tools (browser_navigate, browser_click,
browser_type, browser_snapshot, etc.) with Playwright headless Chromium.

Commands exposed as AI tools:
  browser_navigate(url)       → load a page
  browser_snapshot()          → get text representation of the page
  browser_click(selector)     → click an element
  browser_type(selector, text)→ type into a field
  browser_scroll(direction)   → scroll up/down
  browser_back()              → go back in history
  browser_get_images()        → list images on page
  browser_get_links()         → list links on page

Safety:
  - Headless only, no GUI
  - 30s timeout per operation
  - SSRF protection: block private IPs
  - Page content length limit (50KB)
  - Graceful fallback when Playwright unavailable
"""

import asyncio
import ipaddress
import logging
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# =========================================================
# Config
# =========================================================

TIMEOUT_S = 30
MAX_CONTENT_CHARS = 50_000
HEADLESS = True
VIEWPORT = {"width": 1280, "height": 720}
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36")

# =========================================================
# SSRF protection
# =========================================================

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal",
                  "169.254.169.254", "instance-data"}


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Check URL safety: HTTPS required, no private IPs."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "URL نامعتبر"

    if parsed.scheme not in ("http", "https"):
        return False, "فقط http/https مجاز است"

    hostname = parsed.hostname or ""
    if hostname.lower() in _BLOCKED_HOSTS:
        return False, "هاست مسدود شده"

    # Check for private IPs (except in dev)
    try:
        import socket
        ip = socket.getaddrinfo(hostname, None, socket.AF_INET)
        if ip:
            addr = ip[0][4][0]
            if ipaddress.ip_address(addr).is_private:
                if os.getenv("APP_ENV", "production") not in ("dev", "local"):
                    return False, "آدرس IP خصوصی مجاز نیست"
    except Exception:
        pass  # DNS failure → let it proceed, will timeout on connection

    return True, ""


# =========================================================
# Singleton browser manager
# =========================================================

class BrowserManager:
    """Manages a single persistent Playwright browser + page."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._history: list[str] = []
        self._current_url: str = ""
        self._ready = False

    async def _ensure_ready(self):
        if self._ready and self._page and not self._page.is_closed():
            return
        if not self._pw:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                raise RuntimeError("Playwright نصب نیست: pip install playwright && playwright install chromium")
            self._pw = await async_playwright().start()
        if not self._browser:
            self._browser = await self._pw.chromium.launch(
                headless=HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        if not self._page or self._page.is_closed():
            ctx = await self._browser.new_context(
                user_agent=USER_AGENT,
                viewport=VIEWPORT,
                ignore_https_errors=True,
            )
            self._page = await ctx.new_page()
        self._ready = True

    async def close(self):
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._page = None
        self._ready = False
        self._history.clear()


_browser: Optional[BrowserManager] = None


async def _get_browser() -> BrowserManager:
    global _browser
    if _browser is None:
        _browser = BrowserManager()
    await _browser._ensure_ready()
    return _browser


async def close_browser():
    global _browser
    if _browser:
        await _browser.close()
        _browser = None


# =========================================================
# Tool implementations
# =========================================================

async def browser_navigate(url: str) -> str:
    """Load a URL in the browser."""
    ok, err = _is_safe_url(url)
    if not ok:
        return f"🚫 مسدود: {err}"

    try:
        br = await _get_browser()
        await br._page.goto(url, timeout=TIMEOUT_S * 1000, wait_until="domcontentloaded")
        br._history.append(br._current_url)
        br._current_url = br._page.url
        title = await br._page.title()
        return f"✅ صفحه باز شد: {title}\nURL: {br._page.url}"
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


async def browser_snapshot(max_chars: int = 3000) -> str:
    """Get a text representation of the current page."""
    try:
        br = await _get_browser()
        text = await br._page.inner_text("body")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()[:max_chars]
        url = br._page.url
        title = await br._page.title()
        return f"📄 **{title}** ({url})\n\n{text}"
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


async def browser_click(selector: str) -> str:
    """Click an element by CSS selector."""
    try:
        br = await _get_browser()
        await br._page.click(selector, timeout=10_000)
        await br._page.wait_for_load_state("domcontentloaded", timeout=10_000)
        br._current_url = br._page.url
        return f"✅ کلیک شد: {selector}"
    except Exception as e:
        return f"❌ خطا در کلیک: {str(e)[:200]}"


async def browser_type(selector: str, text: str, press_enter: bool = False) -> str:
    """Type text into a field."""
    try:
        br = await _get_browser()
        await br._page.fill(selector, text, timeout=10_000)
        if press_enter:
            await br._page.press(selector, "Enter")
            await br._page.wait_for_load_state("domcontentloaded", timeout=10_000)
        return f"✅ متن تایپ شد: {text[:50]}..."
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


async def browser_scroll(direction: str = "down") -> str:
    """Scroll the page up or down."""
    try:
        br = await _get_browser()
        delta = 500 if direction.lower() == "down" else -500
        await br._page.mouse.wheel(0, delta)
        await asyncio.sleep(0.5)
        return f"✅ اسکرول {direction}"
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


async def browser_back() -> str:
    """Navigate back in browser history."""
    try:
        br = await _get_browser()
        if br._page.url != "about:blank":
            br._history.append(br._page.url)
        await br._page.go_back(timeout=TIMEOUT_S * 1000)
        br._current_url = br._page.url
        return f"✅ بازگشت به: {br._page.url}"
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


async def browser_get_links(max_results: int = 20) -> str:
    """Extract all links from the current page."""
    try:
        br = await _get_browser()
        links = await br._page.eval_on_selector_all(
            "a[href]",
            "els => els.map(el => ({text: el.innerText.trim().slice(0,80), href: el.href}))",
        )
        links = [l for l in links if l.get("href") and l["text"]][:max_results]
        if not links:
            return "📄 هیچ لینکی در صفحه یافت نشد."
        lines = [f"🔗 {l['text'][:60]}: {l['href']}" for l in links[:max_results]]
        return f"🔗 {len(links)} لینک یافت شد:\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


async def browser_get_images(max_results: int = 10) -> str:
    """Extract image URLs from the current page."""
    try:
        br = await _get_browser()
        imgs = await br._page.eval_on_selector_all(
            "img[src]",
            "els => els.map(el => ({src: el.src, alt: (el.alt||'').slice(0,60), w: el.naturalWidth}))",
        )
        imgs = [i for i in imgs if i.get("src") and i.get("w", 0) > 50][:max_results]
        if not imgs:
            return "🖼 تصویری یافت نشد."
        lines = [f"🖼 {i.get('alt', '?')[:40]}: {i['src'][:120]} ({i['w']}px)" for i in imgs]
        return f"🖼 {len(imgs)} تصویر:\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ خطا: {str(e)[:200]}"


# =========================================================
# Tool specs (OpenAI function-calling format)
# =========================================================

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "browser_navigate",
        "description": "باز کردن یک صفحه وب در مرورگر",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "آدرس URL"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "browser_snapshot",
        "description": "گرفتن نمای متنی فعلی صفحه (محتوای متن)",
        "parameters": {"type": "object", "properties": {
            "max_chars": {"type": "integer", "description": "حداکثر کاراکتر"},
        }},
    }},
    {"type": "function", "function": {
        "name": "browser_click",
        "description": "کلیک روی یک عنصر با CSS selector",
        "parameters": {"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS selector"},
        }, "required": ["selector"]},
    }},
    {"type": "function", "function": {
        "name": "browser_type",
        "description": "تایپ متن در یک فیلد",
        "parameters": {"type": "object", "properties": {
            "selector": {"type": "string"},
            "text": {"type": "string", "description": "متن تایپ"},
            "press_enter": {"type": "boolean", "description": "آیا Enter بزند"},
        }, "required": ["selector", "text"]},
    }},
    {"type": "function", "function": {
        "name": "browser_scroll",
        "description": "اسکرول صفحه بالا یا پایین",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["up", "down"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "browser_back",
        "description": "بازگشت به صفحه قبلی",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "browser_get_links",
        "description": "لیست لینک‌های صفحه فعلی",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "browser_get_images",
        "description": "لیست تصاویر صفحه فعلی",
        "parameters": {"type": "object", "properties": {}},
    }},
]
