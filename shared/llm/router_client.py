"""
DropAgentX v3 — LLM Router Client.

This is the seam that integrates a router such as **9router** into our AI path.
Normally `hermes_engine` calls a provider directly. With a router in front we
gain, for free: 3-tier fallback (subscription → cheap → free), quota/account
tracking, and token saving — without duplicating that logic ourselves.

Design:
  * If `ROUTER_BASE_URL` is set, calls go to `{ROUTER_BASE_URL}/v1/chat/completions`
    (an OpenAI-compatible router endpoint). 
  * No router set OR router fails + `ROUTER_FALLBACK_TO_DIRECT=1` → fall back to
    the direct provider via `hermes_engine.llm_call_raw`.
  * Everything is async, fail-safe, and logged to `observability`.

It is a *thin adapter*: it reuses the same OpenAI-compatible payload/shape as
`hermes_engine`, so wiring it in is a drop-in replacement for the primary call.
"""

from __future__ import annotations

import json
import time

import httpx

from config import config

logger = __import__("logging").getLogger("dropagentx.router")


def router_enabled() -> bool:
    return bool(config.ROUTER_BASE_URL)


async def chat(messages: list, model: str | None = None,
               temperature: float = 0.7, max_tokens: int = 2048,
               tools: list | None = None, fallback_handler=None) -> str:
    """Route a chat completion through the configured router.

    Returns the assistant text. If routing is unavailable and a `fallback_handler`
    is given (async), call it and return its result.
    """
    if not router_enabled():
        if fallback_handler is not None:
            return await fallback_handler()
        raise RuntimeError("ROUTER_BASE_URL not set and no fallback provided")

    base = config.ROUTER_BASE_URL.rstrip("/")
    endpoint = f"{base}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.ROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {config.ROUTER_API_KEY}"

    payload = {
        "model": model or "gpt-4o-mini",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=config.ROUTER_TIMEOUT) as client:
            r = await client.post(endpoint, headers=headers, json=payload)
            if r.status_code not in (200, 201):
                r.raise_for_status()
            data = r.json()
        ms = int((time.monotonic() - start) * 1000)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception:
            logger.warning("router returned unexpected shape: %s", str(data)[:200])
            if fallback_handler is not None:
                return await fallback_handler()
            return ""
    except Exception as e:
        logger.warning("router call failed (%s) — fallback to direct", str(e)[:160])
        if config.ROUTER_FALLBACK_TO_DIRECT and fallback_handler is not None:
            return await fallback_handler()
        raise


# Thin wrapper matching hermes_engine.llm_call_raw(convo, ...) signature so we
# can be used as a drop-in for the tool-loop PRIMARY path.
async def llm_call_with_router(convo: list, model: str | None = None,
                               temperature: float = 0.7, max_tokens: int = 1200,
                               tools: list | None = None, fallback_handler=None):
    """Returns a payload dict (with 'choices'[0].message) so callers that expect
    hermes_engine.llm_call_raw's shape can switch without rewriting."""
    text = await chat(convo, model=model, temperature=temperature,
                      max_tokens=max_tokens, tools=tools,
                      fallback_handler=fallback_handler)
    return {"choices": [{"message": {"content": text}}]}
