"""
DropAgentX v3 — A2A v2 (Agent-to-Agent).

Extends the discovery/agent-card surface (from the radius template) with a
simple `message/send` handler so other agents can drive DropAgentX. It is
self-contained: it reuses the same AI engine that the Telegram bot uses
(hermes_engine.hermes_chat) and requires either no token (dev) or
`A2A_TOKEN` as a Bearer token. Fails closed.

Routes (over the gateway at /a2a/*):
    POST /a2a/send      -> {message, user_id?, session_id?} -> {ok, response, session_id}
    POST /a2a/stream    -> same (alias, currently non-streaming)
    GET  /agent.json    -> A2A agent card
    GET  /healthz       -> liveness
"""

from __future__ import annotations

import os
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from config import config


def _authorized(request: Request) -> bool:
    if not config.A2A_TOKEN:
        return True
    auth = request.headers.get("authorization", "")
    return auth in (f"Bearer {config.A2A_TOKEN}", config.A2A_TOKEN)


def _agent_card() -> dict:
    url = config.AGENT_BASE_URL or "http://localhost:8080"
    return {
        "name": config.AGENT_NAME,
        "version": getattr(config, "VERSION", "3.0.0"),
        "description": "DropAgentX agent (social-commerce Telegram, memory, identity RL).",
        "url": url,
        "capabilities": ["chat", "memory", "image_generation", "purchase"],
        "endpoints": {"sendMessage": f"{url}/a2a/send",
                      "streamMessage": f"{url}/a2a/stream"},
        "protocol": "A2A",
        "interfaces": ["telegram", "web"],
    }


async def _run_agent(message: str, user_id: int) -> str:
    """Run the same AI path the Telegram bot uses."""
    from ai_agent import AI_SYSTEM_PROMPT
    from hermes_engine import hermes_chat
    try:
        answer = await hermes_chat(message, AI_SYSTEM_PROMPT,
                                   user_key=user_id or None)
        return answer or ""
    except Exception as e:
        return f"[agent error] {e}"


async def handle_send(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    user_id = int(body.get("user_id", 0) or 0)
    if not message:
        return JSONResponse({"ok": False, "error": "message required"}, status_code=400)
    response = await _run_agent(message, user_id)
    return JSONResponse({"ok": True, "response": response,
                         "session_id": body.get("session_id", ""),
                         "engine": "dropagentx"})


async def handle_stream(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("message") or "").strip()
    user_id = int(body.get("user_id", 0) or 0)
    if not message:
        return JSONResponse({"ok": False, "error": "message required"}, status_code=400)
    response = await _run_agent(message, user_id)
    return JSONResponse({"ok": True, "response": response,
                         "session_id": body.get("session_id", ""),
                         "engine": "dropagentx", "stream": False})


async def health(request: Request):
    return JSONResponse({"ok": True, "service": "dropagentx-a2a",
                         "version": getattr(config, "VERSION", "3.0.0")})


def build_app() -> Starlette:
    return Starlette(routes=[
        Route("/a2a/send", handle_send, methods=["POST"]),
        Route("/a2a/stream", handle_stream, methods=["POST"]),
        Route("/agent.json", lambda r: JSONResponse(_agent_card()), methods=["GET"]),
        Route("/.well-known/agent.json",
              lambda r: JSONResponse({"agent": _agent_card(), "discovery": "erc8004"}),
              methods=["GET"]),
        Route("/healthz", health, methods=["GET"]),
    ])


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("A2A_PORT", "9000") or 9000)
    uvicorn.run(build_app(), host="0.0.0.0", port=port)
