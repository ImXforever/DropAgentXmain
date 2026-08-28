"""Shared commerce primitives.

All credit purchases go through this module so the Telegram bot and Mini App
cannot diverge on balances, ledgers, sales counters, or idempotency.
"""

from dataclasses import dataclass

from config import config


class CommerceError(Exception):
    """A safe, user-facing commerce failure."""


@dataclass(frozen=True)
class PurchaseResult:
    product: dict
    buyer_id: int
    seller_id: int
    price: int
    commission: int
    seller_earning: int
    payment_method: str


async def purchase_with_credits(
    buyer_id: int,
    product_id: int,
    *,
    price_override: int | None = None,
    payment_method: str = "credits",
    coupon_id: int | None = None,
) -> PurchaseResult:
    """Atomically purchase a product with credits.

    The unique purchase index makes retries idempotent. The balance check and
    all ledger/counter updates happen in one SQLite transaction. A caller must
    perform non-financial notifications after this function returns.
    """
    from database import get_db, get_product, invalidate_user

    product = await get_product(product_id)
    if not product or not product.get("is_active") or product.get("status") != "approved":
        raise CommerceError("محصول در دسترس نیست")
    if product["creator_id"] == buyer_id:
        raise CommerceError("محصول خودت است")

    seller_id = int(product["creator_id"])
    original_price = int(product["price_credits"])
    price = int(price_override if price_override is not None else original_price)
    if price < 1:
        raise CommerceError("قیمت محصول نامعتبر است")
    if payment_method not in {"credits", "stars"}:
        raise CommerceError("روش پرداخت نامعتبر است")

    seller_plan = "free"
    async with get_db() as db:
        seller_cur = await db.execute(
            "SELECT user_id, COALESCE(is_banned,0), COALESCE(seller_plan,'free') "
            "FROM users WHERE user_id=?",
            (seller_id,),
        )
        seller_row = await seller_cur.fetchone()
        if not seller_row:
            raise CommerceError("فروشنده معتبر نیست")
        if seller_row[1]:
            raise CommerceError("فروشنده مسدود است")
        seller_plan = seller_row[2]

        if coupon_id is not None:
            coupon_cur = await db.execute(
                "SELECT percent FROM coupons WHERE id=? AND owner_id=? AND active=1 "
                "AND (max_uses=0 OR uses<max_uses)",
                (coupon_id, seller_id),
            )
            coupon_row = await coupon_cur.fetchone()
            if not coupon_row:
                raise CommerceError("کد تخفیف منقضی یا نامعتبر است")
            calculated = max(1, round(original_price * (100 - coupon_row[0]) / 100))
            if price != calculated:
                price = calculated
            coupon_cur = await db.execute(
                "UPDATE coupons SET uses=uses+1 WHERE id=? AND active=1 "
                "AND (max_uses=0 OR uses<max_uses)",
                (coupon_id,),
            )
            if coupon_cur.rowcount == 0:
                raise CommerceError("ظرفیت کد تخفیف همین الان تمام شد")

        # Mini App and Telegram now share the same plan-based commission.
        comm_rate = 0.05 if seller_plan == "pro" else 0.15
        commission = int(price * comm_rate)
        earning = price - commission

        buyer_cur = await db.execute(
            "SELECT credits, COALESCE(is_banned,0) FROM users WHERE user_id=?",
            (buyer_id,),
        )
        buyer_row = await buyer_cur.fetchone()
        if not buyer_row or buyer_row[1]:
            raise CommerceError("حساب در دسترس نیست")

        cur = await db.execute(
            "INSERT OR IGNORE INTO purchases "
            "(buyer_id, product_id, price_credits, payment_method) VALUES (?,?,?,?)",
            (buyer_id, product_id, price, payment_method),
        )
        if cur.rowcount == 0:
            raise CommerceError("قبلاً این محصول را خریده‌ای")

        if payment_method == "credits":
            # Conditional UPDATE prevents an overdraft under concurrent calls.
            cur = await db.execute(
                "UPDATE users SET credits=credits-?, total_spent=total_spent+? "
                "WHERE user_id=? AND credits>=?",
                (price, price, buyer_id, price),
            )
            if cur.rowcount == 0:
                raise CommerceError("کردیت کافی نداری")
            buyer_amount = -price
        else:
            # Stars are settled by Telegram; this primitive is only used here
            # if the caller has already completed the external payment.
            buyer_amount = 0

        await db.execute(
            "UPDATE users SET credits=credits+?, total_earned=total_earned+?, "
            "products_sold=products_sold+1 WHERE user_id=?",
            (earning, earning, seller_id),
        )
        await db.execute(
            "UPDATE products SET sales_count=sales_count+1 WHERE id=?",
            (product_id,),
        )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description) "
            "VALUES (?, ?, 'purchase', ?, ?)",
            (buyer_id, buyer_amount, product_id, f"Purchased: {product['title']}"),
        )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description) "
            "VALUES (?, ?, 'sale', ?, ?)",
            (seller_id, earning, product_id, f"Sold: {product['title']}"),
        )

    invalidate_user(buyer_id)
    invalidate_user(seller_id)
    return PurchaseResult(
        product=product,
        buyer_id=buyer_id,
        seller_id=seller_id,
        price=price,
        commission=commission,
        seller_earning=earning,
        payment_method=payment_method,
    )


async def apply_sale_network_effects(result: PurchaseResult, bot=None) -> None:
    """Apply first-sale promotion and referral/upline rewards once.

    This is deliberately outside the money transaction: a notification or
    referral side effect can fail without rolling back the actual purchase.
    """
    from database import get_referrer, set_role, update_credits
    from handlers.org import effective_role

    seller = result.seller_id
    if await effective_role(seller) == "associate":
        await set_role(seller, "soldier", granted_by=0)
        if bot:
            try:
                await bot.send_message(
                    seller,
                    "🪖 اولین فروشت ثبت شد و از کارآموز به **سرباز** ارتقا گرفتی.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    seller_ref = await get_referrer(seller)
    if seller_ref and result.commission > 0:
        role = await effective_role(seller_ref)
        if role in ("capo", "underboss", "godfather"):
            override = int(result.commission * config.CAPO_OVERRIDE_PCT)
            if override > 0:
                await update_credits(
                    seller_ref, override, "capo_override",
                    f"Override on sale: {result.product['title']}", result.product["id"],
                )

    referrer_id = await get_referrer(result.buyer_id)
    if referrer_id and result.commission > 0:
        share = int(result.commission * config.REF_COMMISSION_SHARE)
        if share > 0:
            await update_credits(
                referrer_id, share, "ref_commission",
                f"Lifetime share on sale to user {result.buyer_id}", result.product["id"],
            )

    try:
        from handlers.referral import maybe_qualify_referral
        await maybe_qualify_referral(bot, result.buyer_id)
    except Exception:
        pass


async def refund_credits(user_id: int, amount: int, description: str, reference_id: int | None = None):
    """Ledgered refund helper used by failed/manual withdrawal flows."""
    from database import update_credits
    if amount > 0:
        await update_credits(user_id, amount, "refund", description, reference_id)
