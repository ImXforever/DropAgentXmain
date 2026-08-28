from aiogram import Router, F
import os
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from database import (
    search_products, get_product, get_user, update_credits,
    is_product_purchased_by_user, get_db,
    get_coupon, get_coupon_by_id,
)
from config import config
from utils import get_or_create_user,  send_safe, edit_safe
from aiogram.types import LabeledPrice
from aiogram.fsm.state import State as _St
import math as _math
from aiogram.types import FSInputFile

router = Router()


class CouponInput(StatesGroup):
    waiting_code = State()

CATEGORIES = {
    "all": "📂 همه",
    "education": "📚 آموزش",
    "graphics": "🎨 گرافیک",
    "coding": "💻 کدنویسی",
    "content": "📝 محتوا",
    "template": "📦 قالب",
    "tools": "🔧 ابزار",
    "general": "📂 سایر",
}


class MarketSearch(StatesGroup):
    waiting_query = State()


def build_products_view(products: list[dict], title: str) -> tuple[str, InlineKeyboardMarkup]:
    per = config.CREDITS_PER_USDT
    text = f"{title}\n💡 ۱٬۰۰۰ کردیت = ۱ USDT\n\n"
    buttons = []
    for p in products:
        price = int(p.get("price_credits") or 0)
        usd_eq = f"≈{price / max(1, per):.2f}$"
        stars = p.get("stars")
        star_line = f" ⭐{stars:.1f}" if stars else ""
        text += f"• **{p['title']}**\n"
        text += (f"  💰 {price:,} کردیت ({usd_eq}) | 📊 "
                 f"{p.get('sales_count') or 0} فروش{star_line}\n")
        text += f"  👤 {p.get('creator_name', 'ناشناس')}\n\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"📖 {p['title'][:36]} · {price:,}💰",
                callback_data=f"view_product_{p['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 فروشگاه", callback_data="marketplace")])
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_products(callback: CallbackQuery, products: list[dict], title: str):
    if not products:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="marketplace")],
        ])
        await edit_safe(callback.message, f"{title}\n\nمحصولی پیدا نشد!", kb)
        await callback.answer()
        return
    text, kb = build_products_view(products, title)
    await edit_safe(callback.message, text, kb)
    await callback.answer()


@router.callback_query(F.data == "marketplace")
async def marketplace_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 محبوب‌ترین", callback_data="mp_popular")],
        [InlineKeyboardButton(text="🆕 جدیدترین", callback_data="mp_latest")],
        [InlineKeyboardButton(text="🎯 برای تو", callback_data="mp_recs")],
        [InlineKeyboardButton(text="🔍 جستجو", callback_data="mp_search")],
        [
            InlineKeyboardButton(text="📚 آموزش", callback_data="mp_cat_education"),
            InlineKeyboardButton(text="🎨 گرافیک", callback_data="mp_cat_graphics"),
        ],
        [
            InlineKeyboardButton(text="💻 کدنویسی", callback_data="mp_cat_coding"),
            InlineKeyboardButton(text="📝 محتوا", callback_data="mp_cat_content"),
        ],
        [
            InlineKeyboardButton(text="📦 قالب‌ها", callback_data="mp_cat_template"),
            InlineKeyboardButton(text="🔧 ابزارها", callback_data="mp_cat_tools"),
        ],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
    ])
    await edit_safe(
        callback.message,
        "🛒 **بازار محصولات دیجیتال**\n\n"
        "اینجا هر ایده می‌تواند یک محصول شود — جستجو کن، کشف کن، صاحبش شو.",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "mp_popular")
async def mp_popular(callback: CallbackQuery):
    products = await search_products(limit=10)
    await show_products(callback, products, "🔥 **محصولات محبوب**")


@router.callback_query(F.data == "mp_latest")
async def mp_latest(callback: CallbackQuery):
    products = await search_products(limit=10)
    await show_products(callback, products, "🆕 **جدیدترین محصولات**")


@router.callback_query(F.data == "mp_recs")
async def mp_recs(callback: CallbackQuery):
    """🎯 Personalized picks from long-term memory + purchase profile."""
    from memory import recommend_for_user
    recs = await recommend_for_user(callback.from_user.id, limit=5)
    if not recs:
        await callback.answer("هنوز داده کافی برای پیشنهاد ندارم — خرید/چت کن تا یاد بگیرم!", show_alert=True)
        return
    await show_products(callback, recs,
                        "🎯 **پیشنهاد شده برای تو**\nبر اساس سلیقه و تاریخچهٔ خریدت")


@router.callback_query(F.data == "mp_search")
async def mp_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MarketSearch.waiting_query)
    await edit_safe(
        callback.message,
        "🔍 **جستجوی محصول**\n\nعنوان یا کلمه کلیدی رو بنویس:\n\nبرای لغو /cancel بزن.",
    )
    await callback.answer()


@router.message(MarketSearch.waiting_query, F.text & ~F.text.startswith("/"))
async def mp_search_input(message: Message, state: FSMContext):
    query = message.text.strip()
    await state.clear()
    if len(query) < 2:
        await message.answer("❌ عبارت خیلی کوتاهه. دوباره تلاش کن.")
        return
    products = await search_products(query=query, limit=10)
    if not products:
        await message.answer(f"🔍 نتیجه‌ای برای «{query}» پیدا نشد!")
        return
    text, kb = build_products_view(products, f"🔍 **نتایج جستجو: {query}**")
    await send_safe(message, text, kb)


@router.callback_query(F.data.startswith("mp_cat_"))
async def mp_category(callback: CallbackQuery):
    category = callback.data.replace("mp_cat_", "")
    products = await search_products(category=category, limit=10)
    cat_name = CATEGORIES.get(category, category)
    await show_products(callback, products, f"📂 **{cat_name}**")


@router.callback_query(F.data.startswith("view_product_"))
async def view_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    product = await get_product(product_id)

    if not product:
        await callback.answer("محصول پیدا نشد!", show_alert=True)
        return

    user = await get_or_create_user(callback.from_user)
    is_owner = product["creator_id"] == callback.from_user.id
    already_purchased = await is_product_purchased_by_user(product_id, callback.from_user.id)

    from database import product_rating
    avg_stars, n_reviews = await product_rating(product_id)
    stars_line = f"⭐ {avg_stars} ({n_reviews} دیدگاه)" if n_reviews else "⭐ جدید"

    st_badge = {"pending": " ⏳درانتظارتأیید", "rejected": " ❌ردشده"}.get(
        product.get("status") or "approved", "")

    cat_name = CATEGORIES.get(product["category"], product["category"])

    per = config.CREDITS_PER_USDT
    price = int(product["price_credits"] or 0)
    text = f"📖 **{product['title']}**{st_badge}  {stars_line}\n\n"
    text += f"📝 {product['description'] or 'توضیحی ثبت نشده'}\n\n"
    text += f"💰 قیمت: **{price:,} کردیت** (≈{price / max(1, per):.2f}$)\n"
    text += f"📂 دسته: {cat_name}\n"
    text += f"🏷️ تگ‌ها: {product['tags'] or '-'}\n"
    text += f"📊 فروش: {product.get('sales_count') or 0}\n"
    text += f"👤 فروشنده: @{product.get('creator_username') or '-'}\n\n"
    text += f"💰 موجودی شما: **{user['credits']:,} کردیت** " \
            f"(≈{user['credits'] / max(1, per):.2f}$)"

    buttons = []
    if product.get("link"):
        buttons.append([InlineKeyboardButton(text="🔗 لینک محصول", url=product["link"])])
    if is_owner:
        if (product.get("status") or "pending") == "pending":
            buttons.append([InlineKeyboardButton(
                text="⏳ در انتظار تأیید ادمین", callback_data="none_pending")])
        buttons.append([
            InlineKeyboardButton(
                text="🔴 غیرفعال کن" if product["is_active"] else "🟢 فعال کن",
                callback_data=(
                    f"deactivate_product_{product_id}"
                    if product["is_active"]
                    else f"activate_product_{product_id}"
                ),
            )
        ])
    elif already_purchased:
        if product["file_path"]:
            buttons.append([
                InlineKeyboardButton(text="📥 دانلود محصول", callback_data=f"download_product_{product_id}")
            ])
        buttons.append([
            InlineKeyboardButton(text="⭐ ثبت دیدگاه", callback_data=f"rv_{product_id}")
        ])
        buttons.append([InlineKeyboardButton(text="✅ خریده‌شده", callback_data="mp_latest")])
    else:
        # ⭐ Stars one-tap checkout (admin-toggleable)
        from hermes_engine import get_dynamic_setting
        approved = (product.get("status") or "approved") == "approved"
        if (await get_dynamic_setting("stars_enabled", "1")) == "1":
            per = int(await get_dynamic_setting("stars_per_usdt", "100"))
            stars_price = max(1, _math.ceil(
                product["price_credits"] / config.CREDITS_PER_USDT * per))
            if approved and stars_price:
                buttons.append([InlineKeyboardButton(
                    text=f"⭐ پرداخت با استارز (~{stars_price}★)",
                    callback_data=f"starsbuy_{product_id}")])
        buttons.append([InlineKeyboardButton(text="🎟 کد تخفیف دارم", callback_data=f"cpn_{product_id}")])
        if user["credits"] >= product["price_credits"]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🛒 Buy ({product['price_credits']}💰)",
                    callback_data=f"buy_product_{product_id}",
                )
            ])
        else:
            buttons.append([InlineKeyboardButton(text="✅ کردیت رایگان", callback_data="tasks_menu")])

    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="marketplace")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    # photo cover → send as fresh photo message; otherwise edit text view
    if product.get("photo_path") and os.path.exists(product["photo_path"]):
        try:
            await callback.message.answer_photo(
                FSInputFile(product["photo_path"]),
                caption=text[:1024],
                reply_markup=kb,
                parse_mode="Markdown",
            )
            await callback.answer()
            return
        except Exception:
            pass
    await edit_safe(callback.message, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("cpn_"))
async def coupon_entry(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    await state.set_state(CouponInput.waiting_code)
    await state.update_data(cpn_pid=pid)
    await edit_safe(
        callback.message,
        "🎟 **کد تخفیف**\n\nکد رو بفرست تا روی این محصول اعمال بشه:\n\nلغو: /cancel",
    )
    await callback.answer()


@router.message(CouponInput.waiting_code)
async def coupon_apply(message: Message, state: FSMContext):
    code = (message.text or "").strip()
    if not code:
        return
    if code == "/cancel":
        await state.clear()
        await message.answer("↩️ لغو شد.")
        return

    data = await state.get_data()
    pid = data.get("cpn_pid")
    product = await get_product(pid) if pid else None
    coupon = await get_coupon(code)

    if not product or not coupon or coupon["owner_id"] != product["creator_id"] or not coupon["active"]:
        await message.answer("❌ کد برای این محصول معتبر نیست.")
        return
    if coupon["max_uses"] and coupon["uses"] >= coupon["max_uses"]:
        await message.answer("❌ ظرفیت این کد پر شده.")
        return

    final_price = max(1, round(product["price_credits"] * (100 - coupon["percent"]) / 100))
    await state.update_data(**{f"cpn_ok_{pid}": coupon["id"], "cpn_final": final_price})
    await state.set_state(None)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🛒 Buy with {coupon['percent']}% OFF ({final_price}💰)",
            callback_data=f"buy_product_{pid}",
        )],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data=f"view_product_{pid}")],
    ])
    await message.answer(
        f"✅ کد **{code.upper()}** آماده‌ست:\n"
        f"💰 {product['price_credits']} → **{final_price} کردیت** ({coupon['percent']}٪ تخفیف)\n\n"
        f"برای خرید نهایی با تخفیف، دکمه زیر رو بزن:",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("buy_product_"))
async def buy_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    product = await get_product(product_id)

    if not product or not product["is_active"]:
        await callback.answer("محصول در دسترس نیست!", show_alert=True)
        return

    # banned sellers' products are frozen
    seller = await get_user(product["creator_id"])
    if seller and seller.get("is_banned"):
        await callback.answer("⛔ فروشنده این محصول مسدود است.", show_alert=True)
        return

    if product["creator_id"] == callback.from_user.id:
        await callback.answer("نمی‌تونی محصول خودت رو بخری!", show_alert=True)
        return

    # ---- resolve coupon BEFORE charging ----
    data = await state.get_data()
    await state.set_state(None)
    final_price = product["price_credits"]
    coupon_pct = 0
    coupon_code = None
    coupon_id = None
    if data.get(f"cpn_ok_{product_id}") and data.get("cpn_final"):
        coupon = await get_coupon_by_id(data[f"cpn_ok_{product_id}"])
        if (
            coupon
            and coupon["owner_id"] == product["creator_id"]
            and coupon["active"]
            and (not coupon["max_uses"] or coupon["uses"] < coupon["max_uses"])
        ):
            coupon_id = coupon["id"]
            coupon_pct = coupon["percent"]
            coupon_code = coupon["code"]
            final_price = max(1, round(product["price_credits"] * (100 - coupon_pct) / 100))

    commission = int(final_price * config.COMMISSION_RATE)
    creator_earning = final_price - commission

    # ---- shared atomic purchase service ----
    from commerce import CommerceError, purchase_with_credits
    try:
        result = await purchase_with_credits(
            callback.from_user.id,
            product_id,
            price_override=final_price,
            payment_method="credits",
            coupon_id=coupon_id,
        )
    except CommerceError as e:
        await callback.answer(str(e), show_alert=True)
        return

    purchased_now = True
    commission = result.commission
    creator_earning = result.seller_earning

    # long-term memory: update buyer's purchase profile + category interest
    try:
        from memory import record_purchase_event
        await record_purchase_event(callback.from_user.id, product)
    except Exception:
        pass

    # Promotion, referral share and upline override are shared with Mini App.
    from commerce import apply_sale_network_effects
    await apply_sale_network_effects(result, callback.bot)

    user = await get_or_create_user(callback.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دانلود محصول", callback_data=f"download_product_{product_id}")]
        if product["file_path"]
        else [InlineKeyboardButton(text="📖 مشاهده", callback_data=f"view_product_{product_id}")],
        [InlineKeyboardButton(text="⭐ ثبت دیدگاه و نظر", callback_data=f"rv_{product_id}")],
        [InlineKeyboardButton(text="🛒 فروشگاه", callback_data="marketplace")],
        [InlineKeyboardButton(text="🔙 منو", callback_data="main_menu")],
    ])

    per = config.CREDITS_PER_USDT
    discount_line = f"\n🎟 تخفیف {coupon_pct}٪ ({coupon_code}) اعمال شد" if coupon_code else ""
    await edit_safe(
        callback.message,
        f"🎉 **خرید با موفقیت انجام شد!**\n\n"
        f"📖 **{product['title']}**\n"
        f"💰 پرداخت: {final_price:,} کردیت (≈{final_price / max(1, per):.2f}$){discount_line}\n"
        f"💳 موجودی فعلی: **{user['credits']:,} کردیت** "
        f"(≈{user['credits'] / max(1, per):.2f}$)\n\n"
        f"⭐ یه دیدگاه بنویس، به فروشنده انرژی مثبت میدی!",
        kb,
    )
    await callback.answer("خرید موفق! 🎉", show_alert=True)


@router.callback_query(F.data.startswith("deactivate_product_"))
async def deactivate_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    product = await get_product(product_id)

    if not product or product["creator_id"] != callback.from_user.id:
        await callback.answer("دسترسی نداری!", show_alert=True)
        return

    async with get_db() as db:
        await db.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 محصولات من", callback_data="my_products")],
    ])
    await edit_safe(callback.message, "🔴 محصول غیرفعال شد", kb)
    await callback.answer()


@router.callback_query(F.data.startswith("activate_product_"))
async def activate_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    product = await get_product(product_id)

    if not product or product["creator_id"] != callback.from_user.id:
        await callback.answer("دسترسی نداری!", show_alert=True)
        return

    async with get_db() as db:
        await db.execute("UPDATE products SET is_active = 1 WHERE id = ?", (product_id,))
        await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 محصولات من", callback_data="my_products")],
    ])
    await edit_safe(callback.message, "🟢 محصول فعال شد", kb)
    await callback.answer()


# ================= Reviews (buyer trust layer) =================

@router.callback_query(F.data.startswith("rv_"))
async def review_entry(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    from database import is_product_purchased_by_user
    if not await is_product_purchased_by_user(pid, callback.from_user.id):
        await callback.answer("فقط خریدار می‌تواند دیدگاه ثبت کند.", show_alert=True)
        return

    row = [InlineKeyboardButton(text=f"{'⭐'*n}", callback_data=f"rvs_{pid}_{n}")
           for n in (1, 2, 3, 4, 5)]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        row,
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"view_product_{pid}")],
    ])
    product = await get_product(pid)
    await edit_safe(
        callback.message,
        f"⭐ **دیدگاه تو برای «{product['title']}»**\n\nامتیاز بده:",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rvs_"))
async def review_submit(callback: CallbackQuery):
    _, pid, stars = callback.data.split("_")
    from database import add_review, product_rating, is_product_purchased_by_user
    # integrity gate: forged callbacks cannot inject fake ratings
    if not await is_product_purchased_by_user(int(pid), callback.from_user.id):
        await callback.answer("⛔ فقط خریدار واقعی می‌تواند امتیاز بدهد.", show_alert=True)
        return
    ok = await add_review(int(pid), callback.from_user.id, int(stars))
    avg, n = await product_rating(int(pid))
    if not ok:
        await callback.answer("قبلاً برای این محصول امتیاز دادی ✅", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            f"🎉 ممنون از دیدگاهت!\n⭐ میانگین جدید این محصول: **{avg}** ({n} دیدگاه)",
            parse_mode="Markdown",
        )
    except Exception:
        pass
    await callback.answer(f"{stars}⭐ ثبت شد!", show_alert=True)


@router.callback_query(F.data == "none_pending")
async def _noop_pending(callback: CallbackQuery):
    await callback.answer("بعد از تأیید ادمین منتشر می‌شود 🛡️", show_alert=True)


# ================= ⭐ Telegram Stars checkout =================

def price_stars_for(price_credits: int, per_usdt: int) -> int:
    from config import config as cfg
    usd = price_credits / cfg.CREDITS_PER_USDT
    return max(1, _math.ceil(usd * per_usdt))


@router.callback_query(F.data.startswith("starsbuy_"))
async def stars_buy(callback: CallbackQuery):
    from hermes_engine import get_dynamic_setting
    if (await get_dynamic_setting("stars_enabled", "1")) != "1":
        await callback.answer("پرداخت استارزی غیرفعال است.", show_alert=True)
        return
    pid = int(callback.data.split("_")[1])
    product = await get_product(pid)
    if not product or not product["is_active"] or product.get("status") != "approved":
        await callback.answer("محصول در دسترس نیست!", show_alert=True)
        return
    if product["creator_id"] == callback.from_user.id:
        await callback.answer("محصول خودته!", show_alert=True)
        return
    per = int(await get_dynamic_setting("stars_per_usdt", "100"))
    stars = price_stars_for(product["price_credits"], per)
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=product["title"][:32],
        description=(product["description"] or "خرید محصول دیجیتال")[:255],
        payload=f"star:{pid}:{callback.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=product["title"][:32], amount=stars)],
    )
    await callback.answer("فاکتور استارز ارسال شد ⭐")


@router.pre_checkout_query()
async def pre_checkout(query):
    if query.invoice_payload.startswith("star:"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="پرداخت نامعتبر.")


@router.message(F.successful_payment)
async def stars_paid(message: Message):
    sp = message.successful_payment
    parts = sp.invoice_payload.split(":")     # ["star", pid, uid]
    if len(parts) != 3 or parts[0] != "star":
        return
    pid, uid = int(parts[1]), int(parts[2])
    if message.from_user.id != uid:
        return
    product = await get_product(pid)
    if (not product or not product.get("is_active")
            or product.get("status") != "approved"):
        await message.answer("⚠️ محصول دیگر در دسترس نیست — با پشتیبانی تماس بگیر.")
        return

    from hermes_engine import get_dynamic_setting
    per = int(await get_dynamic_setting("stars_per_usdt", "100"))
    expected_stars = price_stars_for(product["price_credits"], per)
    if int(sp.total_amount) != expected_stars:
        # Never deliver an invoice whose amount was changed or forged.
        try:
            await message.bot.refund_star_payment(
                user_id=uid,
                telegram_payment_charge_id=sp.telegram_payment_charge_id,
            )
        except Exception:
            pass
        await message.answer("⚠️ مبلغ پرداخت با فاکتور برابر نبود؛ پرداخت بررسی/برگشت می‌شود.")
        return

    seller = await get_user(product["creator_id"])
    seller_plan = seller.get("seller_plan") if seller else "free"
    comm_rate = 0.05 if seller_plan == "pro" else 0.15
    final_price = product["price_credits"]
    commission = int(final_price * comm_rate)
    creator_earning = final_price - commission

    async with get_db() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO purchases (buyer_id, product_id, price_credits, "
            "payment_method) VALUES (?, ?, ?, 'stars')",
            (uid, pid, final_price))
        if cur.rowcount == 0:
            await db.commit()
            try:
                await message.bot.refund_star_payment(
                    user_id=uid,
                    telegram_payment_charge_id=sp.telegram_payment_charge_id,
                )
            except Exception:
                pass
            await message.answer("ℹ️ این خرید قبلاً تحویل شده بود؛ پرداخت تکراری برگشت می‌خورد.")
            return
        await db.execute(
            "UPDATE users SET credits = credits + ?, total_earned = total_earned + ? "
            "WHERE user_id = ?",
            (creator_earning, creator_earning, product["creator_id"]))
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description)"
            " VALUES (?, ?, 'sale', ?, ?)",
            (product["creator_id"], creator_earning, pid,
             f"Stars sale: {product['title']} ({sp.total_amount}★)"))
        await db.execute(
            "INSERT INTO transactions (user_id, amount, tx_type, reference_id, description)"
            " VALUES (?, 0, 'stars_purchase', ?, ?)",
            (uid, pid, f"Paid {sp.total_amount}★ ({sp.telegram_payment_charge_id})"))
        await db.execute("UPDATE products SET sales_count = sales_count + 1 WHERE id = ?", (pid,))
        await db.execute(
            "UPDATE users SET products_sold = products_sold + 1 WHERE user_id = ?",
            (product["creator_id"],))
        await db.commit()

    # shared post-effects (promote / override / referral share / qualify)
    from handlers.org import effective_role
    if await effective_role(product["creator_id"]) == "associate":
        from database import set_role
        if await set_role(product["creator_id"], "soldier", granted_by=0):
            try:
                await message.bot.send_message(
                    product["creator_id"],
                    "🪖 فروش استارزی اولت! از کارآموز به **سرباز** ارتقا گرفتی!",
                    parse_mode="Markdown")
            except Exception:
                pass

    seller_ref = None
    from database import get_referrer
    seller_ref = await get_referrer(product["creator_id"])
    if seller_ref and commission > 0:
        srole = await effective_role(seller_ref)
        if srole in ("capo", "underboss", "godfather"):
            override = int(commission * config.CAPO_OVERRIDE_PCT)
            if override > 0:
                await update_credits(seller_ref, override, "capo_override",
                                     f"Override on stars sale: {product['title']}", pid)

    referrer_id = await get_referrer(uid)
    if referrer_id and commission > 0:
        share = int(commission * config.REF_COMMISSION_SHARE)
        if share > 0:
            await update_credits(referrer_id, share, "ref_commission",
                                 f"Lifetime share on stars sale to {uid}", pid)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دانلود محصول", callback_data=f"download_product_{pid}")]
        if product["file_path"]
        else [InlineKeyboardButton(text="📖 مشاهده", callback_data=f"view_product_{pid}")],
        [InlineKeyboardButton(text="⭐ ثبت دیدگاه", callback_data=f"rv_{pid}")],
        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="main_menu")],
    ])
    await message.answer(
        f"🎉 **خرید با استارز انجام شد!**\n\n"
        f"📖 **{product['title']}**\n"
        f"⭐ پرداخت: {sp.total_amount}★\n\nاز خریدت لذت ببر!",
        reply_markup=kb,
    )
