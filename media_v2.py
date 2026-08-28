"""
DropAgentX v2.0.0 — Image generation & multimodal agent.

Two goals:

  A) "Google brand" image generation via **Gemini** free-tier API, so covers and
     art are generated WITHOUT a paid image model. Also supports a plain
     OpenAI-compatible `/images/generations` endpoint as fallback.

  B) A single OpenAI-compatible **system** that can be pointed at Gemini's
     OpenAI-compatible base URL (`.../v1beta/openai`) *or* any OpenAI router,
     so text + vision + tool usage all work through one interface.

Backend selection (config.IMAGE_GEN_BACKEND):
    gemini  -> Gemini REST /:generateContent (free plan, GEMINI_API_KEY)
    openai  -> POST {MEDIA_BASE_URL}/images/generations
    auto    -> gemini first, silently fall back to openai
"""

import base64
import os
import time
import uuid

import httpx

from config import config
from observability import db_log

_B64_PREFIX_TO_MIME = {
    "data:image/png": "png", "data:image/jpeg": "jpeg", "data:image/webp": "webp",
}


def _mime_ext(mime: str) -> str:
    mime = (mime or "").lower()
    if "png" in mime:
        return "png"
    if "webp" in mime:
        return "webp"
    if "jpeg" in mime or "jpg" in mime:
        return "jpg"
    return "png"


async def _gemini_generate(prompt: str, model: str) -> str:
    """Generate an image via Gemini REST. Returns a local file path."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY تنظیم نشده (برای پلن رایگان Gemini)")
    url = f"{config.GEMINI_BASE_URL.rstrip('/')}/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt[:2000]}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, params={"key": config.GEMINI_API_KEY}, json=payload)
        if r.status_code == 429:
            raise RuntimeError("Gemini rate limit (free tier) — کمی صبر کن یا backend را toggle کن")
        r.raise_for_status()
        data = r.json()
    # Walk candidates[].content.parts[] for an inline image.
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                b64 = inline["data"]
                mime = inline.get("mimeType") or "image/png"
                return _save_b64(b64, _mime_ext(mime))
            if part.get("text"):
                continue
    raise RuntimeError("Gemini پاسخ تصویری برنگرداند")


def _save_b64(b64: str, ext: str) -> str:
    os.makedirs(os.path.join(config.UPLOAD_DIR, "covers"), exist_ok=True)
    path = os.path.join(config.UPLOAD_DIR, "covers",
                        f"gemini_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}")
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path


async def _openai_generate(prompt: str, model: str) -> str:
    """Generate via any OpenAI-compatible /images/generations endpoint."""
    base = os.getenv("MEDIA_BASE_URL", "").strip() or os.getenv("AI_BASE_URL", "").strip()
    key = os.getenv("MEDIA_API_KEY", "").strip() or os.getenv("AI_API_KEY", "").strip()
    if not base or not key:
        raise RuntimeError("MEDIA_BASE_URL / MEDIA_API_KEY تنظیم نشده")
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            f"{base.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "prompt": prompt[:2000], "n": 1},
        )
        r.raise_for_status()
        item = (r.json().get("data") or [{}])[0]
    if item.get("b64_json"):
        return _save_b64(item["b64_json"], "png")
    if item.get("url"):
        async with httpx.AsyncClient(timeout=90) as c:
            img = await c.get(item["url"])
            img.raise_for_status()
        os.makedirs(os.path.join(config.UPLOAD_DIR, "covers"), exist_ok=True)
        path = os.path.join(config.UPLOAD_DIR, "covers",
                            f"gen_{int(time.time())}_{uuid.uuid4().hex[:6]}.png")
        with open(path, "wb") as f:
            f.write(img.content)
        return path
    raise RuntimeError("OpenAI-compatible endpoint تصویر برنگرداند")


async def generate_image(prompt: str) -> str:
    """Generate a cover image and return the local file path."""
    if not prompt.strip():
        raise ValueError("پرامپت خالی است")
    backend = (config.IMAGE_GEN_BACKEND or "auto").lower()
    model = os.getenv("GEMINI_IMAGE_MODEL", config.GEMINI_IMAGE_MODEL)
    if backend in ("gemini", "auto"):
        try:
            path = await _gemini_generate(prompt, model)
            await db_log("media", "image gemini OK", level="INFO", data={"prompt": prompt[:120]})
            return path
        except Exception as e:
            if backend == "gemini":
                raise
            # auto fallback
    # openai / auto fallback
    path = await _openai_generate(prompt, os.getenv("AI_IMAGE_MODEL", config.GEMINI_IMAGE_MODEL))
    await db_log("media", "image openai OK", level="INFO", data={"prompt": prompt[:120]})
    return path


# ---------------------------------------------------------------------------
# OpenAI-compatible SYSTEM (text + vision). Point AI_BASE_URL at
# Gemini's OpenAI-compatible base (`https://generativelanguage.googleapis.com/v1beta/openai`)
# or any OpenRouter/OpenAI router.
# ---------------------------------------------------------------------------

async def system_chat(messages: list[dict], model: str | None = None,
                      temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """Single OpenAI-compatible chat call (works with Gemini-compatible base too)."""
    from hermes_engine import get_ai_config
    conf = await get_ai_config()
    api_key = conf["api_key"] or config.GEMINI_API_KEY
    base_url = os.getenv("AI_BASE_URL", "").strip() or conf["base_url"]
    # For Gemini OpenAI-compat, the base URL typically ends with /v1beta or /v1beta/openai.
    endpoint = f"{base_url.rstrip('/')}/chat/completions" if base_url else ""
    if not api_key or not endpoint:
        raise RuntimeError("AI/Gemini API key یا base URL تنظیم نشده")
    payload = {
        "model": model or conf["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(endpoint, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except Exception:
        return str(data)[:1000]


async def gemini_vision(prompt: str, image_data_url: str) -> str:
    """Ask Gemini (vision) about an image. `image_data_url` = data:image/...;base64,..."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY تنظیم نشده")
    url = (f"{config.GEMINI_BASE_URL.rstrip('/')}/models/{config.GEMINI_VISION_MODEL}"
           ":generateContent")
    # extract base64 payload
    b64 = image_data_url.split(",", 1)[1] if "," in image_data_url else image_data_url
    mime = image_data_url.split(";")[0].split(":", 1)[1] if ";" in image_data_url else "image/jpeg"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": mime, "data": b64}},
            ]
        }]
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(url, params={"key": config.GEMINI_API_KEY}, json=payload)
        r.raise_for_status()
        data = r.json()
    for cand in data.get("candidates", []):
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if text:
            return text
    return ""
