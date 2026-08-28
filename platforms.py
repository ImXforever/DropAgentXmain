"""Second-gateway scaffolds. Enabled only when their tokens/libs exist.

- Discord: set DISCORD_TOKEN + `pip install discord.py` → run start_discord()
- Telegram webhook mode (alternative to polling) is documented in DEPLOY.md
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def maybe_start_discord(on_text):
    """on_text(text, user_id) -> reply str. Returns True if started."""
    token = os.getenv("DISCORD_TOKEN", "")
    if not token:
        logger.info("Discord gateway: DISCORD_TOKEN خالی — غیرفعال.")
        return False
    try:
        import discord  # type: ignore
    except ImportError:
        logger.warning("Discord gateway: discord.py نصب نیست (pip install discord.py).")
        return False

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Discord gateway live as %s", client.user)

    @client.event
    async def on_message(message):
        if message.author.bot or not message.content:
            return
        reply = await on_text(message.content, message.author.id)
        if reply:
            await message.channel.send(reply[:2000])

    asyncio.get_running_loop().create_task(client.start(token))
    logger.info("Discord gateway starting…")
    return True
