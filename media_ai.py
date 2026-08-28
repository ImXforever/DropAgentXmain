"""Media AI: image generation (covers) + STT/TTS voice.

Endpoints are OpenAI-compatible. NOTE: OpenRouter does NOT support
/images/generations or /audio/* — these features gracefully fail (return
None / raise RuntimeError) when the endpoint is not available.
"""

import base64
import os
import time

import httpx

from hermes_engine import get_ai_config, get_dynamic_setting
from config import config


async def _media_config() -> dict:
    """Use a dedicated media provider; text API keys are fallback only."""
    text_conf = await get_ai_config()
    base = os.getenv("MEDIA_BASE_URL", "").strip() or text_conf["base_url"]
    key = os.getenv("MEDIA_API_KEY", "").strip() or text_conf["api_key"]
    return {"base_url": base.rstrip("/"), "api_key": key}


async def _flag(key: str) -> bool:
    return (await get_dynamic_setting(key, "1")) == "1"


async def generate_image(prompt: str) -> str:
    """Returns local file path of generated PNG, or None if unavailable."""
    if not await _flag("img_enabled"):
        raise RuntimeError("تولید تصویر توسط ادمین غیرفعال است.")
    if not prompt.strip():
        raise ValueError("پرامپت خالی است.")
    conf = await _media_config()
    model = await get_dynamic_setting("img_model", "dall-e-3")

    # OpenRouter doesn't support /images/generations → skip gracefully
    if "openrouter.ai" in conf.get("base_url", ""):
        raise RuntimeError(
            "تصویرسازی از طریق OpenRouter پشتیبانی نمی‌شود. "
            "برای کاور از دکمهٔ 📚 Tutorial یا دستی استفاده کن."
        )

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            conf["base_url"].rstrip("/") + "/images/generations",
            headers={"Authorization": f"Bearer {conf['api_key']}"},
            json={
                "model": model,
                "prompt": prompt[:1000],
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",
            },
        )
        r.raise_for_status()
        data = r.json()
    item = (data.get("data") or [{}])[0]
    b64 = item.get("b64_json")
    url = item.get("url")
    os.makedirs(os.path.join(config.UPLOAD_DIR, "covers"), exist_ok=True)
    path = os.path.join(config.UPLOAD_DIR, "covers", f"cover_{int(time.time())}.png")
    if b64:
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        return path
    if url:
        async with httpx.AsyncClient(timeout=60) as c:
            img = await c.get(url)
            img.raise_for_status()
            with open(path, "wb") as f:
                f.write(img.content)
        return path
    return None


async def speech_to_text(ogg_path: str) -> str | None:
    """Returns transcribed text, or None if endpoint unavailable."""
    if not await _flag("stt_enabled"):
        return None
    conf = await _media_config()
    if "openrouter.ai" in conf.get("base_url", ""):
        return None  # not supported via OpenRouter
    model = await get_dynamic_setting("stt_model", "whisper-1")
    try:
        with open(ogg_path, "rb") as f:
            files = {"file": ("voice.ogg", f, "audio/ogg")}
            async with httpx.AsyncClient(timeout=90) as c:
                r = await c.post(
                    conf["base_url"].rstrip("/") + "/audio/transcriptions",
                    headers={"Authorization": f"Bearer {conf['api_key']}"},
                    data={"model": model},
                    files=files,
                )
        r.raise_for_status()
        return (r.json().get("text") or "").strip()
    except Exception:
        return None


async def text_to_speech(text: str) -> str | None:
    """Returns local mp3 path, or None if endpoint unavailable."""
    if not await _flag("tts_enabled"):
        return None
    conf = await _media_config()
    if "openrouter.ai" in conf.get("base_url", ""):
        return None  # not supported via OpenRouter
    model = await get_dynamic_setting("tts_model", "tts-1")
    voice = await get_dynamic_setting("tts_voice", "alloy")
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(
                conf["base_url"].rstrip("/") + "/audio/speech",
                headers={"Authorization": f"Bearer {conf['api_key']}"},
                json={"model": model, "voice": voice, "input": text[:4000]},
            )
            r.raise_for_status()
            audio = r.content
        path = os.path.join(config.UPLOAD_DIR, f"tts_{int(time.time())}.mp3")
        with open(path, "wb") as f:
            f.write(audio)
        return path
    except Exception:
        return None
