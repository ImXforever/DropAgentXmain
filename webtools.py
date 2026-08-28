"""Web tools: DuckDuckGo search (no API key) + webpage reader.

Playwright is optional — when installed it renders JS pages; otherwise a
fast httpx + regex extractor is used.
"""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from hermes_engine import get_dynamic_setting

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
TIMEOUT = 20


# ---------------- URL safety (hermes-agent url_safety style) -------------

def _ip_is_dangerous(ip: str) -> bool:
    """Private/loopback/link-local/reserved targets can reach intranet or
    cloud metadata endpoints — never fetch them."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (a.is_private or a.is_loopback or a.is_link_local
            or a.is_reserved or a.is_multicast or a.is_unspecified)


async def url_guard(url: str) -> str | None:
    """Return a rejection reason for dangerous URLs, else None."""
    try:
        p = urlparse(url)
    except Exception:
        return "URL قابل تجزیه نیست"
    if p.scheme not in ("http", "https"):
        return f"اسکیم «{p.scheme or '?'}» مجاز نیست — فقط http/https"
    host = (p.hostname or "").strip().lower().rstrip(".")
    if not host:
        return "هاست نامعتبر است"
    if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
        return "دسترسی به هاست‌های داخلی مسدود است"
    if _ip_is_dangerous(host):  # literal IPs like 127.0.0.1 / 169.254.169.254
        return "آدرس‌های لوکال/خصوصی مسدود هستند"
    try:  # DNS must not resolve into private space either
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as e:
        return f"هاست پیدا نشد: {e}"
    except Exception as e:
        return f"خطای DNS: {e}"
    for info in infos:
        if info[4] and _ip_is_dangerous(str(info[4][0])):
            return "این هاست به آدرس داخلی resolve می‌شود (مسیر SSRF بسته شد)"
    return None


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo Lite scraping → [{title, url, snippet}]"""
    query = (query or "").strip()
    if not query:
        return []
    max_results = max(1, min(max_results, 8))
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA},
                                    follow_redirects=True) as c:
            r = await c.get("https://lite.duckduckgo.com/lite/",
                            params={"q": query})
            r.raise_for_status()
            html = r.text
    except Exception as e:
        return [{"error": f"search failed: {e}"}]

    results = []
    # lite layout: result links <a rel="nofollow" href="URL" class='result-link'>TITLE</a>
    for m in re.finditer(
        r'<a[^>]+href="(http[^"]+)"[^>]*class=[\'"]result-link[\'"][^>]*>(.*?)</a>',
        html, re.S):
        url = m.group(1)
        title = re.sub(r"<.*?>", "", m.group(2)).strip()
        # snippet lives in the next result-snippet cell
        tail = html[m.end(): m.end() + 900]
        sm = re.search(r'class=[\'"]result-snippet[\'"]>(.*?)</t', tail, re.S)
        snippet = re.sub(r"<.*?>", "", sm.group(1)).strip()[:220] if sm else ""
        if url.startswith("//"):
            url = "https:" + url
        results.append({"title": title[:120], "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


_TAG_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_TAG_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n{3,}|[ \t]{2,}")


def _html_to_text(html: str) -> str:
    html = _TAG_SCRIPT.sub(" ", html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", html, flags=re.I)
    text = _TAG_ANY.sub(" ", html)
    import html as _h
    text = _h.unescape(text)
    return _WS.sub("\n", text).strip()


async def read_webpage(url: str, max_chars: int = 3500) -> str:
    """Read a page as clean text. Uses Playwright when available."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "⚠️ URL نامعتبر."
    reason = await url_guard(url)
    if reason:
        return f"⛔ {reason}"
    if (await get_dynamic_setting("browser_enabled", "1")) == "1":
        try:
            from playwright.async_api import async_playwright  # noqa
            return await _read_playwright(url, max_chars)
        except ImportError:
            pass
        except Exception:
            pass  # fall back to plain fetch
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA},
                                     follow_redirects=False) as c:
            r = await c.get(url, follow_redirects=False)
            r.raise_for_status()
            final = await url_guard(str(r.url))  # redirects must stay safe too
            if final:
                return f"⛔ {final}"
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return f"📄 محتوای غیر HTML ({ctype.split(';')[0]}) — {len(r.content)} بایت."
            text = _html_to_text(r.text)
            return text[:max_chars] or "(صفحه خالی)"
    except Exception as e:
        return f"⚠️ خطا در خواندن صفحه: {e}"


async def _read_playwright(url: str, max_chars: int) -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=UA)
        try:
            await page.goto(url, timeout=25000, wait_until="domcontentloaded")
            final = await url_guard(page.url)  # JS/redirect may have moved us
            if final:
                return f"⛔ {final}"
            text = await page.inner_text("body")
        finally:
            await browser.close()
    return text.strip()[:max_chars]
