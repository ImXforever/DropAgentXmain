import re

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

from config import config as cfg
from database import (
    get_user, get_role, get_domain, set_role,
    category_stats, category_products, set_product_flag,
    capo_team_stats, count_total_refs, count_qualified_refs,
    create_coupon, ROLES, ROLE_FA,
)
from utils import edit_safe

router = Router()

CATEGORIES = ["education", "graphics", "coding", "content", "template", "tools", "general"]
CATEGORY_FA = {
    "education": "📚 آموزش", "graphics": "🎨 گرافیک", "coding": "💻 کدنویسی",
    "content": "📝 محتوا", "template": "📦 قالب", "tools": "🔧 ابزار",
    "general": "📂 سایر",
}


class CouponFlow(StatesGroup):
    waiting_format = State()


def is_godfather(user_id: int) -> bool:
    return user_id in cfg.ADMIN_IDS


async def effective_role(user_id: int) -> str:
    if is_godfather(user_id):
        return "godfather"
    return await get_role(user_id)


@router.callback_query(F.data == "org")
async def org_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    role = await effective_role(uid)

    if role == "godfather":
        text = (
            "👑 **The Godfather — باس بزرگ**\n\n"
            "قلمرو تو: کل پلتفرم.\n"
            "قوانین طلایی دست توئه: کارمزد، انتصاب آندرباس‌ها، امنیت.\n\n"
            f"⚙️ کمیسیون پلتفرم: {int(cfg.COMMISSION_RATE*100)}٪\n"
            f"🕴️ آستانه کاپو: {cfg.CAPO_MIN_REFS} نفر فعال | سهم اوورراید: {int(cfg.CAPO_OVERRIDE_PCT*100)}٪\n\n"
            "🛠 انتصاب رتبه از ترمینال:\n"
            "`/setrole user_id soldier`\n"
            "`/setrole user_id underboss education`"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Admin Panel", callback_data="admin_panel")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
        ])
        await edit_safe(callback.message, text, kb)
        await callback.answer()
        return

    if role == "underboss":
        domain = (await get_domain(uid)) or "general"
        st = await category_stats(domain)
        prods = await category_products(domain)
        lines = [f"{p['id']}. {'⭐' if p['is_featured'] else ''}{p['title'][:30]} — {p['price_credits']}💰 | فروش {p['sales_count']}" + (" 🔴غیرفعال" if not p["is_active"] else "") for p in prods]
        kb_rows = []
        for p in prods:
            feat_label = "☆ بردار از فیچر" if p["is_featured"] else "⭐ فیچر کن"
            act_label = "🟢 فعال کن" if not p["is_active"] else "🔴 مخفی کن"
            kb_rows.append([
                InlineKeyboardButton(text=f"#{p['id']} {feat_label}", callback_data=f"ubf_{p['id']}_1"),
                InlineKeyboardButton(text=act_label, callback_data=f"uba_{p['id']}_{0 if p['is_active'] else 1}"),
            ])
        kb_rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="org")])
        kb_rows.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")])
        await edit_safe(
            callback.message,
            f"👔 **Underboss — قلمرو {CATEGORY_FA.get(domain, domain)}**\n\n"
            f"📊 **گزارش حوزه:**\n"
            f"• محصولات فعال: {st['products']}\n"
            f"• کل فروش: {st['sales']}\n"
            f"• حجم معاملات: {st['volume']:,} کردیت\n"
            f"• فروشندگان: {st['sellers']}\n\n"
            f"🛒 **محصولات برتر حوزه** (مدیریت):\n" + ("\n".join(lines) if lines else "—"),
            InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )
        await callback.answer()
        return

    if role == "capo":
        team = await capo_team_stats(uid)
        total = await count_total_refs(uid)
        qual = await count_qualified_refs(uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎟 ساخت کد تخفیف", callback_data="crt_coupon")],
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="org")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")],
        ])
        await edit_safe(
            callback.message,
            f"🕴️ **Capo — باس تیم معرفی خودت**\n\n"
            f"📊 **تیم:**\n"
            f"• اعضای شبکه: {total} نفر\n"
            f"• سربازهای فعال: {qual} نفر\n"
            f"• خریدهای تیم: {team['team_buys']} عدد\n"
            f"• کل درآمد شبکه‌ات: {team['earned']:,} کردیت\n\n"
            f"💼 اوورراید: از کمیسیون هر فروشِ فروشنده‌های زیرمجموعه‌ات "
            f"**{int(cfg.CAPO_OVERRIDE_PCT*100)}٪** مال توئه — همیشه.\n\n"
            f"🎯 هدف بعدی: نگه‌دار تیمت بفروشه؛ تو سود می‌بری.",
            kb,
        )
        await callback.answer()
        return

    # soldier / associate
    is_soldier = role == "soldier"
    kb_rows = []
    if is_soldier:
        kb_rows.append([InlineKeyboardButton(text="🎟 ساخت کد تخفیف", callback_data="crt_coupon")])
    kb_rows.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="main_menu")])

    if is_soldier:
        text = (
            "🪖 **Soldier — باس فروشگاه شخصی‌ات**\n\n"
            "قلمرو تو: محصولاتت، قیمتت، مشتریانت.\n"
            "هیچکس در امور فروشگاهت دخالت نمی‌کنه — فقط کارمزد رو پرداخت کن.\n\n"
            f"🎟 ابزار فرماندهی: کد تخفیف اختصاصی بساز تا بازار خودت رو گرم کنی.\n"
            f"📈 مسیر ارتقا: با {cfg.CAPO_MIN_REFS} دعوت فعال → **کاپو** می‌شی و از فروش تیم‌ات اوورراید می‌گیری."
        )
    else:
        sold = await get_user(uid)
        first_sale_hint = "اولین فروشت که ثبت بشه، خودکار سرباز می‌شی."
        text = (
            "🎓 **Associate — باس مسیر رشد خودت**\n\n"
            "قلمرو تو: یادگیری، تست محصولات، مشتریان اولیه‌ات.\n\n"
            f"🚀 {first_sale_hint}\n"
            f"💡 یا با دعوت دوستان از همین الان شبکه‌ات رو بساز."
        )

    await edit_safe(callback.message, text, InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await callback.answer()


# ---------- Underboss moderation ----------

@router.callback_query(F.data.startswith("ubf_"))
async def ub_feature(callback: CallbackQuery):
    _, pid, val = callback.data.split("_")
    domain = await get_domain(callback.from_user.id)
    ok = await set_product_flag(int(pid), "is_featured", int(val), domain or "")
    await callback.answer("انجام شد ⭐" if ok else "خارج از قلمروت!", show_alert=not ok)
    if ok:
        await org_menu_refresh(callback)


@router.callback_query(F.data.startswith("uba_"))
async def ub_activate(callback: CallbackQuery):
    _, pid, val = callback.data.split("_")
    domain = await get_domain(callback.from_user.id)
    ok = await set_product_flag(int(pid), "is_active", int(val), domain or "")
    await callback.answer("انجام شد" if ok else "خارج از قلمروت!", show_alert=not ok)
    if ok:
        await org_menu_refresh(callback)


async def org_menu_refresh(callback: CallbackQuery):
    class _FakeState:
        async def clear(self):
            pass
    await org_menu(callback, _FakeState())


# ---------- Coupons ----------

@router.callback_query(F.data == "crt_coupon")
async def crt_coupon(callback: CallbackQuery, state: FSMContext):
    role = await effective_role(callback.from_user.id)
    if role not in ("soldier", "capo"):
        await callback.answer("فقط سرباز به بالا!", show_alert=True)
        return
    await state.set_state(CouponFlow.waiting_format)
    await edit_safe(
        callback.message,
        "🎟 **کد تخفیف شخصی** (سلاح فروشگاه تو)\n\n"
        "فرمت رو بفرست:\n`CODE درصد حداکثر_استفاده`\n\n"
        "مثال: `LAUNCH20 20 50`\n"
        "= کد LAUNCH20 با ۲۰٪ تخفیف برای ۵۰ بار اول.\n\n"
        "⚠️ تخفیف از سهم فروشنده (تو) کسر می‌شه. لغو: /cancel",
    )
    await callback.answer()


@router.message(CouponFlow.waiting_format)
async def coupon_input(message: Message, state: FSMContext):
    parts = (message.text or "").split()
    if len(parts) != 3 or message.text.strip() == "/cancel":
        if message.text and message.text.strip() == "/cancel":
            await state.clear()
            await message.answer("↩️ لغو شد.")
            return
        await message.answer("❌ فرمت: `CODE درصد تعداد`")
        return
    code, pct_s, uses_s = parts
    if not re.fullmatch(r"[A-Za-z0-9]{3,16}", code):
        await message.answer("❌ کد: ۳ تا ۱۶ کاراکتر حروف/عدد لاتین.")
        return
    try:
        pct, max_uses = int(pct_s), int(uses_s)
    except ValueError:
        await message.answer("❌ درصد و تعداد باید عدد باشن.")
        return
    if not (1 <= pct <= 90):
        await message.answer("❌ درصد بین ۱ تا ۹۰.")
        return
    if not (1 <= max_uses <= 10000):
        await message.answer("❌ تعداد بین ۱ تا ۱۰٬۰۰۰.")
        return

    cid = await create_coupon(message.from_user.id, code, pct, max_uses)
    await state.clear()
    if cid is None:
        await message.answer("⚠️ این کد قبلاً گرفته شده — یکی دیگه انتخاب کن.")
        return
    await message.answer(
        f"✅ کد تخفیف **{code.upper()}** فعال شد!\n"
        f"🎟 {pct}٪ تخفیف | ظرفیت {max_uses} بار\n\n"
        f"مشتری موقع خرید محصولِ تو، کد رو وارد می‌کنه.",
    )
