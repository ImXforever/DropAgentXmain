"""Background chain verification and payout worker.

Disabled by default. Enable with TREASURY_AUTO_ENABLED=1 only after all chain
wallet/token/RPC settings and the external payout signer are configured.
"""

import asyncio
import logging
import os

from blockchain import ChainUnavailable, request_payout, verify_deposit
from config import config

logger = logging.getLogger(__name__)


async def process_deposits(limit: int = 20, bot=None) -> int:
    from database import (
        approve_verified_deposit,
        list_pending_deposits,
        record_deposit_verification_attempt,
    )
    approved = 0
    for dep in await list_pending_deposits(limit):
        try:
            result = await verify_deposit(
                dep["network"], dep["txid"], dep["amount_usdt"],
                config.DEPOSIT_WALLETS.get(dep["network"], ""),
            )
            if not result.verified:
                await record_deposit_verification_attempt(dep["id"], result.reason)
                continue
            row = await approve_verified_deposit(dep["id"], reviewed_by=0)
            if row:
                approved += 1
                logger.info(
                    "verified deposit id=%s network=%s confirmations=%s",
                    dep["id"], dep["network"], result.confirmations,
                )
                if bot:
                    try:
                        from database import usdt_to_credits
                        credits = usdt_to_credits(dep["amount_usdt"])
                        await bot.send_message(
                            dep["user_id"],
                            f"✅ واریز #{dep['id']} به‌صورت خودکار تأیید شد. +{credits:,} کردیت",
                        )
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("deposit verification id=%s failed: %s", dep["id"], type(exc).__name__)
            await record_deposit_verification_attempt(dep["id"], type(exc).__name__)
    return approved


async def process_withdrawals(limit: int = 10, bot=None) -> int:
    from database import list_pending_withdrawals, mark_withdrawal_paid, record_payout_error
    paid = 0
    for wd in await list_pending_withdrawals(limit):
        try:
            txid = await request_payout(
                wd["network"], wd["address"],
                wd["amount_usdt"] - wd["fee_usdt"],
                f"withdrawal:{wd['id']}",
            )
            row = await mark_withdrawal_paid(wd["id"], txid, reviewed_by=0)
            if row:
                paid += 1
                logger.info("paid withdrawal id=%s txid=%s", wd["id"], txid[:16])
                if bot:
                    try:
                        payout = wd["amount_usdt"] - wd["fee_usdt"]
                        await bot.send_message(
                            wd["user_id"],
                            f"💸 برداشت #{wd['id']} پرداخت شد: {payout:g} USDT\nTXID: {txid}",
                        )
                    except Exception:
                        pass
        except Exception as exc:
            await record_payout_error(wd["id"], type(exc).__name__)
            if not isinstance(exc, ChainUnavailable):
                logger.warning("withdrawal id=%s failed: %s", wd["id"], type(exc).__name__)
    return paid


async def treasury_once(bot=None) -> tuple[int, int]:
    return await process_deposits(bot=bot), await process_withdrawals(bot=bot)


async def run_treasury(bot=None) -> None:
    """Long-running worker; one instance only."""
    if os.getenv("TREASURY_AUTO_ENABLED", "0") != "1":
        logger.info("Treasury auto worker disabled")
        return
    delay = max(15, int(os.getenv("TREASURY_POLL_SECONDS", "60")))
    while True:
        try:
            await treasury_once(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("treasury worker iteration failed")
        await asyncio.sleep(delay)
