"""
DropAgentX v3 — MCP Bridge.

Exposes our bot's tool set (_tool_specs from tools.py) over the Model Context
Protocol (JSON-RPC / HTTP), so an external agent harness (e.g. Hermes Agent)
can call "buy", "search", "generate_cover_image", "remember", etc. the same way
our Telegram bot does. This is the seam that lets the big agent (hermes) drive
the marketplace agent (us) without duplicating the logic.

Endpoints (JSON-RPC 2.0 over HTTP):
    POST /mcp         -> tools/list, tools/call, initialize
    GET  /mcp/healthz -> liveness (used by Railway/uptime)

We reuse `tools.py::execute_tool` + `get_tool_specs` (or _TOOL_SPECS) so the
behaviour is identical to in-bot tool calls. Auth via A2A_TOKEN (Bearer), fail-open
only when no token is configured (dev).
"""

from __future__ import annotations

import json
import os
import traceback

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


def _specs() -> list:
    try:
        from tools import __dict__ as _d
        specs = _d.get("_tool_specs") or _d.get("TOOL_SPECS") or []
        return specs
    except Exception:
        return []


async def _call_tool(name: str, args: dict, user_id: int) -> str:
    from tools import execute_tool
    return await execute_tool(name, args, user_id)


async def handle_rpc(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32001, "message": "unauthorized"},
                             "id": None}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"},
                             "id": None}, status_code=400)
    rid = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": rid,
                             "result": {"tools": _specs()}})
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "DropAgentX", "version": config.VERSION}}})

    if method == "tools/call":
        tool = params.get("name", "")
        tool_args = params.get("arguments", {})
        uid = int(params.get("user_id", 0) or 0)
        try:
            result = await _call_tool(tool, tool_args, uid)
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": result}]}})
        except Exception as e:
            return JSONResponse({"jsonrpc": "2.0", "id": rid,
                                 "error": {"code": -32603, "message": str(e)[:300],
                                           "data": traceback.format_exc()[:1000]}})

    return JSONResponse({"jsonrpc": "2.0", "id": rid,
                         "error": {"code": -32601, "message": f"method not found: {method}"}})


async def health(request: Request):
    return JSONResponse({"ok": True, "service": "dropagentx-mcp", "tools": len(_specs())})


def build_app() -> Starlette:
    return Starlette(routes=[
        Route("/mcp", handle_rpc, methods=["POST", "OPTIONS"]),
        Route("/mcp/healthz", health, methods=["GET"]),
    ])


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_PORT", "9020") or 9020)
    uvicorn.run(build_app(), host="0.0.0.0", port=port)
