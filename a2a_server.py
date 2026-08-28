"""A2A / API Server — expose the bot's brain over HTTP (radius-template style).

POST /a2a   {message, user_id?, secret?}  →  {"ok":true,"response":...}
GET  /health

Enabled when A2A_PORT is set. A2A_TOKEN is mandatory; the server fails closed when it is missing.
FastAPI/uvicorn are lazy-imported so the bot runs fine without them.
"""

import hmac
import logging
import os

logger = logging.getLogger(__name__)


def build_app():
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="DropAgentX A2A")

    class A2AIn(BaseModel):
        message: str
        user_id: int = 0
        secret: str = ""

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "hermes-marketplace-a2a"}

    @app.post("/a2a")
    async def a2a(body: A2AIn):
        token = os.getenv("A2A_TOKEN", "").strip()
        # A2A can invoke paid AI and access user-scoped memory. Never expose it
        # anonymously just because the operator forgot to set a token.
        if not token:
            raise HTTPException(503, "A2A_TOKEN must be configured")
        if not hmac.compare_digest(body.secret, token):
            raise HTTPException(401, "invalid secret")
        if body.user_id <= 0 or body.user_id > 10_000_000_000:
            raise HTTPException(400, "user_id must be a real Telegram id (> 0)")
        from database import get_setting
        fleet_on = (await get_setting("fleet_enabled", "1")) == "1"

        if fleet_on:
            from fleet import run_fleet

            async def _noop(s):
                pass
            answer, meta = await run_fleet(body.message, body.user_id or 0, _noop)
            if meta.get("mode") == "team":
                return {"ok": True, "engine": "fleet",
                        "roles": meta.get("roles", []), "response": answer}
            from ai_agent import AI_SYSTEM_PROMPT
            from hermes_engine import hermes_chat
            answer = await hermes_chat(body.message, AI_SYSTEM_PROMPT,
                                       user_key=body.user_id or None)
            return {"ok": True, "engine": "direct", "response": answer}

        from ai_agent import AI_SYSTEM_PROMPT
        from hermes_engine import hermes_chat
        answer = await hermes_chat(body.message, AI_SYSTEM_PROMPT,
                                   user_key=body.user_id or None)
        return {"ok": True, "engine": "direct", "response": answer}

    return app


async def start_server():
    port = int(os.getenv("A2A_PORT", "0") or 0)
    if not port:
        return
    try:
        import uvicorn
    except ImportError:
        logger.warning("A2A_PORT تنظیم است ولی uvicorn نصب نیست — سرور غیرفعال.")
        return
    app = build_app()
    logger.info("A2A server on :%s", port)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
