import os
import re
import json
import random
import shutil
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class HermesEngineError(Exception):
    pass


# ---------------- secret redaction (hermes-agent style) ----------------

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),                       # OpenAI-style keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),                  # GitHub tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),                # GitHub fine-grained
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),                # Slack tokens
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{16,}"),         # auth headers
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),             # Telegram bot tokens
    re.compile(r"0x[a-fA-F0-9]{64}\b"),                         # raw private keys
    re.compile(r"(?i)\b(api[_-]?key|secret|password)\s*[=:]\s*\S{8,}"),
)


def redact_secrets(text: str) -> str:
    """Mask credential-looking substrings before logging or echoing to users."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(0)[:4] + "«REDACTED»", out)
    return out


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def resolve_mode() -> str:
    mode = _env("HERMES_MODE", "auto").strip().lower()
    if mode in ("cli", "http", "api"):
        return mode
    cmd = _env("HERMES_CMD", "hermes").strip().split()[0]
    if shutil.which(cmd):
        return "cli"
    if _env("HERMES_GATEWAY_URL", "").strip():
        return "http"
    return "api"


_SEM: asyncio.Semaphore | None = None
_DYN_CACHE: dict = {}


def _semaphore() -> asyncio.Semaphore:
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(int(_env("HERMES_MAX_CONCURRENT", "2") or "2"))
    return _SEM


async def get_dynamic_setting(key: str, fallback: str = "") -> str:
    """Admin-editable runtime override stored in DB; 30s cache."""
    import time as _t
    hit = _DYN_CACHE.get(key)
    if hit and (_t.time() - hit[1]) < 30:
        return hit[0]
    try:
        from database import get_setting
        val = await get_setting(key)
    except Exception:
        val = None
    if not val:
        val = fallback
    _DYN_CACHE[key] = (val, _t.time())
    return val


def invalidate_dyn_cache():
    _DYN_CACHE.clear()


async def get_ai_config() -> dict:
    """AI backend config. Accepts both naming conventions:
    AI_API_KEY/AI_BASE_URL/AI_MODEL  or  OPENAI_API_KEY/OPENAI_BASE_URL."""
    api_key = await get_dynamic_setting(
        "ai_api_key", _env("AI_API_KEY", "") or _env("OPENAI_API_KEY", ""))
    base_url = await get_dynamic_setting(
        "ai_base_url",
        _env("AI_BASE_URL", "") or _env("OPENAI_BASE_URL", "")
        or "https://openrouter.ai/api/v1")
    model = await get_dynamic_setting(
        "ai_model", _env("AI_MODEL", "openai/gpt-4o-mini"))
    return {"api_key": api_key, "base_url": base_url, "model": model}


_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 522, 524}


async def _post_chat(payload: dict, timeout: float = 90.0,
                     max_attempts: int = 3) -> str:
    """Shared chat/completions POST with exponential backoff + jitter
    (hermes-agent tenacity style) on 429/5xx and network errors."""
    conf = await get_ai_config()
    api_key, base_url = conf["api_key"], conf["base_url"]
    if not api_key:
        raise HermesEngineError("AI_API_KEY تنظیم نشده")
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
            if r.status_code != 200:
                # Never fail invisible: Railway only shows what we log here.
                detail = redact_secrets(r.text[:500]) if r.text else "no detail"
                if r.status_code in _RETRYABLE_STATUS and attempt < max_attempts:
                    wait = min(2 ** attempt, 8) + random.uniform(0, 0.5)
                    logger.warning(
                        "AI HTTP %s (model=%s) — تلاش مجدد %d/%d پس از %.1fs: %s",
                        r.status_code, payload.get("model"), attempt,
                        max_attempts - 1, wait, detail[:160])
                    await asyncio.sleep(wait)
                    continue
                logger.error("AI HTTP %s (model=%s, base=%s): %s",
                             r.status_code, payload.get("model"), base_url,
                             detail)
                raise HermesEngineError(
                    f"سرویس AI خطای HTTP {r.status_code} داد: {detail[:200]}")
            return r.text
        except httpx.HTTPStatusError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_exc = e
            if attempt < max_attempts:
                wait = min(2 ** attempt, 8) + random.uniform(0, 0.5)
                logger.warning("AI شبکه (%s) — تلاش مجدد %d/%d",
                               type(e).__name__, attempt, max_attempts - 1)
                await asyncio.sleep(wait)
                continue
            raise HermesEngineError(
                f"ارتباط با سرویس AI برقرار نشد: {type(e).__name__}") from e
    raise last_exc or HermesEngineError("فراخوانی AI ناموفق بود")


async def _run_cli(message: str, session_id: str | None) -> tuple[str, str | None]:
    cmd = _env("HERMES_CMD", "hermes").strip()
    args = cmd.split()
    profile = _env("HERMES_PROFILE", "").strip()
    if profile:
        args += ["-p", profile]
    args += ["chat", "--quiet", "--no-restore-cwd"]
    if session_id:
        args += ["--resume", session_id]
    args += ["--query-file", "-"]

    timeout = float(_env("HERMES_TIMEOUT", "180") or "180")
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise HermesEngineError(f"Hermes executable not found: {cmd!r}") from e

    try:
        out, err = await asyncio.wait_for(
            proc.communicate(message.encode("utf-8")), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HermesEngineError(f"Hermes timed out after {timeout:.0f}s")

    response = out.decode("utf-8", "replace").strip()
    m = re.search(r"session_id:\s*(\S+)", err.decode("utf-8", "replace"))
    new_sid = m.group(1) if m else None
    if proc.returncode != 0 and not response:
        tail = err.decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else f"exit code {proc.returncode}"
        raise HermesEngineError(f"Hermes failed: {detail}")
    if not response:
        raise HermesEngineError("Hermes returned an empty response")
    return response, new_sid


async def _run_http(message: str, user_key: int, session_id: str | None) -> tuple[str, str | None]:
    url = _env("HERMES_GATEWAY_URL", "").strip()
    if not url:
        raise HermesEngineError("HERMES_GATEWAY_URL is not set")
    timeout = float(_env("HERMES_TIMEOUT", "180") or "180")
    headers = {}
    token = _env("HERMES_GATEWAY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            url,
            json={"message": message, "user_id": user_key, "session_id": session_id},
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
    response = (data.get("response") or data.get("final_response") or "").strip()
    if not response:
        raise HermesEngineError("Hermes gateway returned an empty response")
    return response, data.get("session_id")


def _extract_json_objects(text: str) -> list[dict]:
    """Pull every JSON object out of a possibly-malformed SSE/body stream."""
    dec = json.JSONDecoder()
    objs: list[dict] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \r\n\t":
            i += 1
            continue
        if text.startswith("data:", i):
            j = i + 5
            while j < n and text[j] in " \t":
                j += 1
            if text.startswith("[DONE]", j):
                break
            i = j
            continue
        if ch == "{":
            try:
                obj, end = dec.raw_decode(text, i)
                objs.append(obj)
                i = end
                continue
            except json.JSONDecodeError:
                pass
        i += 1
    return objs


def _content_from_payload(payload: dict) -> str:
    try:
        msg = (payload.get("choices") or [{}])[0].get("message") or {}
    except AttributeError:
        return ""
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    if not content or not str(content).strip():
        # reasoning models may leave content null and fill .reasoning instead
        content = msg.get("reasoning") or ""
    return str(content or "").strip()


async def llm_call_raw(
    messages: list[dict],
    model_override: str = "",
    max_tokens: int = 800,
    temperature: float = 0.6,
    tools: list | None = None,
) -> dict:
    """Single call returning the raw assistant message dict (may contain tool_calls)."""
    conf = await get_ai_config()
    model = (model_override or "").strip() or conf["model"]
    payload = {
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    body = await _post_chat(payload)

    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        objs = [o for o in _extract_json_objects(body) if isinstance(o, dict)]
        data = next((o for o in objs if o.get("choices")), None) or (objs[0] if objs else None)
    if not isinstance(data, dict):
        raise HermesEngineError("پاسخ نامعتبر از سرویس AI")
    try:
        return (data.get("choices") or [{}])[0].get("message") or {}
    except AttributeError as e:
        raise HermesEngineError("ساختار پاسخ نامعتبر") from e


async def chat_with_tools(
    messages: list[dict],
    tool_specs: list,
    executor,
    max_iter: int = 3,
) -> tuple[str, list[str]]:
    """Agentic tool loop. executor(name, args_dict) must be awaited.
    Returns (final_text, tools_used)."""
    convo = list(messages)
    used: list[str] = []
    for _ in range(max_iter):
        msg = await llm_call_raw(convo, max_tokens=1200, temperature=0.5, tools=tool_specs)
        calls = msg.get("tool_calls") or []
        if not calls:
            content = _content_from_payload({"choices": [{"message": msg}]})
            return (content or "").strip(), used
        convo.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": calls,
        })
        for tc in calls:
            fn = (tc.get("function") or {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await executor(name, args)
            used.append(name)
            # v2: Token Saver — compress noisy tool output before it costs tokens.
            try:
                from token_saver import maybe_compress_tool_output
                rendered = maybe_compress_tool_output(str(result))
            except Exception:
                rendered = str(result)
            convo.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": rendered[:2000],
            })
    # exhausted iterations → ask for plain synthesis
    convo.append({"role": "user", "content":
                  "جمع‌بندی نهایی را بدون ابزار جدید بنویس."})
    final_msg = await llm_call_raw(convo, max_tokens=900, temperature=0.6)
    return (_content_from_payload({"choices": [{"message": final_msg}]}) or "").strip(), used


async def llm_call(
    messages: list[dict],
    model_override: str = "",
    max_tokens: int = 800,
    temperature: float = 0.6,
) -> str:
    """Generic single-shot call used by Fleet roles; supports per-role model."""
    conf = await get_ai_config()
    model = (model_override or "").strip() or conf["model"]
    payload = {
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
        "stream": False,
    }
    body = await _post_chat(payload)

    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        objs = [o for o in _extract_json_objects(body) if isinstance(o, dict)]
        data = next((o for o in objs if o.get("choices")), None) or (objs[0] if objs else None)
    content = _content_from_payload(data or {})
    if not content:
        raise HermesEngineError("پاسخ خالی از مدل")
    return content


async def _run_api(messages: list[dict]) -> str:
    conf = await get_ai_config()
    if not conf["api_key"]:
        raise HermesEngineError("هیچ بک‌اندی فعال نیست: HERMES نصب نیست و AI_API_KEY تنظیم نشده")
    payload = {
        "model": conf["model"],
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.7,
        "stream": False,
    }
    body = await _post_chat(payload, timeout=120.0)

    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("non-dict body")
    except (json.JSONDecodeError, ValueError):
        objs = [o for o in _extract_json_objects(body) if isinstance(o, dict)]
        data = next((o for o in objs if o.get("choices")), None) or (objs[0] if objs else None)

    if not isinstance(data, dict):
        raise HermesEngineError("پاسخ نامعتبر از سرویس AI")

    content = _content_from_payload(data)
    if not content:
        raise HermesEngineError("مدل پاسخ خالی برگرداند")
    return content


async def chat_custom(
    message: str,
    system_prompt: str | None,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """User's own OpenAI-compatible endpoint (Custom Bot, lifetime unlock)."""
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": message})
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": msgs, "max_tokens": 2000,
                      "temperature": 0.7, "stream": False},
            )
            r.raise_for_status()
            body = r.text
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code in (401, 403):
            return "⚠️ کلید Custom Bot نامعتبره (401/403)."
        return f"⚠️ خطای سرویس شخصی تو (HTTP {code}). تنظیمات را بررسی کن."
    except httpx.HTTPError as e:
        logger.warning("custom bot network error: %s", e)
        return "⚠️ اتصال به Endpoint شخصی‌ات برقرار نشد."

    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        objs = [o for o in _extract_json_objects(body) if isinstance(o, dict)]
        data = next((o for o in objs if o.get("choices")), None) or (objs[0] if objs else None)

    content = _content_from_payload(data) if isinstance(data, dict) else ""
    if not content:
        return "⚠️ Custom Bot پاسخ خالی داد — مدل/URL را چک کن."
    return content


def _delta_from_chunk(chunk: dict) -> str:
    try:
        d = (chunk.get("choices") or [{}])[0].get("delta") or {}
    except AttributeError:
        return ""
    piece = d.get("content")
    if isinstance(piece, str):
        return piece
    return ""


async def _run_api_stream(messages: list[dict], on_delta) -> str | None:
    """True SSE streaming; calls on_delta(accumulated_text) as chunks arrive.
    Returns final text, or None if the endpoint doesn't stream properly."""
    conf = await get_ai_config()
    api_key = conf["api_key"]
    base_url = conf["base_url"]
    model = conf["model"]
    if not api_key:
        raise HermesEngineError("هیچ بک‌اندی فعال نیست: HERMES نصب نیست و AI_API_KEY تنظیم نشده")

    buf = []
    got_any = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0)) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "max_tokens": 2000,
                      "temperature": 0.7, "stream": True},
            ) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode("utf-8", "replace")
                    detail = redact_secrets(body[:500]) if body.strip() else "no detail"
                    # Logged loudly (this used to be invisible on Railway), then
                    # handed to the non-streaming fallback, which owns the raise
                    # so the caller can refund the reserved credit.
                    logger.error("AI stream HTTP %s (model=%s, base=%s) → fallback: %s",
                                 r.status_code, model, base_url, detail)
                    return None
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        # tolerate malformed bodies that mix plain JSON objects
                        if line.startswith("{"):
                            try:
                                obj = json.loads(line)
                                piece = _content_from_payload(obj) if obj.get("choices") and obj[0]["choices"][0].get("message") else _delta_from_chunk(obj)
                                if piece:
                                    got_any = True
                                    buf.append(piece)
                                    await on_delta("".join(buf))
                            except Exception:
                                pass
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    piece = _delta_from_chunk(chunk)
                    if piece:
                        got_any = True
                        buf.append(piece)
                        await on_delta("".join(buf))
    except httpx.HTTPStatusError:
        raise
    except httpx.HTTPError:
        return None  # network hiccup mid-stream → caller falls back

    text = "".join(buf).strip()
    if not got_any or not text:
        return None
    return text


async def hermes_chat_stream(messages: list[dict], on_delta) -> str:
    """Streaming-first chat over a full OpenAI-style message list.
    Falls back to non-streaming when endpoint/stream disabled/fails."""
    enabled = (await get_dynamic_setting("stream_enabled", "1")) == "1"

    if enabled:
        try:
            text = await _run_api_stream(messages, on_delta)
            if text:
                return text
        except HermesEngineError:
            raise
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (401, 403):
                raise HermesEngineError("کلید API نامعتبر است.")
            logger.warning("stream HTTP %s → fallback", code)
        except Exception as e:
            logger.warning("stream failed (%s) → fallback", e)

    return await _run_api(messages)


async def hermes_chat(
    message: str,
    system_prompt: str | None = None,
    user_key: int | None = None,
) -> str:
    """Send one message to the Hermes agent (or fallback backend).

    Per-user conversation continuity is preserved for cli/http backends via
    the hermes_sessions table; the api backend is stateless.
    Returns a user-friendly error string instead of raising, so bot handlers
    never crash on backend failures.
    """
    from database import get_hermes_session, set_hermes_session

    mode = resolve_mode()
    prompt = message
    if system_prompt and mode in ("cli", "http"):
        prompt = f"{system_prompt.strip()}\n\n---\n\n{message}"

    try:
        async with _semaphore():
            if mode == "cli":
                sid = await get_hermes_session(user_key) if user_key else None
                response, new_sid = await _run_cli(prompt, sid)
                if user_key and new_sid:
                    await set_hermes_session(user_key, new_sid)
                return response
            if mode == "http":
                sid = await get_hermes_session(user_key) if user_key else None
                response, new_sid = await _run_http(prompt, user_key or 0, sid)
                if user_key and new_sid:
                    await set_hermes_session(user_key, new_sid)
                return response

        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": message})
        return await _run_api(msgs)
    except HermesEngineError as e:
        logger.warning("hermes_chat failed (%s): %s", mode, redact_secrets(str(e)))
        return f"⚠️ خطا در موتور AI: {redact_secrets(str(e))}"
    except httpx.HTTPStatusError as e:
        logger.warning("hermes_chat HTTP %s: %s", e.response.status_code,
                       redact_secrets(str(e)))
        code = e.response.status_code
        if code in (401, 403):
            return "⚠️ کلید API نامعتبر است (AI_API_KEY را بررسی کن)."
        if code == 429:
            return "⚠️ محدودیت نرخ سرویس AI — چند لحظه بعد دوباره تلاش کن."
        return f"⚠️ خطای سرویس AI (HTTP {code})"
    except httpx.HTTPError as e:
        logger.warning("hermes_chat network error: %s", type(e).__name__)
        return "⚠️ ارتباط با سرویس AI برقرار نشد. اتصال اینترنت را بررسی کن."


def extract_json(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from an LLM response."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    candidates.append(text.strip())
    for c in candidates:
        try:
            data = json.loads(c)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None
