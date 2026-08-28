"""
DropAgentX v3 — Gateway (single entry point).

The gateway is the ONE door into the whole platform. It reverse-proxies each
subpath to the right backing service and exposes the discovery surface:

    /v1/*            -> LLM router (9router)          ROUTER_BASE_URL
    /dashboard/*     -> 9router web dashboard         ROUTER_DASH_URL
    /panel/*         -> our Next.js admin dashboard    PANEL_URL
    /.well-known/*   -> agent discovery (this gateway)
    /agent.json      -> A2A agent card (served here)
    /                -> local static (storefront) optional

It is built on Starlette so it can sit beside the existing FastAPI web admin
without extra dependencies (starlette ships with FastAPI/uvicorn).

Purpose: a single origin + auth boundary + one hostname for Railway, so the bot,
router and dashboards appear as one cohesive "giant" product.
"""

from __future__ import annotations

import json
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from config import config

_LOG = __import__("logging").getLogger("dropagentx.gateway")


# ---------------------------------------------------------------------------
# Agent discovery (A2A card) — ported from the radius template idea
# ---------------------------------------------------------------------------

def _agent_card() -> dict:
    url = config.AGENT_BASE_URL or "http://localhost:8080"
    return {
        "name": config.AGENT_NAME or "DropAgentX",
        "version": getattr(config, "VERSION", "3.0.0"),
        "description": "DropAgentX — a social-commerce Telegram agent with "
                       "multi-faceted memory, identity RL and a marketplace.",
        "url": url,
        "capabilities": [
            "chat", "memory", "marketplace", "image_generation", "purchase",
        ],
        "endpoints": {
            "sendMessage": f"{url}/a2a/send",
            "streamMessage": f"{url}/a2a/stream",
        },
        "protocol": "A2A",
        "interfaces": ["telegram", "web"],
    }


def _serve_agent_card(request: Request) -> JSONResponse:
    return JSONResponse(_agent_card())


def _well_known_agent(request: Request) -> JSONResponse:
    return JSONResponse({"agent": _agent_card(), "discovery": "erc8004|cloudflare"})


# ---------------------------------------------------------------------------
# Reverse proxy helper
# ---------------------------------------------------------------------------

async def _proxy(request: Request, upstream: str):
    """Forward a request to `upstream` and mirror the response back."""
    if not upstream:
        return JSONResponse({"ok": False, "error": "upstream not configured"}, status_code=503)
    path = request.url.path
    # strip a leading mount prefix if present (we mount at root of the upstream)
    target = upstream.rstrip("/") + "/" + path.lstrip("/")
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length", "connection")}
    body = await request.body()
    forward_method = request.method
    timeout = 60.0
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(forward_method, target, headers=headers, content=body)
    except Exception as e:
        _LOG.warning("proxy %s failed: %s", path, str(e)[:160])
        return JSONResponse({"ok": False, "error": "backing service unavailable",
                             "detail": str(e)[:160]}, status_code=502)
    content = resp.content
    return Response(content=content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"))


async def proxy_v1(request: Request):
    return await _proxy(request, os.getenv("ROUTER_BASE_URL", ""))

async def proxy_dashboard(request: Request):
    return await _proxy(request, os.getenv("ROUTER_DASH_URL", ""))

async def proxy_panel(request: Request):
    return await _proxy(request, os.getenv("PANEL_URL", ""))


async def health(request: Request):
    return JSONResponse({"ok": True, "service": "dropagentx-gateway",
                         "version": getattr(config, "VERSION", "3.0.0"),
                         "router": bool(config.ROUTER_BASE_URL)})


async def root(request: Request):
    card = _agent_card()
    body = json.dumps({
        "service": "DropAgentX gateway",
        "version": getattr(config, "VERSION", "3.0.0"),
        "agent": card["name"],
        "paths": {
            "/healthz": "health",
            "/agent.json": "A2A card",
            "/.well-known/agent.json": "discovery",
            "/v1/*": "LLM router (9router)",
            "/dashboard": "9router dashboard",
            "/panel": "admin dashboard",
        },
    }, ensure_ascii=False, indent=2)
    return Response(content=body, media_type="application/json")


def build_app() -> Starlette:
    return Starlette(routes=[
        Route("/", root, methods=["GET"]),
        Route("/healthz", health, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/agent.json", _serve_agent_card, methods=["GET"]),
        Route("/.well-known/agent.json", _well_known_agent, methods=["GET"]),
        Route("/v1", proxy_v1, methods=["GET", "POST"]),
        Route("/v1/{path:path}", proxy_v1, methods=["GET", "POST", "OPTIONS"]),
        Route("/dashboard", proxy_dashboard, methods=["GET", "POST"]),
        Route("/dashboard/{path:path}", proxy_dashboard, methods=["GET", "POST"]),
        Route("/panel", proxy_panel, methods=["GET", "POST"]),
        Route("/panel/{path:path}", proxy_panel, methods=["GET", "POST"]),
    ])


app = build_app()
